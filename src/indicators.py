from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rma(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(alpha=1 / n, adjust=False).mean()


def macd(series: pd.Series, fast: int, slow: int, signal: int):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return rma(tr, n).replace(0, np.nan)


def adx_wilder(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    atr = atr_wilder(high, low, close, n).replace(0, np.nan)
    plus_di = 100 * (rma(pd.Series(plus_dm, index=high.index), n) / atr)
    minus_di = 100 * (rma(pd.Series(minus_dm, index=high.index), n) / atr)

    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    return rma(dx, n)


def donchian(high: pd.Series, low: pd.Series, n: int):
    return high.rolling(n).max(), low.rolling(n).min()


def rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    close = close.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = rma(gain, n)
    avg_loss = rma(loss, n)
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(avg_gain != 0, 0.0)
    return rsi


def return_nd(close: pd.Series, n: int) -> float:
    if close is None or close.empty or len(close) < (n + 1):
        return np.nan
    base = close.iloc[-(n + 1)]
    last = close.iloc[-1]
    if pd.isna(base) or base == 0 or pd.isna(last):
        return np.nan
    return float(last / base - 1.0)


def ohlcv_to_weekly(df_d: pd.DataFrame) -> pd.DataFrame:
    weekly = pd.DataFrame(
        {
            "open": df_d["open"].resample("W-FRI").first(),
            "high": df_d["high"].resample("W-FRI").max(),
            "low": df_d["low"].resample("W-FRI").min(),
            "close": df_d["close"].resample("W-FRI").last(),
            "vol": df_d["vol"].resample("W-FRI").sum(min_count=1),
        }
    ).dropna(subset=["close"])
    if not weekly.empty:
        last_session_date = df_d.index.max().normalize()
        last_week_label = weekly.index.max().normalize()
        if last_session_date < last_week_label:
            weekly = weekly.iloc[:-1]
    return weekly
