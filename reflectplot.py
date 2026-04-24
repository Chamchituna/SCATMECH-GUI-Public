from __future__ import annotations
import csv
import numpy as np
import matplotlib.pyplot as plt


def _read_numeric_csv(path: str) -> np.ndarray:
    """Read whitespace- or comma-separated numeric CSV into ndarray."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        rdr = csv.reader(f)
        for raw in rdr:
            if not raw:
                continue
            parts = raw if len(raw) > 1 else raw[0].split()
            try:
                rows.append([float(x) for x in parts])
            except ValueError:
                continue
    if not rows:
        raise ValueError("No numeric rows found in file.")
    return np.array(rows, dtype=float)


def plot_reflectance(ax, csv_path: str, component: str = "p", semilogy: bool = False):
  
    data = _read_numeric_csv(csv_path)
    if data.shape[1] < 3:
        raise ValueError("Expected at least 3 columns: θ, R_p, R_s")

    theta = data[:, 0]
    Rp = data[:, 1]
    Rs = data[:, 2]

    ax.cla()
    if component.lower().startswith("p"):
        y = Rp
        label = "Rp (p-polarized)"
    else:
        y = Rs
        label = "Rs (s-polarized)"

    if semilogy:
        ax.semilogy(theta, y, label=label)
    else:
        ax.plot(theta, y, label=label)

    ax.set_xlabel("Incidence angle θ (deg)")
    ax.set_ylabel("Reflectance")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")

def plot_csv(ax, csv_path: str, x_col: int = 0, y_col: int = 1, semilogy: bool = False, label: str | None = None):
    
    data = _read_numeric_csv(csv_path)
    ncols = data.shape[1]
    if max(x_col, y_col) >= ncols:
        raise ValueError(f"CSV has {ncols} columns; need at least {max(x_col, y_col)+1}.")

    x = data[:, x_col]
    y = data[:, y_col]

    ax.cla()
    if semilogy:
        ax.semilogy(x, y, label=label)
    else:
        ax.plot(x, y, label=label)

    ax.set_xlabel("Incidence angle θ (deg)" if x_col == 0 else "X")
    if label in ("Rp", "Rs"):
        ax.set_ylabel("Reflectance")
    else:
        ax.set_ylabel("Value")

    if label:
        ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
