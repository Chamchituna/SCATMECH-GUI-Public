from __future__ import annotations

import csv
import math
from typing import List, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from mpl_toolkits.mplot3d import Axes3D  


# Metric selection
_METRIC_NAME = "S11"  # default
_COLOR_SCALE = "linear"


def set_metric(name: str) -> None:
    global _METRIC_NAME
    name = (name or "").strip()
    allowed = {"S11", "Pol", "S33", "S34"}
    if name not in allowed:
        raise ValueError(f"metric must be one of {sorted(allowed)}")
    _METRIC_NAME = name


def get_metric() -> str:
    return _METRIC_NAME


def set_color_scale(scale: str) -> None:
    global _COLOR_SCALE
    normalized = (scale or "linear").strip().lower()
    aliases = {
        "normal": "linear",
        "lin": "linear",
        "linear": "linear",
        "log": "log",
        "logarithmic": "log",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"linear", "log"}:
        raise ValueError("color scale must be 'linear' or 'log'")
    _COLOR_SCALE = normalized


def get_color_scale() -> str:
    return _COLOR_SCALE


# CSV parsing 
def _read_csv(csv_path: str) -> Tuple[List[str], List[List[str]]]:
    with open(csv_path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows or len(rows) < 2:
        raise ValueError("CSV appears empty.")
    header = rows[0]
    data = rows[1:]
    return header, data


def _to_float_list(col: List[str]) -> np.ndarray:
    vals = []
    for s in col:
        try:
            vals.append(float(s))
        except Exception:
            vals.append(np.nan)
    return np.array(vals, dtype=float)


def _extract_columns(header: List[str], data: List[List[str]]) -> Tuple[np.ndarray, np.ndarray, dict]:
    
    # normalize header
    h = [c.strip() for c in header]
    hl = [c.lower() for c in h]

    # locate indices
    colmap = {name: None for name in ["theta", "phi", "angle", "s11", "pol", "s33", "s34"]}
    for i, name in enumerate(hl):
        if name in colmap:
            colmap[name] = i

    # build column arrays
    cols = {}
    for key, idx in colmap.items():
        if idx is not None:
            cols[key] = _to_float_list([row[idx] if idx < len(row) else "" for row in data])

    # theta/phi values
    if colmap["theta"] is not None:
        theta = cols["theta"]
    elif colmap["angle"] is not None:
        theta = cols["angle"]
    else:
        raise ValueError("CSV must contain 'Theta' or 'Angle' column.")

    if colmap["phi"] is not None:
        phi = cols["phi"]
    else:
        phi = np.zeros_like(theta)

    # collect metrics data
    metrics = {}
    for mname in ["s11", "pol", "s33", "s34"]:
        if mname in cols:
            metrics[mname.upper()] = cols[mname]

    return theta, phi, metrics


# Spherical->Cartesian conversion
def _sph_to_cart(theta_deg: np.ndarray, phi_deg: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """r=1 conversion."""
    th = np.radians(theta_deg)
    ph = np.radians(phi_deg)
    x = np.sin(th) * np.cos(ph) 
    y = np.sin(th) * np.sin(ph)
    z = np.cos(th)
    return x, y, z


# Plotting 
def _log_norm(values: np.ndarray, label: str) -> LogNorm:
    positive = values[np.isfinite(values) & (values > 0)]
    if positive.size == 0:
        raise ValueError(f"Log color scale requires positive {label} values.")
    vmin = float(np.min(positive))
    vmax = float(np.max(positive))
    if math.isclose(vmin, vmax):
        vmin /= 10.0
        vmax *= 10.0
    return LogNorm(vmin=vmin, vmax=vmax)


def _do_scatter(
    ax,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    cvals: np.ndarray,
    label: str,
    norm=None,
) -> None:
    fig = ax.figure
    if not hasattr(ax, "name") or ax.name != "3d":
        fig.clear()
        ax = fig.add_subplot(111, projection="3d")

    sc = ax.scatter(x, y, z, c=cvals, norm=norm)
    fig.colorbar(sc, ax=ax, label=label)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("z")
    ax.set_title(f"3D scatter colored by {label}")


def plot_csv(ax, csv_path: str) -> None:
    metric = get_metric()
    header, data = _read_csv(csv_path)
    theta, phi, metrics = _extract_columns(header, data)

    label = metric
    cvals = metrics.get(metric.upper())
    if cvals is None:
        if metrics:
            label, cvals = next(iter(metrics.items()))
        else:
            raise ValueError("No recognized metric columns found.")

    # Spherical to Cartesian 
    x, y, z = _sph_to_cart(theta, phi)

    # Error control
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(cvals)
    norm = None
    color_label = label
    if get_color_scale() == "log":
        mask &= cvals > 0
        norm = _log_norm(cvals[mask], label)
        color_label = f"{label} (log scale)"
    if not np.any(mask):
        raise ValueError("No finite data after parsing.")
    _do_scatter(ax, x[mask], y[mask], z[mask], cvals[mask], color_label, norm=norm)

# CLI for quick testing 
def _cli():
    import argparse
    p = argparse.ArgumentParser(description="3D scatter from Mie CSV (Theta/Phi -> Cartesian; color by metric).")
    p.add_argument("csv", help="Path to CSV exported by mieprog.")
    p.add_argument("--metric", choices=["S11", "Pol", "S33", "S34"], default=get_metric(),
                   help="Metric for color. Default: %(default)s")
    p.add_argument("--color-scale", choices=["linear", "log"], default=get_color_scale(),
                   help="Color scale. Default: %(default)s")
    p.add_argument("--sample", type=float, default=1.0, help="Downsample rate (0 < rate <= 1). Default: %(default)s")
    args = p.parse_args()

    set_metric(args.metric)
    set_color_scale(args.color_scale)
    header, data = _read_csv(args.csv)
    theta, phi, metrics = _extract_columns(header, data)

    cvals = metrics.get(args.metric.upper())
    label = args.metric if cvals is not None else None
    if cvals is None:
        if metrics:
            label, cvals = next(iter(metrics.items()))
        else:
            raise SystemExit("No recognized metric columns found.")

    n = len(theta)
    if args.sample < 1.0 and args.sample > 0:
        import numpy as _np
        k = max(1, int(n * args.sample))
        idx = _np.random.choice(n, size=k, replace=False)
        theta, phi, cvals = theta[idx], phi[idx], cvals[idx]

    x, y, z = _sph_to_cart(theta, phi)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(cvals)
    norm = None
    color_label = label
    if get_color_scale() == "log":
        mask &= cvals > 0
        norm = _log_norm(cvals[mask], label)
        color_label = f"{label} (log scale)"
    x, y, z, cvals = x[mask], y[mask], z[mask], cvals[mask]

    # Plot
    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111, projection="3d")
    sc = ax.scatter(x, y, z, c=cvals, norm=norm)
    fig.colorbar(sc, ax=ax, label=color_label)
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
    ax.set_title(f"3D scatter colored by {color_label}")
    plt.show()


if __name__ == "__main__":
    _cli()
