#!/usr/bin/env python3
"""
Comparação entre uma captura V-I de referência e uma captura atual.

Duas estratégias são usadas, conforme a forma da curva:

1. **Interpolação em X** (curvas monotônicas em X): as duas curvas são
   interpoladas em uma grade comum dentro da faixa X de sobreposição e o erro
   é calculado em unidades físicas do eixo Y.
2. **Distância geométrica** (curvas não monotônicas, laços V-I): as curvas são
   normalizadas pelos spans da referência e comparadas por distância
   simétrica ao vizinho mais próximo (estilo Hausdorff). Isso compara a forma
   sem exigir que X seja uma função nem que a ordem das amostras coincida.

O veredito usa o erro RMS normalizado (NRMSE) em relação ao span da
referência, o desvio máximo normalizado e a correlação. O desvio máximo evita
que um defeito localizado (pico estreito) seja mascarado por um RMS baixo.
A comparação não altera, ordena ou reamostra os dados persistidos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    from scipy.spatial import cKDTree
except Exception:  # pragma: no cover - scipy é dependência do projeto
    cKDTree = None

_EPS = 1e-12


@dataclass(frozen=True)
class ComparisonResult:
    method: str
    verdict: str
    is_anomaly: bool
    n_reference: int
    n_live: int
    n_common: int
    nrmse: float
    max_error: float
    max_error_normalized: float
    p95_error: float
    correlation: float | None
    x_overlap: tuple[float, float] | None
    y_span_reference: float
    tolerance: float
    message: str


def _clean_xy(x, y) -> tuple[np.ndarray, np.ndarray]:
    x_arr = np.asarray(x, dtype=float).ravel()
    y_arr = np.asarray(y, dtype=float).ravel()
    if x_arr.size != y_arr.size:
        raise ValueError("x and y must have the same length")
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    return x_arr[mask], y_arr[mask]


def _is_monotonic(x: np.ndarray) -> bool:
    if x.size < 2:
        return False
    diff = np.diff(x)
    return bool(np.all(diff >= 0) or np.all(diff <= 0))


def _collapse_duplicates(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ordena por X e agrupa X repetidos pela média de Y."""
    order = np.argsort(x, kind="stable")
    xs = x[order]
    ys = y[order]
    unique_x, start, counts = np.unique(xs, return_index=True, return_counts=True)
    sums = np.add.reduceat(ys, start)
    return unique_x, sums / counts


