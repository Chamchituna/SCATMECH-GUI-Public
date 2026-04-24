from __future__ import annotations

import math
import re
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.ticker import AutoMinorLocator, LogLocator, MultipleLocator


PUBLICATION_CMAP = LinearSegmentedColormap.from_list(
    "publication_yellow_red",
    [
        "#440154",
        "#414487",
        "#2a788e",
        "#22a884",
        "#7ad151",
        "#fde725",
        "#f46d43",
        "#b2182b",
    ],
    N=256,
)


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

    width = max(len(row) for row in rows)
    table = np.full((len(rows), width), np.nan, dtype=float)
    for idx, row in enumerate(rows):
        table[idx, : len(row)] = row
    return table


def _edges(vals: np.ndarray, low: float | None = None, high: float | None = None) -> np.ndarray:
    vals = np.asarray(vals, dtype=float)
    if vals.size == 1:
        step = 1.0
        out = np.array([vals[0] - step / 2, vals[0] + step / 2], dtype=float)
    else:
        mids = (vals[:-1] + vals[1:]) / 2
        first = vals[0] - (mids[0] - vals[0])
        last = vals[-1] + (vals[-1] - mids[-1])
        out = np.concatenate(([first], mids, [last]))
    if low is not None:
        out[0] = low
    if high is not None:
        out[-1] = high
    return out


def _style_polar(ax) -> None:
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 90)
    ax.set_yticks([15, 30, 45, 60, 75, 90])
    ax.set_yticklabels(["15", "30", "45", "60", "75", "90"])
    ax.set_rlabel_position(22.5)
    ax.grid(color="#b5b5b5", linewidth=0.45, alpha=0.75)
    ax.spines["polar"].set_linewidth(0.7)


def _select_polar_columns(data: np.ndarray) -> tuple[int, int, int] | None:
    if data.ndim != 2 or data.shape[1] < 3:
        return None

    theta_idx = 0
    phi_idx = 1
    value_idx = 6 if data.shape[1] >= 7 else data.shape[1] - 1

    theta = data[:, theta_idx]
    phi = data[:, phi_idx]
    values = data[:, value_idx]

    mask = np.isfinite(theta) & np.isfinite(phi) & np.isfinite(values)
    if mask.sum() < 4:
        return None

    theta = theta[mask]
    phi = phi[mask]
    theta_unique = np.unique(theta)
    phi_unique = np.unique(phi)
    if theta_unique.size < 2 or phi_unique.size < 2:
        return None
    expected_points = theta_unique.size * phi_unique.size
    if expected_points < 4:
        return None
    covered_points = len({(float(t), float(p)) for t, p in zip(theta, phi)})
    if covered_points / expected_points < 0.9:
        return None
    if np.nanmin(theta_unique) < -1e-6 or np.nanmax(theta_unique) > 90.0 + 1e-6:
        return None
    if np.nanmin(phi_unique) < -1e-6 or np.nanmax(phi_unique) > 360.0 + 1e-6:
        return None

    return theta_idx, phi_idx, value_idx


