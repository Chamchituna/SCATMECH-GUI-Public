import os, sys, runpy, pathlib

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE / "main.py"

if os.name == "nt" and sys.executable.lower().endswith("python.exe"):
    pyw = sys.executable[:-10] + "pythonw.exe"  
    if pathlib.Path(pyw).exists():
        os.execv(pyw, [pyw, __file__])

os.chdir(HERE)

try:
    runpy.run_path(str(MAIN), run_name="__main__")
except Exception as e:
    try:
        import tkinter as tk
        from tkinter import messagebox
        tk.Tk().withdraw()
        messagebox.showerror("SCATMECH GUI - Startup Error", f"{type(e).__name__}: {e}")
    except Exception:
        print(f"Startup error: {e}")
    raise