def _corr(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size < 2 or b.size < 2:
        return None
    a_std = float(np.std(a))
    b_std = float(np.std(b))
    if a_std <= _EPS and b_std <= _EPS:
        return 1.0 if np.allclose(a, b) else 0.0
    if a_std <= _EPS or b_std <= _EPS:
        return 0.0
    value = float(np.corrcoef(a, b)[0, 1])
    return value if np.isfinite(value) else None


def _resample_arclength(
    x: np.ndarray, y: np.ndarray, cx: float, cy: float, sx: float, sy: float, n: int
) -> tuple[np.ndarray, np.ndarray]:
    xn = (x - cx) / sx
    yn = (y - cy) / sy
    if xn.size < 2:
        return xn, yn
    step = np.hypot(np.diff(xn), np.diff(yn))
    s = np.concatenate(([0.0], np.cumsum(step)))
    if s[-1] <= _EPS:
        return np.full(n, xn[0]), np.full(n, yn[0])
    u = np.linspace(0.0, s[-1], n)
    return np.interp(u, s, xn), np.interp(u, s, yn)


def _nearest_distances(points: np.ndarray, other: np.ndarray) -> np.ndarray:
    if cKDTree is not None:
        return cKDTree(other).query(points, k=1)[0]
    # Fallback sem scipy: distância exata em blocos (evita matriz NxN).
    out = np.empty(points.shape[0], dtype=float)
    for start in range(0, points.shape[0], 256):
        block = points[start:start + 256]
        d = np.hypot(
            block[:, None, 0] - other[None, :, 0],
            block[:, None, 1] - other[None, :, 1],
        )
        out[start:start + 256] = d.min(axis=1)
    return out


def _verdict(
    nrmse: float,
    max_normalized: float,
    correlation: float | None,
    tolerance: float,
) -> str:
    if (
        nrmse <= tolerance
        and max_normalized <= 2.0 * tolerance
        and (correlation is None or correlation >= 0.90)
    ):
        return "MATCH"
    if nrmse <= 2.0 * tolerance and max_normalized <= 4.0 * tolerance:
        return "WARNING"
    return "DEVIATION"


def compare_curves(
    reference_x,
    reference_y,
    live_x,
    live_y,
    tolerance: float = 0.05,
) -> ComparisonResult:
    """Compara duas curvas e devolve métricas e um veredito.

    ``tolerance`` é o NRMSE máximo (fração do span Y da referência) para
    considerar a captura compatível. O padrão de 5% é um ponto de partida;
    ajuste conforme o ruído do instrumento e a tolerância do componente.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    rx, ry = _clean_xy(reference_x, reference_y)
    lx, ly = _clean_xy(live_x, live_y)
    if rx.size < 2 or lx.size < 2:
        raise ValueError("Both curves need at least two valid points")

    ry_span = float(np.ptp(ry))
    if ry_span <= _EPS:
        ry_span = max(float(np.ptp(ly)), 1.0)

    x_overlap = (max(float(rx.min()), float(lx.min())),
                 min(float(rx.max()), float(lx.max())))

    common_count = 0
    p95 = float("nan")
    max_normalized = float("nan")
    correlation: float | None = None

    if _is_monotonic(rx) and _is_monotonic(lx) and x_overlap[1] > x_overlap[0]:
        ref_x, ref_y = _collapse_duplicates(rx, ry)
        live_xs, live_ys = _collapse_duplicates(lx, ly)
        inside_ref = (ref_x >= x_overlap[0]) & (ref_x <= x_overlap[1])
        if int(inside_ref.sum()) >= 2:
            n_grid = int(min(4096, max(ref_x.size, live_xs.size)))
            grid = np.linspace(x_overlap[0], x_overlap[1], max(n_grid, 32))
            ref_i = np.interp(grid, ref_x, ref_y)
            live_i = np.interp(grid, live_xs, live_ys)
            diff = live_i - ref_i
            rmse = float(np.sqrt(np.mean(diff ** 2)))
            max_error = float(np.max(np.abs(diff)))
            p95 = float(np.quantile(np.abs(diff), 0.95))
            correlation = _corr(ref_i, live_i)
            common_count = int(grid.size)
            method = "interpolation"
            nrmse = rmse / ry_span
            max_normalized = max_error / ry_span
            message = (
                f"Interpolated {common_count} points over "
                f"X={x_overlap[0]:.6g}..{x_overlap[1]:.6g}."
            )
        else:
            method = None
    else:
        method = None

    if method is None:
        # Distância geométrica simétrica em coordenadas normalizadas.
        ref_cx = float((rx.min() + rx.max()) / 2.0)
        ref_cy = float((ry.min() + ry.max()) / 2.0)
        sx = float(np.ptp(rx))
        sy = ry_span
        if sx <= _EPS:
            sx = max(float(np.ptp(lx)), 1.0)
        if sy <= _EPS:
            sy = max(float(np.ptp(ly)), 1.0)

        ref_n = np.column_stack(((rx - ref_cx) / sx, (ry - ref_cy) / sy))
        live_n = np.column_stack(((lx - ref_cx) / sx, (ly - ref_cy) / sy))
        d_live = _nearest_distances(live_n, ref_n)
        d_ref = _nearest_distances(ref_n, live_n)
        distances = np.concatenate((d_live, d_ref))
        nrmse = float(np.sqrt(np.mean(distances ** 2)))
        max_error = float(np.max(distances))
        max_normalized = max_error
        p95 = float(np.quantile(distances, 0.95))
        common_count = int(distances.size)

        # Correlação por comprimento de arco, testando os dois sentidos.
        n_resample = int(min(2048, max(rx.size, lx.size)))
        ar_x, ar_y = _resample_arclength(
            rx, ry, ref_cx, ref_cy, sx, sy, n_resample
        )
        al_x, al_y = _resample_arclength(
            lx, ly, ref_cx, ref_cy, sx, sy, n_resample
        )
        corr_fwd = _corr(
            np.concatenate((ar_x, ar_y)), np.concatenate((al_x, al_y))
        )
        corr_rev = _corr(
            np.concatenate((ar_x, ar_y)),
            np.concatenate((al_x[::-1], al_y[::-1])),
        )
        candidates = [v for v in (corr_fwd, corr_rev) if v is not None]
        correlation = max(candidates) if candidates else None
        method = "geometric"
        message = (
            "Non-monotonic curve: symmetric nearest-neighbor distance in "
            "normalized coordinates."
        )

    verdict = _verdict(nrmse, max_normalized, correlation, tolerance)
    is_anomaly = verdict != "MATCH"
    return ComparisonResult(
        method=method,
        verdict=verdict,
        is_anomaly=is_anomaly,
        n_reference=int(rx.size),
        n_live=int(lx.size),
        n_common=common_count,
        nrmse=float(nrmse),
        max_error=float(max_error),
        max_error_normalized=float(max_normalized),
        p95_error=float(p95),
        correlation=correlation,
        x_overlap=x_overlap if x_overlap[1] > x_overlap[0] else None,
        y_span_reference=ry_span,
        tolerance=float(tolerance),
        message=message,
    )
