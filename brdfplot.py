from __future__ import annotations
import math
import re
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np
from matplotlib.ticker import LogLocator, MultipleLocator, AutoMinorLocator

def _load_numeric_table(csv_path: str) -> np.ndarray:

    rows: List[List[float]] = []
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {csv_path}")
        
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tokens = [tok for tok in re.split(r"[\s,]+", line) if tok]
            if not tokens:
                continue
            row: List[float] = []
            for tok in tokens:
                cleaned = tok.replace("D", "E").replace("d", "E")
                try:
                    row.append(float(cleaned))
                except ValueError:
                    row = []
                    break
            if not row:
                continue
            rows.append(row)

    if not rows:
        raise ValueError("No numeric rows detected in BRDF output.")

    width = max(len(r) for r in rows)
    table = np.full((len(rows), width), np.nan, dtype=float)
    for idx, row in enumerate(rows):
        table[idx, : len(row)] = row
    return table


def plot_csv(
    ax,
    csv_path: str,
    *,
    x_col: Optional[int] = None,
    y_col: Optional[int] = None,
    semilogy: bool = True,
    x_span_hint: Tuple[float, float] = (-90.0, 90.0),
    label: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    """Render BRDF vs scattering angle on the provided Matplotlib axis."""

    data = _load_numeric_table(csv_path)
    ncols = data.shape[1]

    header_tokens = []
    scatter_meta = {}
    if meta:
        header_tokens = meta.get("header_tokens") or []
        scatter_meta = meta.get("scatter") or {}
        start_hint = scatter_meta.get("scatter_start")
        end_hint = scatter_meta.get("scatter_end")
        if start_hint is not None and end_hint is not None:
            lo_hint = float(min(start_hint, end_hint))
            hi_hint = float(max(start_hint, end_hint))
            if math.isfinite(lo_hint) and math.isfinite(hi_hint):
                x_span_hint = (lo_hint, hi_hint)

    header_lower: List[str] = []
    if header_tokens:
        header_lower = [str(tok).strip().lower() for tok in header_tokens]
    while len(header_lower) < ncols:
        header_lower.append("")

    def _select_x_column() -> int:
        if x_col is not None and 0 <= x_col < ncols:
            return int(x_col)

        expected_start = scatter_meta.get("scatter_start") if scatter_meta else None
        expected_end = scatter_meta.get("scatter_end") if scatter_meta else None
        exp_min = exp_max = None
        if expected_start is not None and expected_end is not None:
            exp_min = min(expected_start, expected_end)
            exp_max = max(expected_start, expected_end)

        best_idx = None
        best_score = -float("inf")
        for idx in range(ncols):
            col = data[:, idx]
            finite = col[np.isfinite(col)]
            if finite.size < 3:
                continue
            spread = float(np.max(finite) - np.min(finite))
            if spread < 1e-6:
                continue

            diffs = np.diff(finite)
            if diffs.size:
                inc = np.mean(diffs >= -1e-8)
                dec = np.mean(diffs <= 1e-8)
                monotonic = max(inc, dec)
            else:
                monotonic = 0.0

            header_score = 0.0
            name = header_lower[idx]
            if name:
                if any(key in name for key in ("theta_r", "theta_s", "thetas", "scatter", "scatt", "view")):
                    header_score += 2.5
                if "angle" in name:
                    header_score += 0.5
                if "phi" in name or "azimuth" in name:
                    header_score -= 1.0

            range_score = min(spread / 180.0, 1.0)
            closeness = 0.0
            if exp_min is not None and exp_max is not None and exp_max > exp_min:
                lo_val = float(np.min(finite))
                hi_val = float(np.max(finite))
                denom = max(exp_max - exp_min, 1e-6)
                closeness = 1.0 - ((abs(lo_val - exp_min) + abs(hi_val - exp_max)) / (2.0 * denom))

            score = 1.8 * monotonic + range_score + header_score + closeness
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is None:
            fallback = 2 if ncols > 2 else ncols - 1
            best_idx = max(0, fallback)
        return best_idx

    def _select_measure_columns(x_idx: int) -> List[int]:
        if y_col is not None and 0 <= y_col < ncols:
            return [int(y_col)]

        geometry_keys = (
            "theta_i",
            "thetai",
            "incident",
            "azimuth",
            "phi",
            "rotation",
            "lambda",
            "wavelength",
            "index",
            "type",
        )

        x_vals = data[:, x_idx]
        mask_x = np.isfinite(x_vals)
        candidates: List[Tuple[int, float]] = []
        for idx in range(ncols):
            if idx == x_idx:
                continue
            col = data[:, idx]
            mask = mask_x & np.isfinite(col)
            if mask.sum() < 2:
                continue
            vals = col[mask]
            if np.allclose(vals, x_vals[mask], rtol=1e-5, atol=1e-4):
                continue
            spread = float(np.max(vals) - np.min(vals))
            if spread < 1e-12:
                continue
            name = header_lower[idx]
            if name and any(key in name for key in geometry_keys):
                continue
            candidates.append((idx, float(np.nanstd(vals))))

        if not candidates:
            fallback = ncols - 1
            if fallback == x_idx and fallback > 0:
                fallback -= 1
            if 0 <= fallback < ncols and fallback != x_idx:
                candidates.append((fallback, float(np.nanstd(data[:, fallback]))))

        candidates.sort(key=lambda item: item[1], reverse=True)
        return [idx for idx, _ in candidates]

    x_idx = _select_x_column()
    measure_indices = _select_measure_columns(x_idx)
    if not measure_indices:
        raise ValueError("No measurement columns available for plotting.")

    xs = data[:, x_idx]
    base_mask = np.isfinite(xs)

    valid_indices: List[int] = []
    positive_scores: List[float] = []
    for idx in measure_indices:
        col = data[:, idx]
        mask = base_mask & np.isfinite(col)
        if mask.sum() == 0:
            continue
        valid_indices.append(idx)
        positive_scores.append(float(np.mean(col[mask] > 0)))

    if not valid_indices:
        raise ValueError("No finite measurement data available for plotting.")
        
    use_semilogy = bool(semilogy and positive_scores and min(positive_scores) >= 0.7)

    header_names: List[str] = []
    if header_tokens:
        header_names = [str(tok).strip() for tok in header_tokens]
    while len(header_names) < ncols:
        header_names.append("")

    ax.cla()
    ax.set_yscale("log" if use_semilogy else "linear")

    xmin = math.inf
    xmax = -math.inf
    all_positive_values: List[float] = []

    for idx in valid_indices:
        col = data[:, idx]
        mask = base_mask & np.isfinite(col)
        xs_vals = xs[mask]
        ys_vals = col[mask]
        if xs_vals.size == 0:
            continue
        order = np.argsort(xs_vals)
        xs_vals = xs_vals[order]
        ys_vals = ys_vals[order]

        xmin = min(xmin, float(np.min(xs_vals)))
        xmax = max(xmax, float(np.max(xs_vals)))

        col_label = header_names[idx] if idx < len(header_names) else ""
        if label:
            if col_label:
                line_label = f"{label}: {col_label}"
            else:
                line_label = label
        else:
            line_label = col_label or f"C{idx + 1}"

        if use_semilogy:
            ys_plot = ys_vals.astype(float).copy()
            positives = ys_plot > 0
            ys_plot[~positives] = np.nan
            if positives.any():
                all_positive_values.extend(float(val) for val in ys_plot[positives] if math.isfinite(val))
            ax.plot(xs_vals, ys_plot, linewidth=1.4, label=line_label)
        else:
            ax.plot(xs_vals, ys_vals, linewidth=1.4, label=line_label)

    if not math.isfinite(xmin) or not math.isfinite(xmax):
        raise ValueError("Unable to determine X-axis bounds from data.")
        
    ax.set_xlabel(r"$\theta_r$ (degrees)")
    ax.set_ylabel(r"BRDF [sr$^{-1}$]")
  
    lo, hi = x_span_hint
    if lo >= hi:
        lo, hi = xmin, xmax
    if (xmin >= lo - 5.0) and (xmax <= hi + 5.0):
        ax.set_xlim(lo, hi)
        ax.xaxis.set_major_locator(MultipleLocator(30))
        ax.xaxis.set_minor_locator(AutoMinorLocator(3))
    else:
        ax.set_xlim(xmin, xmax)
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))

    if use_semilogy:
        ax.yaxis.set_major_locator(LogLocator(base=10.0, numticks=10))
        ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=(0.2, 0.4, 0.6, 0.8), numticks=12))
        positive_array = np.array(all_positive_values, dtype=float)
        positive_array = positive_array[np.isfinite(positive_array)]
        if positive_array.size:
            ymin = float(np.min(positive_array) * 0.8)
            ymax = float(np.max(positive_array) * 1.2)
            if np.isfinite(ymin) and np.isfinite(ymax) and ymin > 0 and ymax > 0:
                ax.set_ylim(ymin, ymax)
    else:
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))

    if len(valid_indices) > 1 or label:
        ax.legend(loc="best")

    ax.grid(True, which="major", linewidth=0.8, alpha=0.6)
    ax.grid(True, which="minor", linewidth=0.4, alpha=0.35)
    ax.set_axisbelow(True)

    ax.figure.tight_layout()