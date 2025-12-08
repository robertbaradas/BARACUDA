from __future__ import annotations

import numpy as np


def compute_rsi14(close: np.ndarray) -> np.ndarray:
    """Compute 14-period RSI for a closing price series.

    Args:
        close: NumPy array of closing prices

    Returns:
        NumPy array of RSI values (NaN for insufficient data points)
    """
    n = close.size
    rsi = np.full(n, np.nan, dtype=np.float32)
    if n < 15:
        return rsi
    delta = np.diff(close)
    gain = np.maximum(delta, 0.0)
    loss = np.maximum(-delta, 0.0)
    avgG = gain[:14].mean() if gain[:14].size else 0.0
    avgL = loss[:14].mean() if loss[:14].size else 0.0
    if avgL == 0 and avgG == 0:
        rsi[14] = 50.0
    elif avgL == 0:
        rsi[14] = 100.0
    elif avgG == 0:
        rsi[14] = 0.0
    else:
        rs = avgG / avgL
        rsi[14] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(15, n):
        g = gain[i - 1] if i - 1 < gain.size else 0.0
        l = loss[i - 1] if i - 1 < loss.size else 0.0
        avgG = (avgG * 13.0 + g) / 14.0
        avgL = (avgL * 13.0 + l) / 14.0
        if avgL == 0 and avgG == 0:
            rsi[i] = 50.0
        elif avgL == 0:
            rsi[i] = 100.0
        elif avgG == 0:
            rsi[i] = 0.0
        else:
            rs = avgG / avgL
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi
