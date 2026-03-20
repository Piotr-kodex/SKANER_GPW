from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

from .data_loader import build_zip_index, load_daily_from_zip, load_gpw_list_from_bytes, norm_ticker, open_zip_from_bytes
from .indicators import adx_wilder, atr_wilder, donchian, ema, macd, ohlcv_to_weekly, return_nd, rsi_wilder


@dataclass
class ScanArtifacts:
    df_rank: pd.DataFrame
    df_err: pd.DataFrame
    df_leaders: pd.DataFrame
    df_breakouts_watch: pd.DataFrame
    df_breakouts_strict: pd.DataFrame
    df_pullbacks: pd.DataFrame
    interactive_store: Dict[str, Any]
    audit_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def _to_float(x):
    try:
        if x is None:
            return np.nan
        if isinstance(x, (pd.Series, pd.Index)):
            x = x.iloc[-1] if len(x) else np.nan
        if pd.isna(x):
            return np.nan
        return float(x)
    except Exception:
        return np.nan


def find_last_swing_low(series: pd.Series, left: int = 2, right: int = 2):
    vals = series.astype(float).values
    idx = series.index
    if len(vals) < left + right + 1:
        return np.nan, None
    for i in range(len(vals) - right - 1, left - 1, -1):
        center = vals[i]
        if np.isnan(center):
            continue
        left_vals = vals[i - left:i]
        right_vals = vals[i + 1:i + 1 + right]
        if np.all(center <= left_vals) and np.all(center <= right_vals):
            return float(center), idx[i].date().isoformat()
    return np.nan, None


def find_last_swing_high(series: pd.Series, left: int = 2, right: int = 2):
    vals = series.astype(float).values
    idx = series.index
    if len(vals) < left + right + 1:
        return np.nan, None
    for i in range(len(vals) - right - 1, left - 1, -1):
        center = vals[i]
        if np.isnan(center):
            continue
        left_vals = vals[i - left:i]
        right_vals = vals[i + 1:i + 1 + right]
        if np.all(center >= left_vals) and np.all(center >= right_vals):
            return float(center), idx[i].date().isoformat()
    return np.nan, None


def compute_rs_60d(stock_close: pd.Series, bench_close: Optional[pd.Series], n: int = 60) -> float:
    if stock_close is None or bench_close is None:
        return np.nan
    common = stock_close.index.intersection(bench_close.index)
    if len(common) < (n + 10):
        return np.nan
    s = stock_close.reindex(common)
    b = bench_close.reindex(common)
    rs = (s / b).replace([np.inf, -np.inf], np.nan)
    if len(rs) < (n + 1) or pd.isna(rs.iloc[-1]) or pd.isna(rs.iloc[-(n + 1)]) or rs.iloc[-(n + 1)] == 0:
        return np.nan
    return float(rs.iloc[-1] / rs.iloc[-(n + 1)] - 1.0)


def score_10pt_daily(config: dict, d_close, ema_fast_d, ema_slow_d, don_u, don_l, macd_line, macd_signal, macd_hist, adx14):
    d_close = _to_float(d_close)
    ema_fast_d = _to_float(ema_fast_d)
    ema_slow_d = _to_float(ema_slow_d)
    don_u = _to_float(don_u)
    don_l = _to_float(don_l)
    macd_line = _to_float(macd_line)
    macd_signal = _to_float(macd_signal)
    macd_hist = _to_float(macd_hist)
    adx14 = _to_float(adx14)

    score = 0
    if np.isfinite(d_close) and np.isfinite(ema_fast_d) and np.isfinite(ema_slow_d):
        if d_close > ema_fast_d > ema_slow_d:
            score += 3
        elif (d_close > ema_slow_d) and (ema_fast_d > ema_slow_d):
            score += 2
        elif d_close > ema_slow_d:
            score += 1

    if np.isfinite(d_close) and np.isfinite(don_u) and np.isfinite(don_l) and (don_u > don_l):
        if d_close > don_u:
            score += 3
        elif d_close >= config["SCORE10_DONCHIAN_NEAR_MULT"] * don_u:
            score += 2
        else:
            pos = (d_close - don_l) / (don_u - don_l)
            if pos >= config["SCORE10_DONCHIAN_POS_THRESHOLD"]:
                score += 1

    if np.isfinite(macd_line) and np.isfinite(macd_signal) and np.isfinite(macd_hist):
        if (macd_line > macd_signal) and (macd_hist > 0):
            score += 3
        elif macd_line > macd_signal:
            score += 2

    synergy = (
        np.isfinite(d_close) and np.isfinite(don_u) and (d_close > don_u)
        and np.isfinite(macd_line) and np.isfinite(macd_signal) and np.isfinite(macd_hist)
        and (macd_line > macd_signal) and (macd_hist > 0)
    )
    if (np.isfinite(adx14) and (adx14 >= config["SCORE10_ADX_THRESHOLD"])) or synergy:
        score += 1

    return int(max(0, min(10, score)))


def score_4pt_daily(config: dict, d_close, ema_fast_d, ema_slow_d, ret_60d, adx14):
    d_close = _to_float(d_close)
    ema_fast_d = _to_float(ema_fast_d)
    ema_slow_d = _to_float(ema_slow_d)
    ret_60d = _to_float(ret_60d)
    adx14 = _to_float(adx14)

    score = 0
    if np.isfinite(d_close) and np.isfinite(ema_fast_d) and np.isfinite(ema_slow_d):
        if d_close > ema_fast_d > ema_slow_d:
            score += 2
        elif d_close > ema_slow_d:
            score += 1
    if np.isfinite(ret_60d) and ret_60d > 0:
        score += 1
    if np.isfinite(adx14) and adx14 >= config["SCORE4_ADX_THRESHOLD"]:
        score += 1
    return int(max(0, min(4, score)))


def build_badges(row: pd.Series, config: dict) -> list[dict[str, str]]:
    badges = []
    trend_ok = (
        pd.notna(row.get("D_close")) and pd.notna(row.get("EMA_fast_D")) and pd.notna(row.get("EMA_slow_D"))
        and pd.notna(row.get("ADX14")) and row["D_close"] > row["EMA_fast_D"] > row["EMA_slow_D"]
        and row["ADX14"] >= config["ADX_REF_LINE"]
    )
    if trend_ok:
        badges.append({"label": "Trend OK", "kind": "green"})
    if bool(row.get("IsBreakout")):
        badges.append({"label": "Breakout", "kind": "blue"})
    pullback_flag = (
        (pd.notna(row.get("DistToEMA_fast_D")) and row["DistToEMA_fast_D"] <= config["PULLBACK_PCT_TO_EMA_FAST_D"])
        or (pd.notna(row.get("DistToEMA_slow_D")) and row["DistToEMA_slow_D"] <= config["PULLBACK_PCT_TO_EMA_SLOW_D"])
    )
    if pullback_flag:
        badges.append({"label": "Pullback", "kind": "yellow"})
    if pd.notna(row.get("RSI14_D")) and row["RSI14_D"] >= 70:
        badges.append({"label": "Hot", "kind": "red"})
    if not bool(row.get("Liquid_OK")):
        badges.append({"label": "Thin", "kind": "gray"})
    return badges


