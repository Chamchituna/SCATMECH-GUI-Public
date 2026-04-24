import csv
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from matplotlib.ticker import AutoMinorLocator, MultipleLocator


_GREEK_LABELS: Dict[str, str] = {
    "alpha": r"$\alpha$",
    "beta": r"$\beta$",
}

_GREEK_COLORS: Dict[str, str] = {
    "alpha": "tab:orange",
    "beta": "tab:blue",
}


def _nice_step(value: float) -> float:
    """Return a human-friendly tick interval for a given numeric span."""
    if not np.isfinite(value) or value <= 0:
        return 1.0

    exponent = float(np.floor(np.log10(value)))
    fraction = float(value / (10 ** exponent))
    for candidate in (1.0, 2.0, 2.5, 5.0, 10.0):
        if fraction <= candidate:
            return float(candidate * (10 ** exponent))
    return float(10 ** (exponent + 1))


def _read_csv(csv_path: str) -> Tuple[List[str], List[List[str]]]:
    """Read a CSV file, returning the header row and subsequent data rows."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with open(path, newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.reader(handle) if any(cell.strip() for cell in row)]

    if not rows:
        raise ValueError(f"CSV appears empty: {csv_path}")

    header = rows[0]
    data = rows[1:] if len(rows) > 1 else []
    if not data:
        raise ValueError("CSV contains header but no data rows.")
    return header, data


def _column_by_hint(header: Sequence[str], hints: Iterable[str]) -> int:
    """Return the first column index whose lowercase header contains any hint."""
    lowered = [name.lower() for name in header]
    for hint in hints:
        hint_lower = hint.lower()
        for idx, candidate in enumerate(lowered):
            if hint_lower in candidate:
                return idx
    return -1


def _to_float(values: Sequence[str]) -> np.ndarray:
    """Convert an iterable of strings to a float numpy array, preserving NaN on failure."""
    parsed: List[float] = []
    for item in values:
        try:
            parsed.append(float(item))
        except Exception:
            parsed.append(float("nan"))
    return np.asarray(parsed, dtype=float)


def _series_type(raw_label: str, fallback_index: int, total_series: int) -> str:
    """Determine whether a column represents alpha/beta, returning a normalized key."""
    label = (raw_label or "").strip().lower()
    if "alpha" in label:
        return "alpha"
    if "beta" in label:
        return "beta"
    if not raw_label and total_series == 2:
        return "alpha" if fallback_index == 0 else "beta"
    return ""


def plot_csv(ax, csv_path: str) -> None:
    """Render the RCW output CSV onto the provided matplotlib axes."""
    header, data = _read_csv(csv_path)

    # Choose x-axis/order column
    order_idx = _column_by_hint(header, ["order", "m", "index"])
    if order_idx < 0:
        order_idx = 0

    x_vals = _to_float([row[order_idx] if order_idx < len(row) else "" for row in data])

    # Choose y columns by hint priority, then fall back to all except x
    hint_priority = [
        "alpha", "beta", "diff", "eff", "rs", "rp", "s11", "intensity", "power",
    ]
    y_indices: List[int] = []
    for hint in hint_priority:
        idx = _column_by_hint(header, [hint])
        if idx >= 0 and idx != order_idx and idx not in y_indices:
            y_indices.append(idx)
    if not y_indices:
        y_indices = [idx for idx in range(len(header)) if idx != order_idx]

    if not y_indices:
        raise ValueError("No value columns detected for plotting.")

    ax.cla()
    plotted_types: List[str] = []

    for series_pos, idx in enumerate(y_indices):
        series = _to_float([row[idx] if idx < len(row) else "" for row in data])
        mask = np.isfinite(x_vals) & np.isfinite(series)
        if not np.any(mask):
            continue

        raw_label = header[idx].strip()
        normalized_key = _series_type(raw_label, series_pos, len(y_indices))

        if normalized_key:
            label = _GREEK_LABELS.get(normalized_key, raw_label or f"col{idx + 1}")
        else:
            label = raw_label or f"col{idx + 1}"

        style = {"linewidth": 2.5}
        if normalized_key and normalized_key in _GREEK_COLORS:
            style["color"] = _GREEK_COLORS[normalized_key]

        ax.plot(x_vals[mask], series[mask], label=label, **style)

        if normalized_key:
            plotted_types.append(normalized_key)

    if not ax.lines:
        raise ValueError("Parsed CSV but found no plottable numeric data.")

    # Labels and ticks
    xlabel = header[order_idx].strip() or "Diffraction Order"
    normalized_xlabel = xlabel.lower()
    is_wavelength = ("lambda" in normalized_xlabel) or ("wave" in normalized_xlabel)

    ax.set_xlabel("Wavelength λ (μm)" if is_wavelength else xlabel)
    ax.set_ylabel("Value")

    finite_x = x_vals[np.isfinite(x_vals)]
    if is_wavelength and finite_x.size:
        span = float(finite_x.max() - float(finite_x.min()))
        step = _nice_step(span / 6.0) if span else 0.1
        ax.xaxis.set_major_locator(MultipleLocator(step))
        ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    else:
        ax.xaxis.set_major_locator(MultipleLocator(1))
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))

    ax.grid(True, which="major", linewidth=0.8, alpha=0.6)
    ax.grid(True, which="minor", linewidth=0.4, alpha=0.35)

    if ax.lines:
        ax.legend(loc="best", frameon=False)

    if {"alpha", "beta"}.issubset(set(plotted_types)):
        ax.set_title(r"$\alpha$ and $\beta$ vs Wavelength $\lambda$", fontsize=16, fontstyle="italic")
    else:
        ax.set_title("")

    ax.figure.tight_layout()
