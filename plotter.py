# plotter.py
import threading
import time
from collections import deque
from typing import Callable, Deque, Tuple
import matplotlib.pyplot as plt

class LivePlot:
    def __init__(self, title: str = 'QMB6Pro – CH1 Rate'):
        self.x: Deque[float] = deque(maxlen=1200)
        self.y: Deque[float] = deque(maxlen=1200)
        self._running = False
        self.title = title

    def start(self, value_fn: Callable[[], Tuple[float, float]]):
        self._running = True
        t = threading.Thread(target=self._loop, args=(value_fn,), daemon=True)
        t.start()
        self._show()

    def stop(self):
        self._running = False

    def _loop(self, value_fn):
        t0 = time.time()
        while self._running:
            ts, val = value_fn()
            self.x.append(ts - t0)
            self.y.append(val)
            time.sleep(0.1)

    def _show(self):
        plt.figure()
        plt.title(self.title)
        plt.xlabel('Time [s]')
        plt.ylabel('Rate [Å/s]')
        line, = plt.plot([], [])

        def update(_):
            line.set_data(list(self.x), list(self.y))
            if self.x:
                plt.xlim(max(0, self.x[0]), max(10, self.x[-1]))
                ymin = min(self.y) if self.y else -1
                ymax = max(self.y) if self.y else 1
                pad = 0.1 * (ymax - ymin + 1)
                plt.ylim(ymin - pad, ymax + pad)
            return line,

        import matplotlib.animation as animation
        ani = animation.FuncAnimation(plt.gcf(), update, interval=200, blit=True)
        plt.show()
