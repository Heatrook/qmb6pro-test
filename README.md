QMB6Pro Test App – GUI (CH1/CH2 Thickness)

Instalacja:
  py -3.12 -m venv .venv
  . .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt

Uruchom:
  python app_gui.py

Działanie:
  - Start bez sprzętu -> status "Czekam na urządzenie…" w oknie.
  - Co ~2s skan COM i próba probe (pierwszy rejestr z registers.json).
  - Po wykryciu urządzenia: automatyczny odczyt, wykres grubości (CH1/CH2),
    wskaźniki i edycja wybranych rejestrów (window, FIFO, alpha ON/alpha, density, Z, tooling).

Zapis R/W:
  - Walidacja zakresów (gdzie podane).
  - Skale: density/Z x0.01, alpha x0.01, tooling x0.001 (mapa w registers.json).
  - Pojedyncze write (FC6). TCP po PoE możliwy po dopisaniu klienta TCP (pymodbus).

Build .exe:
  build_gui.bat -> dist\QMB6Pro_GUI.exe

Uwaga:
  - Jeśli 32-bit wygląda źle -> zmień "endianness" w registers.json na "little".
  - Jeśli nie masz pymodbus, TCP jest nieaktywne (RTU działa normalnie).