def _polar_grid(data: np.ndarray, theta_idx: int, phi_idx: int, value_idx: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    theta_vals = np.unique(data[:, theta_idx][np.isfinite(data[:, theta_idx])])
    phi_vals = np.unique(data[:, phi_idx][np.isfinite(data[:, phi_idx])])
    grid = np.full((theta_vals.size, phi_vals.size), np.nan, dtype=float)
    theta_index = {float(value): idx for idx, value in enumerate(theta_vals)}
    phi_index = {float(value): idx for idx, value in enumerate(phi_vals)}

    for row in data:
        theta = row[theta_idx]
        phi = row[phi_idx]
        value = row[value_idx]
        if not (math.isfinite(theta) and math.isfinite(phi) and math.isfinite(value)):
            continue
        grid[theta_index[float(theta)], phi_index[float(phi)]] = value

    return theta_vals, phi_vals, grid


def _plot_polar_map(ax, data: np.ndarray, *, value_idx: int, title: str | None = None) -> None:
    fig = ax.figure
    fig.clear()
    polar_ax = fig.add_subplot(111, projection="polar")

    theta_vals, phi_vals, values = _polar_grid(data, 0, 1, value_idx)
    values = np.where(values > 0, values, np.nan)
    positive = values[np.isfinite(values)]
    if positive.size == 0:
        raise ValueError("Polar BRDF view requires positive BRDF values.")

    vmin = float(np.nanmin(positive))
    vmax = float(np.nanmax(positive))
    if math.isclose(vmin, vmax):
        vmin /= 10.0
        vmax *= 10.0
    else:
        vmin = 10 ** math.floor(math.log10(vmin))
        vmax = 10 ** math.ceil(math.log10(vmax))
    norm = LogNorm(vmin=vmin, vmax=vmax)

    theta_edges = _edges(theta_vals, low=0.0, high=90.0)
    phi_edges = _edges(phi_vals, low=0.0, high=360.0)

    mesh = polar_ax.pcolormesh(
        np.deg2rad(phi_edges),
        theta_edges,
        values,
        cmap=PUBLICATION_CMAP,
        norm=norm,
        shading="auto",
    )
    _style_polar(polar_ax)
    polar_ax.set_title(title or "BRDF Polar Map", pad=8)

    cbar = fig.colorbar(mesh, ax=polar_ax, shrink=0.82, pad=0.08)
    cbar.set_label(r"BRDF (sr$^{-1}$)")


def _finite_bounds(col: np.ndarray) -> tuple[float, float] | None:
    finite = col[np.isfinite(col)]
    if finite.size < 2:
        return None
    return float(np.min(finite)), float(np.max(finite))


def _angle_score(
    col: np.ndarray,
    *,
    preferred_span: tuple[float, float] | None = None,
    index_bias: float = 0.0,
) -> float:
    finite = col[np.isfinite(col)]
    if finite.size < 3:
        return -float("inf")

    lo = float(np.min(finite))
    hi = float(np.max(finite))
    spread = hi - lo
    if spread <= 1e-6:
        return -float("inf")

    if lo < -360.0 - 1e-6 or hi > 360.0 + 1e-6:
        return -float("inf")

    diffs = np.diff(finite)
    if diffs.size:
        inc = float(np.mean(diffs >= -1e-8))
        dec = float(np.mean(diffs <= 1e-8))
        monotonic = max(inc, dec)
    else:
        monotonic = 0.0

    score = 1.6 * monotonic + min(spread / 180.0, 1.0) + index_bias
    if preferred_span is not None:
        target_lo, target_hi = preferred_span
        denom = max(target_hi - target_lo, 1e-6)
        closeness = 1.0 - ((abs(lo - target_lo) + abs(hi - target_hi)) / (2.0 * denom))
        score += max(closeness, -2.0)
    return score


def _select_line_axes(
    data: np.ndarray,
    *,
    x_col: Optional[int],
    y_col: Optional[int],
    meta: Optional[dict],
) -> tuple[int, int, str, tuple[float, float] | None]:
    ncols = data.shape[1]

    if x_col is not None and 0 <= x_col < ncols:
        x_idx = int(x_col)
    else:
        scatter = (meta or {}).get("scatter") or {}
        scatter_start = scatter.get("scatter_start")
        scatter_end = scatter.get("scatter_end")
        azimuth_start = scatter.get("azimuth_start")
        azimuth_end = scatter.get("azimuth_end")

        scatter_span = None
        if scatter_start is not None and scatter_end is not None and not math.isclose(
            float(scatter_start), float(scatter_end), abs_tol=1e-6
        ):
            scatter_span = (
                float(min(scatter_start, scatter_end)),
                float(max(scatter_start, scatter_end)),
            )

        azimuth_span = None
        if azimuth_start is not None and azimuth_end is not None and not math.isclose(
            float(azimuth_start), float(azimuth_end), abs_tol=1e-6
        ):
            azimuth_span = (
                float(min(azimuth_start, azimuth_end)),
                float(max(azimuth_start, azimuth_end)),
            )

        candidates: List[tuple[float, int, str, tuple[float, float] | None]] = []
        preferred_kinds: List[tuple[str, tuple[float, float] | None, int]] = []
        if scatter_span is not None:
            preferred_kinds.append(("scatter", scatter_span, 0))
        if azimuth_span is not None:
            preferred_kinds.append(("azimuth", azimuth_span, 1))

        index_biases = {0: 0.35, 1: 0.3, 2: 0.2}
        indices = list(range(min(ncols, 3)))
        if not indices:
            raise ValueError("No numeric columns available for plotting.")

        for kind, span, preferred_idx in preferred_kinds:
            for idx in indices:
                score = _angle_score(
                    data[:, idx],
                    preferred_span=span,
                    index_bias=index_biases.get(idx, 0.0) + (0.45 if idx == preferred_idx else 0.0),
                )
                if math.isfinite(score):
                    candidates.append((score, idx, kind, span))

        if not candidates:
            fallback_labels = {0: "scatter", 1: "azimuth", 2: "signed_scatter"}
            for idx in indices:
                score = _angle_score(data[:, idx], index_bias=index_biases.get(idx, 0.0))
                if math.isfinite(score):
                    candidates.append((score, idx, fallback_labels.get(idx, "angle"), None))

        if not candidates:
            fallback = 0 if ncols > 0 else -1
            if fallback < 0:
                raise ValueError("No numeric columns available for plotting.")
            x_idx = fallback
            x_kind = "angle"
            x_hint = None
        else:
            _, x_idx, x_kind, x_hint = max(candidates, key=lambda item: item[0])

    if y_col is not None and 0 <= y_col < ncols:
        y_idx = int(y_col)
    elif ncols >= 7:
        y_idx = 6
    else:
        y_idx = ncols - 1
        if y_idx == x_idx and y_idx > 0:
            y_idx -= 1

    if y_idx == x_idx:
        raise ValueError("Selected BRDF value column matches X column.")

    if x_col is not None:
        if x_idx == 0:
            x_kind = "scatter"
        elif x_idx == 1:
            x_kind = "azimuth"
        elif x_idx == 2:
            x_kind = "signed_scatter"
        else:
            x_kind = "angle"
        x_hint = None

    if x_kind == "scatter":
        x_label = "Scatter Angle (degrees)"
    elif x_kind == "azimuth":
        x_label = "Azimuth (degrees)"
    elif x_kind == "signed_scatter":
        x_label = "Signed Scatter Angle (degrees)"
    else:
        x_label = "Angle (degrees)"

    return x_idx, y_idx, x_label, x_hint


def _plot_line_fallback(
    ax,
    data: np.ndarray,
    *,
    x_col: Optional[int],
    y_col: Optional[int],
    semilogy: bool,
    x_span_hint: Tuple[float, float],
    label: Optional[str],
    meta: Optional[dict],
) -> None:
    x_idx, y_idx, x_label, meta_hint = _select_line_axes(
        data,
        x_col=x_col,
        y_col=y_col,
        meta=meta,
    )

    xs = data[:, x_idx]
    ys = data[:, y_idx]
    mask = np.isfinite(xs) & np.isfinite(ys)
    if mask.sum() < 2:
        raise ValueError("No finite BRDF data available for plotting.")

    xs_vals = xs[mask]
    ys_vals = ys[mask]
    order = np.argsort(xs_vals)
    xs_vals = xs_vals[order]
    ys_vals = ys_vals[order]

    positive_fraction = float(np.mean(ys_vals > 0))
    use_semilogy = bool(semilogy and positive_fraction >= 0.7)

    ax.cla()
    ax.set_yscale("log" if use_semilogy else "linear")

    if use_semilogy:
        ys_plot = ys_vals.astype(float).copy()
        positive_mask = ys_plot > 0
        ys_plot[~positive_mask] = np.nan
        ax.plot(xs_vals, ys_plot, linewidth=1.5, label=label)
        positive_values = ys_plot[np.isfinite(ys_plot)]
    else:
        ax.plot(xs_vals, ys_vals, linewidth=1.5, label=label)
        positive_values = np.array([], dtype=float)

    xmin = float(np.min(xs_vals))
    xmax = float(np.max(xs_vals))

    ax.set_xlabel(x_label)
    ax.set_ylabel(r"BRDF (sr$^{-1}$)")

    lo, hi = meta_hint if meta_hint is not None else x_span_hint
    if lo < hi and (xmin >= lo - 5.0) and (xmax <= hi + 5.0):
        ax.set_xlim(lo, hi)
        ax.xaxis.set_major_locator(MultipleLocator(30))
        ax.xaxis.set_minor_locator(AutoMinorLocator(3))
    else:
        ax.set_xlim(xmin, xmax)
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))

    if use_semilogy:
        ax.yaxis.set_major_locator(LogLocator(base=10.0, numticks=10))
        ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=(0.2, 0.4, 0.6, 0.8), numticks=12))
        if positive_values.size:
            ymin = float(np.min(positive_values) * 0.8)
            ymax = float(np.max(positive_values) * 1.2)
            if np.isfinite(ymin) and np.isfinite(ymax) and ymin > 0 and ymax > 0:
                ax.set_ylim(ymin, ymax)
    else:
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))

    if label:
        ax.legend(loc="best")

    ax.grid(True, which="major", linewidth=0.8, alpha=0.6)
    ax.grid(True, which="minor", linewidth=0.4, alpha=0.35)
    ax.set_axisbelow(True)
    ax.figure.tight_layout()


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
    """Render a BRDF result as a publication-style polar map when possible."""

    data = _load_numeric_table(csv_path)
    polar_columns = _select_polar_columns(data)
    if polar_columns is not None:
        _theta_idx, _phi_idx, value_idx = polar_columns
        title = "BRDF Polar Map"
        if meta and meta.get("model_name"):
            title = f"{meta['model_name']} BRDF"
        _plot_polar_map(ax, data, value_idx=value_idx, title=title)
        return

    _plot_line_fallback(
        ax,
        data,
        x_col=x_col,
        y_col=y_col,
        semilogy=semilogy,
        x_span_hint=x_span_hint,
        label=label,
        meta=meta,
    )
