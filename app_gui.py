# app_gui.py — QMB6Pro GUI (modern): 2 channels, Thickness chart (Å), high-contrast UI,
# settings forms with auto-commit, theme-aware colors, rolling window, oscillator combobox,
# robust registers.json lookup for PyInstaller onefile. Auto-maximize + minsize so nothing is hidden.

import json
import threading
import time
import queue
from collections import deque
from typing import Dict, Any, List, Tuple, Optional

import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import PRIMARY, OUTLINE

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from pathlib import Path
import sys

from autodetect import autodetect, resource_path  # reuse helper
from modbus_client import RTUClient, find_reg, scale_to_raw, write_u16, read_all

CFG_PATH = resource_path('registers.json')
POLL_INTERVAL_MS = 200
SCAN_INTERVAL_SEC = 2.0
SAMPLE_PERIOD_SEC = 0.3


def load_cfg() -> Dict[str, Any]:
    with open(CFG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def safe_number(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) else None


def compute_crystal_usage(values: Dict[str, Any], ch_prefix: str) -> float:
    f_cur = safe_number(values.get(f'{ch_prefix}_Frequency_0p01Hz'))
    f_min = safe_number(values.get(f'{ch_prefix}_MinFreq_Hz'))
    f_max = safe_number(values.get(f'{ch_prefix}_MaxFreq_Hz'))
    if f_cur is None or f_min is None or f_max is None or f_max <= f_min:
        return 0.0
    usage = (f_max - f_cur) / (f_max - f_min)
    return max(0.0, min(1.0, usage)) * 100.0


# ---------------- Settings Panel ----------------

class SettingsPanel(tb.Frame):
    Row = Tuple[str, str, str, str]

    def __init__(self, master, rows: List[Row], on_write, get_reg, connected_getter):
        super().__init__(master, padding=10)
        self.rows = rows
        self.on_write = on_write
        self.get_reg = get_reg
        self.is_connected = connected_getter
        self.vars: Dict[Tuple[str, str], tk.Variable] = {}
        self.widgets: Dict[Tuple[str, str], tk.Widget] = {}
        self._building = False
        self._build()

    def _build(self):
        self._building = True
        tb.Label(self, text="Settings", font=("-size", 11, "-weight", "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        tb.Label(self, text="CH1", font=("-size", 10, "-weight", "bold")).grid(row=0, column=1, sticky="w", padx=(12, 0))
        tb.Label(self, text="CH2", font=("-size", 10, "-weight", "bold")).grid(row=0, column=2, sticky="w", padx=(12, 0))
        tb.Label(self, text="Unit").grid(row=0, column=3, sticky="w", padx=(12, 0))

        for i, (label, n1, n2, unit) in enumerate(self.rows, start=1):
            tb.Label(self, text=label).grid(row=i, column=0, sticky="e", pady=3)
            self._make_field(i, 1, n1)
            self._make_field(i, 2, n2)
            tb.Label(self, text=unit).grid(row=i, column=3, sticky="w", padx=(12, 0))

        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self._building = False
        self.set_connected(False)

    def _commit(self, reg_name: str, col: int):
        if self._building or not self.is_connected():
            return
        var = self.vars.get((reg_name, 'var'))
        if not var:
            return
        text = var.get().strip()
        ch = 1 if col == 1 else 2
        try:
            self.on_write(reg_name, ch, text)
        except Exception as e:
            messagebox.showerror("Write failed", f"{reg_name}: {e}")

    def _make_field(self, row: int, col: int, reg_name: str):
        reg = self.get_reg(reg_name)
        var = tk.StringVar(value="")
        self.vars[(reg_name, 'var')] = var

        if "OscillatorSelect" in reg_name:
            cb = tb.Combobox(self, state="readonly", values=["internal", "external"], textvariable=var)
            cb.bind("<<ComboboxSelected>>", lambda _e: self._commit(reg_name, col))
            cb.grid(row=row, column=col, sticky="we", padx=6)
            self.widgets[(reg_name, 'widget')] = cb

        elif "AlphaFiltering_ON" in reg_name:
            sw = tb.Checkbutton(self, bootstyle="success", text="")
            def sw_cmd():
                var.set("1" if sw.instate(["selected"]) else "0")
                self._commit(reg_name, col)
            sw.configure(command=sw_cmd)
            sw.grid(row=row, column=col, sticky="we", padx=6)
            self.widgets[(reg_name, 'widget')] = sw

        elif "AlphaValue" in reg_name:
            frame = tb.Frame(self)
            var.set("0.50")
            sp = tb.Spinbox(
                frame, from_=0.01, to=1.00, increment=0.01, width=7,
                textvariable=var, command=lambda: self._commit(reg_name, col), format="%.2f"
            )
            sl = tb.Scale(
                frame, from_=0.01, to=1.00, orient="horizontal", length=160,
                command=lambda _=None: self._commit(reg_name, col)
            )
            sp.pack(side="left"); sl.pack(side="left", fill="x", expand=True, padx=(6, 0))

            def sync_widgets(*_):
                try:
                    v = float(var.get())
                except Exception:
                    return
                if v < 0.01: v = 0.01
                if v > 1.00: v = 1.00
                sp.delete(0, "end"); sp.insert(0, f"{v:.2f}")
                sl.set(v)
            var.trace_add("write", sync_widgets)

            frame.grid(row=row, column=col, sticky="we", padx=6)
            self.widgets[(reg_name, 'widget_spin')] = sp
            self.widgets[(reg_name, 'widget_scale')] = sl

        elif "Window_ms" in reg_name:
            sp = tb.Spinbox(self, from_=100, to=2000, increment=10, width=8,
                            textvariable=var, command=lambda: self._commit(reg_name, col))
            sp.grid(row=row, column=col, sticky="we", padx=6)
            self.widgets[(reg_name, 'widget')] = sp

        elif "FIFO_FilterSize" in reg_name:
            sp = tb.Spinbox(self, from_=0, to=64, width=8,
                            textvariable=var, command=lambda: self._commit(reg_name, col))
            sp.grid(row=row, column=col, sticky="we", padx=6)
            self.widgets[(reg_name, 'widget')] = sp

        else:
            ent = tb.Entry(self, textvariable=var)
            ent.grid(row=row, column=col, sticky="we", padx=6)
            ent.bind("<Return>", lambda _e: self._commit(reg_name, col))
            ent.bind("<FocusOut>", lambda _e: self._commit(reg_name, col))
            self.widgets[(reg_name, 'widget')] = ent

    def sync_values(self, values: Dict[str, Any]):
        for (reg_name, key), var in list(self.vars.items()):
            if key != 'var' or reg_name not in values:
                continue
            w = self.widgets.get((reg_name, 'widget')) or self.widgets.get((reg_name, 'widget_spin'))
            try:
                if w and w.focus_displayof() == w:
                    continue
            except Exception:
                pass
            v = values[reg_name]
            if isinstance(v, bool):
                var.set("1" if v else "0")
                sw = self.widgets.get((reg_name, 'widget'))
                if sw:
                    if v: sw.state(["selected"])
                    else: sw.state(["!selected"])
            elif isinstance(v, (int, float)):
                if "AlphaValue" in reg_name:
                    var.set(f"{float(v):.2f}")
                else:
                    var.set(f"{v:.3f}".rstrip('0').rstrip('.') if isinstance(v, float) else str(v))
            else:
                var.set(str(v))

    def set_connected(self, connected: bool):
        state = "normal" if connected else "disabled"
        for w in self.widgets.values():
            try:
                w.configure(state=state)
            except Exception:
                pass


# ---------------- Main App ----------------

class App(tb.Window):
    def __init__(self, themename: str = "darkly"):
        super().__init__(themename=themename)
        self.title("QMB6Pro – Thickness Monitor")
        # domyślka, zanim zmaksymalizujemy
        self.geometry("1200x780")
        self.minsize(1120, 700)

        self.cfg = load_cfg()
        self.regs = self.cfg['registers']
        self.endianness = self.cfg['endianness']
        self.slave = self.cfg['slave_id']

        self.cli: Optional[RTUClient] = None
        self.connected = False
        self._stop = threading.Event()
        self.q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()

        self._high_contrast_labels: List[tk.Widget] = []

        self._build_ui()

        # auto-maximize na starcie i ustaw minsize do wymaganego rozmiaru
        self.after(10, self._maximize_on_start)
        self.after(40, self._ensure_min_size)

        self.t0: Optional[float] = None
        self.x = deque(maxlen=3600)
        self.y1 = deque(maxlen=3600)
        self.y2 = deque(maxlen=3600)

        self._apply_text_contrast(self.style.theme.name)

        self.worker_th = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_th.start()

        self.after(POLL_INTERVAL_MS, self._ui_tick)

    def _maximize_on_start(self):
        try:
            # Windows
            self.state('zoomed')
        except Exception:
            # reszta światów: jak się nie da, ustaw maksymalny geometry
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            # zostaw mały margines na paski systemowe
            self.geometry(f"{sw}x{int(sh*0.94)}+0+0")

    def _ensure_min_size(self):
        # po zbudowaniu UI policz wymagany rozmiar i ustaw jako minimum,
        # żeby nic się nie chowało przy ponownym starcie
        try:
            self.update_idletasks()
            req_w = self.winfo_reqwidth()
            req_h = self.winfo_reqheight()
            # cap, żeby minsize nie był absurdalny na małych ekranach
            scr_w = self.winfo_screenwidth()
            scr_h = self.winfo_screenheight()
            req_w = min(max(req_w, 1000), scr_w)
            req_h = min(max(req_h, 700), scr_h)
            self.minsize(req_w, req_h)
        except Exception:
            pass

    def _build_ui(self):
        top = tb.Frame(self, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        self.status_var = tk.StringVar(value="Waiting for device… Connect QMB6Pro (RS232/485/USB).")
        stat_lbl = tb.Label(top, textvariable=self.status_var)
        stat_lbl.pack(side=tk.LEFT)
        self._high_contrast_labels.append(stat_lbl)

        tb.Button(top, text="Scan now", bootstyle=OUTLINE, command=self._force_scan).pack(side=tk.RIGHT, padx=(6, 0))
        self.theme_btn = tb.Button(top, text="Light/Dark", bootstyle=OUTLINE, command=self._toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=6)

        cards = tb.Frame(self, padding=(10, 4))
        cards.pack(side=tk.TOP, fill=tk.X)
        self._card_ch1 = self._make_channel_card(cards, "CH1"); self._card_ch1.pack(side=tk.TOP, fill=tk.X, pady=4)
        self._card_ch2 = self._make_channel_card(cards, "CH2"); self._card_ch2.pack(side=tk.TOP, fill=tk.X, pady=4)

        usage = tb.Frame(self, padding=(10, 4))
        usage.pack(side=tk.TOP, fill=tk.X)
        lbl1 = tb.Label(usage, text="Crystal wear CH1:"); lbl1.grid(row=0, column=0, sticky="w"); self._high_contrast_labels.append(lbl1)
        self.usage1 = tk.DoubleVar(value=0.0)
        tb.Progressbar(usage, variable=self.usage1, maximum=100).grid(row=0, column=1, sticky="we", padx=8)
        lbl2 = tb.Label(usage, text="CH2:"); lbl2.grid(row=0, column=2, sticky="e", padx=(12, 0)); self._high_contrast_labels.append(lbl2)
        self.usage2 = tk.DoubleVar(value=0.0)
        tb.Progressbar(usage, variable=self.usage2, maximum=100).grid(row=0, column=3, sticky="we", padx=8)
        usage.grid_columnconfigure(1, weight=1); usage.grid_columnconfigure(3, weight=1)

        plot_frame = tb.Frame(self, padding=(10, 6))
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(6.5, 3.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("CH1 / CH2 Thickness [Å]")
        self.ax.set_xlabel("time [s]")
        self.ax.set_ylabel("Thickness [Å]")

        self.WINDOW_SEC = 120
        self.ax.set_autoscalex_on(False)
        self.ax.margins(x=0)

        self.line1, = self.ax.plot([], [], label="CH1")
        self.line2, = self.ax.plot([], [], label="CH2")
        self._apply_theme_to_plot(self.style.theme.name)

        self.ax.legend(loc="upper left")
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        settings_frame = tb.Labelframe(self, text="Settings (auto-save)", padding=10)
        settings_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)

        self.param_defs: List[SettingsPanel.Row] = [
            ("Oscillator",               "CH1_OscillatorSelect",    "CH2_OscillatorSelect",   ""),
            ("Window [ms] (100–2000)",  "CH1_Window_ms",           "CH2_Window_ms",           "ms"),
            ("FIFO size (0–64)",        "CH1_FIFO_FilterSize",     "CH2_FIFO_FilterSize",     ""),
            ("Alpha ON (0/1)",          "CH1_AlphaFiltering_ON",   "CH2_AlphaFiltering_ON",   ""),
            ("Alpha",                   "CH1_AlphaValue_x100",     "CH2_AlphaValue_x100",     ""),
            ("Density",                 "CH1_Density",             "CH2_Density",             ""),
            ("Z-Factor",                "CH1_ZFactor",             "CH2_ZFactor",             ""),
            ("Tooling factor x1000",    "CH1_ToolingFactor_x1000", "CH2_ToolingFactor_x1000", "")
        ]

        def _get_reg(name): return find_reg(self.regs, name)
        def _is_connected(): return self.connected and self.cli is not None

        def _on_write(reg_name: str, channel: int, text: str):
            reg = find_reg(self.regs, reg_name)
            if reg.get('type') == 'enum16' and 'map' in reg:
                inv = {str(v).lower(): int(k) for k, v in reg['map'].items()}
                if text.lower() in inv:
                    iv = inv[text.lower()]
                else:
                    iv = int(float(text))
                write_u16(self.cli, reg['address'], iv, fn=6)
                return
            if reg['type'] == 'bool16':
                iv = 1 if text.lower() in ("1", "true", "on", "yes") else 0
            else:
                fv = float(text)
                if 'min' in reg: fv = max(float(reg['min']), fv)
                if 'max' in reg: fv = min(float(reg['max']), fv)
                iv = scale_to_raw(fv, reg)
            write_u16(self.cli, reg['address'], iv, fn=6)

        self.settings = SettingsPanel(settings_frame, self.param_defs, _on_write, _get_reg, _is_connected)
        self.settings.pack(fill=tk.X)

    def _make_channel_card(self, parent, title):
        card = tb.Frame(parent, padding=10, borderwidth=1, relief="solid")
        title_lbl = tb.Label(card, text=title, bootstyle=PRIMARY)
        title_lbl.grid(row=0, column=0, sticky="w", pady=(0, 4))

        vars_map = { "freq": tk.StringVar(value="–"),
                     "rate": tk.StringVar(value="–"),
                     "thick": tk.StringVar(value="–"),
                     "status": tk.StringVar(value="–") }

        def add_row(r, c0, label, var):
            lbl = tb.Label(card, text=label); lbl.grid(row=r, column=c0, sticky="e"); self._high_contrast_labels.append(lbl)
            val = tb.Label(card, textvariable=var); val.grid(row=r, column=c0 + 1, sticky="w", padx=6); self._high_contrast_labels.append(val)

        add_row(1, 0, "Freq [Hz]:",     vars_map["freq"])
        add_row(1, 2, "Rate [Å/s]:",    vars_map["rate"])
        add_row(1, 4, "Thickness [Å]:", vars_map["thick"])
        add_row(1, 6, "Crystal:",       vars_map["status"])

        for col in (1, 3, 5, 7):
            card.grid_columnconfigure(col, weight=1)

        setattr(self, f"{title.lower()}_vars", vars_map)
        return card

    def _apply_text_contrast(self, theme: str):
        fg = "white" if theme == "darkly" else "black"
        for lbl in self._high_contrast_labels:
            try:
                lbl.configure(foreground=fg)
            except Exception:
                pass

    def _apply_theme_to_plot(self, theme: str):
        if theme == "darkly":
            fig_bg = "#222222"; ax_bg = "#222222"; axis = "white"
            c1, c2 = "#6ab0ff", "#ffb86b"
        else:
            fig_bg = "white"; ax_bg = "white"; axis = "black"
            c1, c2 = "#1f77b4", "#d62728"

        self.fig.patch.set_facecolor(fig_bg)
        self.ax.set_facecolor(ax_bg)
        self.ax.tick_params(colors=axis, labelcolor=axis)
        for spine in self.ax.spines.values():
            spine.set_color(axis)
        self.ax.xaxis.label.set_color(axis); self.ax.yaxis.label.set_color(axis); self.ax.title.set_color(axis)
        self.line1.set_color(c1); self.line2.set_color(c2)
        leg = self.ax.legend(loc="upper left")
        if leg:
            for text in leg.get_texts():
                text.set_color(axis)
            leg.get_frame().set_facecolor(ax_bg)
            leg.get_frame().set_edgecolor(axis)
        if hasattr(self, "canvas"):
            self.canvas.draw_idle()

    def _toggle_theme(self):
        cur = self.style.theme.name
        next_theme = "litera" if cur == "darkly" else "darkly"
        self.style.theme_use(next_theme)
        self._apply_theme_to_plot(next_theme)
        self._apply_text_contrast(next_theme)

    def _force_scan(self):
        self.status_var.set("Scanning COM ports…")

    def _worker_loop(self):
        while not self._stop.is_set():
            try:
                if not self.connected:
                    det = autodetect()
                    if det:
                        port, baud, parity = det
                        self.cli = RTUClient(port, baud, self.slave, parity=parity)
                        self.connected = True
                        self.q.put(("status", f"Connected: {port} {baud} {parity}, slave={self.slave}"))
                    else:
                        time.sleep(SCAN_INTERVAL_SEC)
                        continue
                else:
                    t = time.time()
                    values = read_all(self.cli, self.regs, self.endianness)
                    self.q.put(("data", (t, values)))
                    time.sleep(SAMPLE_PERIOD_SEC)
            except Exception as e:
                self.connected = False
                self.cli = None
                self.q.put(("status", f"Disconnected: {type(e).__name__}. Waiting for device…"))
                time.sleep(SCAN_INTERVAL_SEC)

    def _ui_tick(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "data":
                    ts, values = payload
                    self._update_indicators(values)
                    self._update_plot(ts, values)
                    self.settings.sync_values(values)
                    self.settings.set_connected(self.connected and self.cli is not None)
        except queue.Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._ui_tick)

    def _fmt(self, x, prec=2):
        return f"{x:.{prec}f}" if isinstance(x, (int, float)) else "–"

    def _update_indicators(self, v: Dict[str, Any]):
        ch1 = self.ch1_vars; ch2 = self.ch2_vars
        ch1["freq"].set(self._fmt(v.get("CH1_Frequency_0p01Hz")))
        ch1["rate"].set(self._fmt(v.get("CH1_Rate_A_per_s")))
        ch1["thick"].set(self._fmt(v.get("CH1_Thickness_A")))
        ch1["status"].set(str(v.get("CH1_CrystalStatus", "–")))
        ch2["freq"].set(self._fmt(v.get("CH2_Frequency_0p01Hz")))
        ch2["rate"].set(self._fmt(v.get("CH2_Rate_A_per_s")))
        ch2["thick"].set(self._fmt(v.get("CH2_Thickness_A")))
        ch2["status"].set(str(v.get("CH2_CrystalStatus", "–")))
        self.usage1.set(compute_crystal_usage(v, "CH1"))
        self.usage2.set(compute_crystal_usage(v, "CH2"))

    def _update_plot(self, ts: float, v: Dict[str, Any]):
        x = 0.0 if self.t0 is None else ts - self.t0
        if self.t0 is None:
            self.t0 = ts
        t1 = v.get("CH1_Thickness_A"); t2 = v.get("CH2_Thickness_A")
        if not isinstance(t1, (int, float)): t1 = 0.0
        if not isinstance(t2, (int, float)): t2 = 0.0
        self.x.append(x); self.y1.append(t1); self.y2.append(t2)
        self.line1.set_data(self.x, self.y1); self.line2.set_data(self.x, self.y2)
        right = max(10.0, self.x[-1]); left = 0.0 if right <= self.WINDOW_SEC else right - self.WINDOW_SEC
        self.ax.set_xlim(left, right)
        ymin = min(min(self.y1), min(self.y2)); ymax = max(max(self.y1), max(self.y2))
        if ymin == ymax: ymax = ymin + 1.0
        pad = 0.05 * (ymax - ymin); self.ax.set_ylim(ymin - pad, ymax + pad)
        self.canvas.draw_idle()

    def on_close(self):
        self._stop.set(); self.destroy()


if __name__ == '__main__':
    app = App(themename="darkly")
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