def build_interactive_payload(config: dict, symbol: str, name: str, row: dict, d: pd.DataFrame, w: pd.DataFrame,
                              ema_fast_d: pd.Series, ema_slow_d: pd.Series,
                              macd_line_d: pd.Series, macd_sig_d: pd.Series, macd_hist_d: pd.Series,
                              dc_u: pd.Series, dc_l: pd.Series, adx: pd.Series,
                              rsi14_d: pd.Series, rsi10_d: pd.Series) -> dict:
    payload = {
        "Symbol": symbol,
        "Nazwa": name,
        "badges": build_badges(pd.Series(row), config),
        "kpi": {key: row.get(key) for key in [
            "Score10", "Score4", "D_last", "D_close", "Return_20D", "Return_60D", "RS_60D", "ADX14",
            "ATR14_pct", "RSI14_D", "RSI10_D", "VolSpikeRatio", "TurnoverApproxPLN_med20", "TQ", "TQ_Label",
            "PQ", "PQ_Label", "RQ", "RQ_Label"
        ]}
    }

    d_tail_sr = d.tail(120).copy()
    d_swing_low, d_swing_low_date = find_last_swing_low(d_tail_sr["low"], 2, 2)
    d_swing_high, d_swing_high_date = find_last_swing_high(d_tail_sr["high"], 2, 2)
    d_low_20 = float(d["low"].tail(20).min()) if len(d) >= 20 else np.nan
    d_high_20 = float(d["high"].tail(20).max()) if len(d) >= 20 else np.nan
    d_low_60 = float(d["low"].tail(60).min()) if len(d) >= 60 else np.nan
    d_high_60 = float(d["high"].tail(60).max()) if len(d) >= 60 else np.nan

    if w is not None and not w.empty:
        w_tail = w.tail(config["PAYLOAD_WEEKLY_TAIL"]).copy()
        w_swing_low, w_swing_low_date = find_last_swing_low(w_tail["low"], 2, 2)
        w_swing_high, w_swing_high_date = find_last_swing_high(w_tail["high"], 2, 2)
        w_low_26 = float(w["low"].tail(26).min()) if len(w) >= 26 else np.nan
        w_high_26 = float(w["high"].tail(26).max()) if len(w) >= 26 else np.nan
        w_low_52 = float(w["low"].tail(52).min()) if len(w) >= 52 else np.nan
        w_high_52 = float(w["high"].tail(52).max()) if len(w) >= 52 else np.nan
        payload["weekly"] = {
            "dates": [dt.date().isoformat() for dt in w_tail.index],
            "open": [float(x) if pd.notna(x) else None for x in w_tail["open"].values],
            "high": [float(x) if pd.notna(x) else None for x in w_tail["high"].values],
            "low": [float(x) if pd.notna(x) else None for x in w_tail["low"].values],
            "close": [float(x) if pd.notna(x) else None for x in w_tail["close"].values],
            "vol": [float(x) if pd.notna(x) else None for x in w_tail["vol"].values],
            "sr": {
                "swing_low": float(w_swing_low) if pd.notna(w_swing_low) else None,
                "swing_low_date": w_swing_low_date,
                "swing_high": float(w_swing_high) if pd.notna(w_swing_high) else None,
                "swing_high_date": w_swing_high_date,
                "low_26": float(w_low_26) if pd.notna(w_low_26) else None,
                "high_26": float(w_high_26) if pd.notna(w_high_26) else None,
                "low_52": float(w_low_52) if pd.notna(w_low_52) else None,
                "high_52": float(w_high_52) if pd.notna(w_high_52) else None,
            },
        }
    else:
        payload["weekly"] = {"dates": [], "open": [], "high": [], "low": [], "close": [], "vol": [], "sr": {}}

    d_tail = d.tail(config["PAYLOAD_DAILY_TAIL"]).copy()
    idxd = d_tail.index
    payload["daily"] = {
        "dates": [dt.date().isoformat() for dt in idxd],
        "open": [float(x) if pd.notna(x) else None for x in d_tail["open"].values],
        "high": [float(x) if pd.notna(x) else None for x in d_tail["high"].values],
        "low": [float(x) if pd.notna(x) else None for x in d_tail["low"].values],
        "close": [float(x) if pd.notna(x) else None for x in d_tail["close"].values],
        "vol": [float(x) if pd.notna(x) else None for x in d_tail["vol"].values],
        "ema_fast": [float(x) if pd.notna(x) else None for x in ema_fast_d.reindex(idxd).values],
        "ema_slow": [float(x) if pd.notna(x) else None for x in ema_slow_d.reindex(idxd).values],
        "don_u": [float(x) if pd.notna(x) else None for x in dc_u.reindex(idxd).values],
        "don_l": [float(x) if pd.notna(x) else None for x in dc_l.reindex(idxd).values],
        "adx14": [float(x) if pd.notna(x) else None for x in adx.reindex(idxd).values],
        "macd": [float(x) if pd.notna(x) else None for x in macd_line_d.reindex(idxd).values],
        "macd_signal": [float(x) if pd.notna(x) else None for x in macd_sig_d.reindex(idxd).values],
        "macd_hist": [float(x) if pd.notna(x) else None for x in macd_hist_d.reindex(idxd).values],
        "rsi14": [float(x) if pd.notna(x) else None for x in rsi14_d.reindex(idxd).values],
        "rsi10": [float(x) if pd.notna(x) else None for x in rsi10_d.reindex(idxd).values],
        "sr": {
            "swing_low": float(d_swing_low) if pd.notna(d_swing_low) else None,
            "swing_low_date": d_swing_low_date,
            "swing_high": float(d_swing_high) if pd.notna(d_swing_high) else None,
            "swing_high_date": d_swing_high_date,
            "low_20": float(d_low_20) if pd.notna(d_low_20) else None,
            "high_20": float(d_high_20) if pd.notna(d_high_20) else None,
            "low_60": float(d_low_60) if pd.notna(d_low_60) else None,
            "high_60": float(d_high_60) if pd.notna(d_high_60) else None,
        },
    }
    return payload


def pct_rank(series: pd.Series, higher_is_better: bool = True, neutral_if_all_nan: float = 0.5) -> pd.Series:
    s = series.astype(float).copy()
    if s.notna().sum() == 0:
        return pd.Series([neutral_if_all_nan] * len(s), index=s.index)
    if not higher_is_better:
        s = -s
    med = float(s.median()) if s.notna().any() else 0.0
    s = s.fillna(med)
    return s.rank(pct=True, method="average").clip(0, 1)


def label_from_thresholds(x: float, thresholds: list[list[Any]]) -> str:
    for thr, lab in thresholds:
        if x >= thr:
            return lab
    return thresholds[-1][1]


def build_quality(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    weights = config["QUALITY_W"]
    p_score10 = pct_rank(df["Score10"], True)
    p_persist = pct_rank(df["TrendPersist40D"], True)
    p_adx = pct_rank(df["ADX14"], True)
    tq = (weights["TQ"]["Score10"] * p_score10 + weights["TQ"]["TrendPersist40D"] * p_persist + weights["TQ"]["ADX14"] * p_adx) * 100.0

    p_turn = pct_rank(df["TurnoverApproxPLN_med20"], True)
    p_vols = pct_rank(df["VolSpikeRatio"], True)
    bonus = df.apply(lambda r: 1.0 if r.get("Liquid_OK") else (0.5 if r.get("Liquid_Soft") else 0.0), axis=1)
    p_bonus = pct_rank(bonus, True)
    pq = (weights["PQ"]["TurnoverApproxPLN_med20"] * p_turn + weights["PQ"]["VolSpikeRatio"] * p_vols + weights["PQ"]["LiquidBonus"] * p_bonus) * 100.0

    p_atr_low = pct_rank(df["ATR14_pct"], higher_is_better=False)
    heat = pd.concat([df["DistToEMA_fast_D"], df["DistToEMA_slow_D"]], axis=1).max(axis=1)
    p_heat_low = pct_rank(heat, higher_is_better=False)
    rq = (weights["RQ"]["ATR14_pct_low"] * p_atr_low + weights["RQ"]["Heat_low"] * p_heat_low) * 100.0

    out = df.copy()
    out["TQ"] = tq.round(1)
    out["PQ"] = pq.round(1)
    out["RQ"] = rq.round(1)
    out["TQ_Label"] = out["TQ"].apply(lambda v: label_from_thresholds(v, config["QUALITY_LABELS"]["TQ"]))
    out["PQ_Label"] = out["PQ"].apply(lambda v: label_from_thresholds(v, config["QUALITY_LABELS"]["PQ"]))
    out["RQ_Label"] = out["RQ"].apply(lambda v: label_from_thresholds(v, config["QUALITY_LABELS"]["RQ"]))
    return out


def run_scan(zip_bytes: bytes | None, list_bytes: bytes | None, config: dict, supabase_df: pd.DataFrame | None = None) -> ScanArtifacts:
    tz = pytz.timezone("Europe/Warsaw")
    run_ts_local = datetime.now(tz).isoformat()
    run_ts_utc = datetime.now(timezone.utc).isoformat()

    zip_obj = None
    zip_index = {}

    if supabase_df is not None and not supabase_df.empty:
        unique_symbols = supabase_df['Nazwa'].unique()
        gpw = pd.DataFrame({'Symbol': unique_symbols, 'Nazwa': unique_symbols})
        gpw["Key"] = gpw["Symbol"].map(norm_ticker)
        gpw["ZipMember"] = gpw["Nazwa"]
    else:
        if zip_bytes is None or list_bytes is None:
            raise ValueError("Musisz podać albo (zip_bytes + list_bytes) albo supabase_df")
        gpw = load_gpw_list_from_bytes(list_bytes)
        zip_obj = open_zip_from_bytes(zip_bytes)
        zip_index = build_zip_index(zip_obj)
        gpw["ZipMember"] = gpw["Key"].map(zip_index)

    def load_benchmark_daily() -> Optional[pd.DataFrame]:
        if zip_obj:
            member = zip_index.get(norm_ticker(config["BENCHMARK_SYMBOL"]))
            if not member:
                return None
            df_d, _ = load_daily_from_zip(zip_obj, member)
            df_d = df_d.rename(columns=str.lower)
            if df_d.empty or len(df_d) < 200:
                return None
            return df_d
        elif supabase_df is not None:
            bench_symbol = config["BENCHMARK_SYMBOL"]
            bench_data = supabase_df[supabase_df['Nazwa'] == bench_symbol].copy()
            if not bench_data.empty:
                bench_data = bench_data.set_index('Data').sort_index()
                return bench_data
            return None
        return None

    bench_d = load_benchmark_daily()

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    interactive_store: Dict[str, Any] = {}

    for r in gpw[gpw["ZipMember"].isna()].itertuples(index=False):
        errors.append({"Symbol": r.Symbol, "Nazwa": r.Nazwa, "Stage": "zip_match", "Error": "Brak pliku w ZIP dla tickera"})

    gpw_ok = gpw.dropna(subset=["ZipMember"]).copy()

    for r in gpw_ok.itertuples(index=False):
        symbol, name, member = r.Symbol, r.Nazwa, r.ZipMember
        try:
            if supabase_df is not None:
                df_d = supabase_df[supabase_df['Nazwa'] == name].copy()
                if df_d.empty:
                    df_d = supabase_df[supabase_df['Nazwa'] == symbol].copy()
                if not df_d.empty:
                    df_d = df_d.set_index('Data').sort_index()
                    ticker_from_file = symbol
                else:
                    df_d = pd.DataFrame()
                    ticker_from_file = None
            else:
                df_d, ticker_from_file = load_daily_from_zip(zip_obj, member)
                df_d = df_d.rename(columns=str.lower)

            if df_d.empty:
                errors.append({"Symbol": symbol, "Nazwa": name, "Stage": "compute", "Error": "Brak danych dziennych"})
                continue
            if len(df_d) < 120:
                errors.append({"Symbol": symbol, "Nazwa": name, "Stage": "compute", "Error": f"Za mało danych dziennych (len={len(df_d)})"})
                continue

            last_date = df_d.index.max()
            d = df_d.loc[df_d.index >= last_date - pd.Timedelta(days=config["D_LOOKBACK_DAYS"])].copy()
            wsrc = df_d.loc[df_d.index >= last_date - pd.Timedelta(days=config["W_LOOKBACK_DAYS"])].copy()
            if d.empty:
                errors.append({"Symbol": symbol, "Nazwa": name, "Stage": "compute", "Error": "Puste okno danych"})
                continue

            dc_u, dc_l = donchian(d["high"], d["low"], config["DONCHIAN_N"])
            dc_u_prev = dc_u.shift(1)
            atr = atr_wilder(d["high"], d["low"], d["close"], config["ATR_N"])
            adx = adx_wilder(d["high"], d["low"], d["close"], config["ADX_N"])
            ema_fast_d = ema(d["close"], config["EMA_FAST_D"])
            ema_slow_d = ema(d["close"], config["EMA_SLOW_D"])
            macd_line_d, macd_sig_d, macd_hist_d = macd(d["close"], config["MACD_FAST"], config["MACD_SLOW"], config["MACD_SIGNAL"])
            rsi14 = rsi_wilder(d["close"], 14)
            rsi10 = rsi_wilder(d["close"], 10)
            w = ohlcv_to_weekly(wsrc) if not wsrc.empty else pd.DataFrame()
            ret_20d = return_nd(d["close"], config["RETURN_20D"])
            ret_60d = return_nd(d["close"], config["RETURN_60D"])
            last_atr = atr.iloc[-1] if len(atr) else np.nan
            last_close = d["close"].iloc[-1]
            atr_pct = float(last_atr / last_close) if pd.notna(last_atr) and pd.notna(last_close) and last_close != 0 else np.nan

            turnover_proxy = (d["close"] * d["vol"]).tail(config["TURNOVER_WINDOW"])
            turnover_med20 = float(turnover_proxy.median()) if len(turnover_proxy) else np.nan
            liquid_soft = bool(pd.notna(turnover_med20) and turnover_med20 >= config["MIN_TURNOVER_APPROX_PLN_MED20"])
            liquid_ok = bool(pd.notna(turnover_med20) and turnover_med20 >= config["MIN_TURNOVER_APPROX_PLN_MED20_STRICT"])

            vol_sma = d["vol"].rolling(config["VOL_SMA_N"]).mean()
            vol_spike_ratio = float(d["vol"].iloc[-1] / vol_sma.iloc[-1]) if pd.notna(vol_sma.iloc[-1]) and vol_sma.iloc[-1] != 0 else np.nan

            score10 = score_10pt_daily(config, d["close"].iloc[-1], ema_fast_d.iloc[-1], ema_slow_d.iloc[-1], dc_u.iloc[-1], dc_l.iloc[-1], macd_line_d.iloc[-1], macd_sig_d.iloc[-1], macd_hist_d.iloc[-1], adx.iloc[-1])
            score4 = score_4pt_daily(config, d["close"].iloc[-1], ema_fast_d.iloc[-1], ema_slow_d.iloc[-1], ret_60d, adx.iloc[-1])

            dist_to_ema_fast = float(abs(d["close"].iloc[-1] - ema_fast_d.iloc[-1]) / ema_fast_d.iloc[-1]) if ema_fast_d.iloc[-1] != 0 else np.nan
            dist_to_ema_slow = float(abs(d["close"].iloc[-1] - ema_slow_d.iloc[-1]) / ema_slow_d.iloc[-1]) if ema_slow_d.iloc[-1] != 0 else np.nan
            d_tail = d.tail(int(config["TREND_PERSIST_DAYS"]))
            ema_slow_tail = ema_slow_d.reindex(d_tail.index)
            trend_persist = float(((d_tail["close"] > ema_slow_tail).astype(int)).mean()) if len(d_tail) >= 20 else np.nan

            d_close = float(d["close"].iloc[-1])
            d_high = float(d["high"].iloc[-1])
            don_u_prev = dc_u_prev.iloc[-1]
            is_breakout = False
            if pd.notna(don_u_prev):
                don_u_prev = float(don_u_prev)
                if config["BREAKOUT_MODE"] == "high_touch":
                    is_breakout = bool(d_high > don_u_prev)
                else:
                    is_breakout = bool(d_close >= config["CLOSE_NEAR_MULT"] * don_u_prev)

            rs_60d = compute_rs_60d(d["close"], bench_d["close"] if bench_d is not None else None, n=60)
            row = {
                "Symbol": symbol, "Nazwa": name, "Score10": int(score10), "Score4": int(score4),
                "TrendPersist40D": float(trend_persist) if pd.notna(trend_persist) else np.nan,
                "D_last": d.index.max().date().isoformat(),
                "D_close": float(d["close"].iloc[-1]), "D_high": float(d["high"].iloc[-1]),
                "EMA_fast_D": float(ema_fast_d.iloc[-1]), "EMA_slow_D": float(ema_slow_d.iloc[-1]),
                "MACD_D": float(macd_line_d.iloc[-1]), "MACD_signal_D": float(macd_sig_d.iloc[-1]), "MACD_hist_D": float(macd_hist_d.iloc[-1]),
                "Return_20D": float(ret_20d) if pd.notna(ret_20d) else np.nan,
                "Return_60D": float(ret_60d) if pd.notna(ret_60d) else np.nan,
                "RS_60D": float(rs_60d) if pd.notna(rs_60d) else np.nan,
                "DonchianU_20": float(dc_u.iloc[-1]) if pd.notna(dc_u.iloc[-1]) else np.nan,
                "DonchianU_20_prev": float(don_u_prev) if pd.notna(don_u_prev) else np.nan,
                "DonchianL_20": float(dc_l.iloc[-1]) if pd.notna(dc_l.iloc[-1]) else np.nan,
                "ADX14": float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else np.nan,
                "ATR14": float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else np.nan,
                "ATR14_pct": float(atr_pct) if pd.notna(atr_pct) else np.nan,
                "RSI14_D": float(rsi14.iloc[-1]) if pd.notna(rsi14.iloc[-1]) else np.nan,
                "RSI10_D": float(rsi10.iloc[-1]) if pd.notna(rsi10.iloc[-1]) else np.nan,
                "D_vol": float(d["vol"].iloc[-1]) if pd.notna(d["vol"].iloc[-1]) else np.nan,
                "VolSpikeRatio": float(vol_spike_ratio) if pd.notna(vol_spike_ratio) else np.nan,
                "TurnoverApproxPLN_med20": float(turnover_med20) if pd.notna(turnover_med20) else np.nan,
                "Liquid_OK": bool(liquid_ok), "Liquid_Soft": bool(liquid_soft), "IsBreakout": bool(is_breakout),
                "DistToEMA_fast_D": float(dist_to_ema_fast) if pd.notna(dist_to_ema_fast) else np.nan,
                "DistToEMA_slow_D": float(dist_to_ema_slow) if pd.notna(dist_to_ema_slow) else np.nan,
                "TQ": np.nan, "TQ_Label": None, "PQ": np.nan, "PQ_Label": None, "RQ": np.nan, "RQ_Label": None,
                "ZipMember": member, "TickerFromFile": ticker_from_file,
            }
            rows.append(row)
            interactive_store[symbol] = build_interactive_payload(config, symbol, name, row, d, w, ema_fast_d, ema_slow_d, macd_line_d, macd_sig_d, macd_hist_d, dc_u, dc_l, adx, rsi14, rsi10)
        except Exception as exc:
            errors.append({"Symbol": symbol, "Nazwa": name, "Stage": "exception", "Error": str(exc)})

    if zip_obj:
        zip_obj.close()

    df_rank = pd.DataFrame(rows)
    df_err = pd.DataFrame(errors)
    if not df_rank.empty:
        df_rank = df_rank.sort_values(config["SORT_COLUMNS"], ascending=config["SORT_ASC"], na_position="last")
        df_rank = build_quality(df_rank, config)
        for sym, payload in interactive_store.items():
            rr = df_rank[df_rank["Symbol"] == sym].head(1)
            if len(rr):
                for key in ["TQ", "PQ", "RQ"]:
                    payload["kpi"][key] = float(rr[key].iloc[0]) if pd.notna(rr[key].iloc[0]) else None
                for key in ["TQ_Label", "PQ_Label", "RQ_Label"]:
                    payload["kpi"][key] = rr[key].iloc[0]

    df_leaders = df_rank[(df_rank["Liquid_OK"] == True) & (df_rank["Score10"] >= config["LEADERS_SCORE10_MIN"])] if not df_rank.empty else pd.DataFrame()
    df_breakouts_watch = df_rank[(df_rank["IsBreakout"] == True) & (df_rank["Score10"] >= config["BREAKOUTS_WATCH_SCORE10_MIN"])] if not df_rank.empty else pd.DataFrame()
    if not df_breakouts_watch.empty:
        df_breakouts_watch = df_breakouts_watch.sort_values(["Score10", "VolSpikeRatio", "TurnoverApproxPLN_med20"], ascending=[False, False, False], na_position="last")

    df_breakouts_strict = df_rank[
        (df_rank["IsBreakout"] == True) & (df_rank["Liquid_OK"] == True) & (df_rank["Score10"] >= config["BREAKOUTS_STRICT_SCORE10_MIN"]) &
        (df_rank["MACD_D"] > df_rank["MACD_signal_D"]) & (df_rank["VolSpikeRatio"].fillna(0) >= config["VOL_SPIKE_MULT_STRICT"])
    ] if not df_rank.empty else pd.DataFrame()
    if not df_breakouts_strict.empty:
        df_breakouts_strict = df_breakouts_strict.sort_values(["Score10", "VolSpikeRatio", "TurnoverApproxPLN_med20"], ascending=[False, False, False], na_position="last")

    df_pullbacks = df_rank[
        (df_rank["Liquid_OK"] == True) & (df_rank["Score10"] >= config["PULLBACKS_SCORE10_MIN"]) &
        ((df_rank["DistToEMA_fast_D"].fillna(999) <= config["PULLBACK_PCT_TO_EMA_FAST_D"]) |
         (df_rank["DistToEMA_slow_D"].fillna(999) <= config["PULLBACK_PCT_TO_EMA_SLOW_D"]))
    ] if not df_rank.empty else pd.DataFrame()
    if not df_pullbacks.empty:
        df_pullbacks = df_pullbacks.sort_values(["Score10", "DistToEMA_fast_D", "DistToEMA_slow_D"], ascending=[False, True, True], na_position="last")

    summary = {
        "run_ts_local": run_ts_local,
        "run_ts_utc": run_ts_utc,
        "benchmark_symbol": config["BENCHMARK_SYMBOL"],
        "counts": {
            "rank_rows": int(len(df_rank)), "errors_rows": int(len(df_err)), "leaders": int(len(df_leaders)),
            "breakouts_watch": int(len(df_breakouts_watch)), "breakouts_strict": int(len(df_breakouts_strict)), "pullbacks": int(len(df_pullbacks)),
        },
    }
    audit_row = {"ts_utc": run_ts_utc, "summary": summary, "config": config}
    return ScanArtifacts(
        df_rank=df_rank,
        df_err=df_err,
        df_leaders=df_leaders,
        df_breakouts_watch=df_breakouts_watch,
        df_breakouts_strict=df_breakouts_strict,
        df_pullbacks=df_pullbacks,
        interactive_store=interactive_store,
        audit_rows=[audit_row],
        summary=summary,
    )
