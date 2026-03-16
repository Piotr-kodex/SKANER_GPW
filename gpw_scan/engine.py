\
# -*- coding: utf-8 -*-
from __future__ import annotations

import io, json
from datetime import date
import numpy as np
import pandas as pd
from datetime import datetime, timezone
import pytz
import requests

from .utils import to_float, norm_ticker
from .data_io import open_zip_from_bytes, build_zip_index, load_daily_from_zip, load_gpw_list_from_bytes
from .indicators import (
    ema, macd, atr_wilder, adx_wilder, donchian, rsi_wilder, ohlcv_to_weekly, return_nd
)
from .reporting import build_interactive_html, write_excel_bytes
from .live_quote import fetch_stooq_live_quotes, upsert_today_bar_from_quote

def run_gpw_scan(cfg: dict, stooq_zip_bytes: bytes, list_bytes: bytes) -> dict:
    """
    Cloud-ready engine:
    - wejście: bytes ZIP + bytes listy
    - wyjście: DataFrame'y + pliki jako bytes (excel/html/audit)
    """
    # ---------- load inputs ----------
    gpw = load_gpw_list_from_bytes(list_bytes)

    z = open_zip_from_bytes(stooq_zip_bytes)
    zip_index = build_zip_index(z)

    gpw["ZipMember"] = gpw["Key"].map(zip_index)

    # ---------- benchmark ----------
    def load_benchmark_daily():
        key = norm_ticker(cfg["BENCHMARK_SYMBOL"])
        member = zip_index.get(key)
        if not member:
            return None
        df_d, _ = load_daily_from_zip(z, member)
        df_d = df_d.rename(columns=str.lower)
        if df_d.empty or len(df_d) < 200:
            return None
        return df_d

    bench_d = load_benchmark_daily()

    def compute_rs_60d(stock_close: pd.Series, bench_close: pd.Series, n=60):
        if stock_close is None or bench_close is None:
            return np.nan
        common = stock_close.index.intersection(bench_close.index)
        if len(common) < (n + 10):
            return np.nan
        s = stock_close.reindex(common)
        b = bench_close.reindex(common)
        rs = (s / b).replace([np.inf, -np.inf], np.nan)
        if len(rs) < (n + 1) or pd.isna(rs.iloc[-1]) or pd.isna(rs.iloc[-(n+1)]) or rs.iloc[-(n+1)] == 0:
            return np.nan
        return float(rs.iloc[-1] / rs.iloc[-(n+1)] - 1.0)

    # ---------- scoring ----------
    def score_10pt_daily(D_close, EMA_fast, EMA_slow, DonU, DonL,
                         MACD_line, MACD_signal, MACD_hist, ADX14):
        D_close=to_float(D_close); EMA_fast=to_float(EMA_fast); EMA_slow=to_float(EMA_slow)
        DonU=to_float(DonU); DonL=to_float(DonL)
        MACD_line=to_float(MACD_line); MACD_signal=to_float(MACD_signal); MACD_hist=to_float(MACD_hist)
        ADX14=to_float(ADX14)

        score = 0

        # A) Trend daily (EMA) — do 3 pkt
        if np.isfinite(D_close) and np.isfinite(EMA_fast) and np.isfinite(EMA_slow):
            if D_close > EMA_fast > EMA_slow:
                score += 3
            elif (D_close > EMA_slow) and (EMA_fast > EMA_slow):
                score += 2
            elif D_close > EMA_slow:
                score += 1

        # B) Donchian daily — do 3 pkt
        if np.isfinite(D_close) and np.isfinite(DonU) and np.isfinite(DonL) and (DonU > DonL):
            if D_close > DonU:
                score += 3
            elif D_close >= cfg["SCORE10_DONCHIAN_NEAR_MULT"] * DonU:
                score += 2
            else:
                pos = (D_close - DonL) / (DonU - DonL)
                if pos >= cfg["SCORE10_DONCHIAN_POS_THRESHOLD"]:
                    score += 1

        # C) MACD daily — do 3 pkt
        if np.isfinite(MACD_line) and np.isfinite(MACD_signal) and np.isfinite(MACD_hist):
            if (MACD_line > MACD_signal) and (MACD_hist > 0):
                score += 3
            elif (MACD_line > MACD_signal):
                score += 2

        # D) ADX / synergy — 1 pkt
        synergy = (
            np.isfinite(D_close) and np.isfinite(DonU) and (D_close > DonU) and
            np.isfinite(MACD_line) and np.isfinite(MACD_signal) and np.isfinite(MACD_hist) and
            (MACD_line > MACD_signal) and (MACD_hist > 0)
        )
        if (np.isfinite(ADX14) and (ADX14 >= cfg["SCORE10_ADX_THRESHOLD"])) or synergy:
            score += 1

        return int(max(0, min(10, score)))

    def score_4pt_daily(D_close, EMA_fast, EMA_slow, ret_60d, adx14):
        D_close=to_float(D_close); EMA_fast=to_float(EMA_fast); EMA_slow=to_float(EMA_slow)
        ret_60d=to_float(ret_60d); adx14=to_float(adx14)

        s = 0
        if np.isfinite(D_close) and np.isfinite(EMA_fast) and np.isfinite(EMA_slow):
            if D_close > EMA_fast > EMA_slow:
                s += 2
            elif D_close > EMA_slow:
                s += 1
        if np.isfinite(ret_60d) and ret_60d > 0:
            s += 1
        if np.isfinite(adx14) and adx14 >= cfg["SCORE4_ADX_THRESHOLD"]:
            s += 1
        return int(max(0, min(4, s)))

    # ---------- payload ----------
    def build_interactive_payload(symbol, name, row, d, w,
                                  ema_fast_d, ema_slow_d,
                                  macd_line_d, macd_sig_d, macd_hist_d,
                                  dc_u, dc_l, adx,
                                  rsi14_d, rsi10_d):
        payload = {
            "Symbol": symbol,
            "Nazwa": name,
            "kpi": {
                "Score10": row.get("Score10"),
                "Score4": row.get("Score4"),
                "D_last": row.get("D_last"),
                "D_close": row.get("D_close"),
                "Return_20D": row.get("Return_20D"),
                "Return_60D": row.get("Return_60D"),
                "RS_60D": row.get("RS_60D"),
                "ADX14": row.get("ADX14"),
                "ATR14_pct": row.get("ATR14_pct"),
                "RSI14_D": row.get("RSI14_D"),
                "RSI10_D": row.get("RSI10_D"),
                "VolSpikeRatio": row.get("VolSpikeRatio"),
                "TurnoverApproxPLN_med20": row.get("TurnoverApproxPLN_med20"),
                "TQ": row.get("TQ"),
                "TQ_Label": row.get("TQ_Label"),
                "PQ": row.get("PQ"),
                "PQ_Label": row.get("PQ_Label"),
                "RQ": row.get("RQ"),
                "RQ_Label": row.get("RQ_Label"),
            }
        }

        # weekly poglądowo
        if w is not None and not w.empty:
            w_tail = w.tail(cfg["PAYLOAD_WEEKLY_TAIL"]).copy()
            idxw = w_tail.index
            payload["weekly"] = {
                "dates": [dt.date().isoformat() for dt in idxw],
                "open":  [float(x) if pd.notna(x) else None for x in w_tail["open"].values],
                "high":  [float(x) if pd.notna(x) else None for x in w_tail["high"].values],
                "low":   [float(x) if pd.notna(x) else None for x in w_tail["low"].values],
                "close": [float(x) if pd.notna(x) else None for x in w_tail["close"].values],
                "vol":   [float(x) if pd.notna(x) else None for x in w_tail["vol"].values],
            }
        else:
            payload["weekly"] = {"dates":[], "open":[], "high":[], "low":[], "close":[], "vol":[]}

        # daily (pełne dane do wykresów)
        d_tail = d.tail(cfg["PAYLOAD_DAILY_TAIL"]).copy()
        idxd = d_tail.index
        payload["daily"] = {
            "dates": [dt.date().isoformat() for dt in idxd],
            "open":  [float(x) if pd.notna(x) else None for x in d_tail["open"].values],
            "high":  [float(x) if pd.notna(x) else None for x in d_tail["high"].values],
            "low":   [float(x) if pd.notna(x) else None for x in d_tail["low"].values],
            "close": [float(x) if pd.notna(x) else None for x in d_tail["close"].values],
            "vol":   [float(x) if pd.notna(x) else None for x in d_tail["vol"].values],
            "ema_fast": [float(x) if pd.notna(x) else None for x in ema_fast_d.reindex(idxd).values],
            "ema_slow": [float(x) if pd.notna(x) else None for x in ema_slow_d.reindex(idxd).values],
            "don_u": [float(x) if pd.notna(x) else None for x in dc_u.reindex(idxd).values],
            "don_l": [float(x) if pd.notna(x) else None for x in dc_l.reindex(idxd).values],
            "adx14": [float(x) if pd.notna(x) else None for x in adx.reindex(idxd).values],
            "macd":  [float(x) if pd.notna(x) else None for x in macd_line_d.reindex(idxd).values],
            "macd_signal": [float(x) if pd.notna(x) else None for x in macd_sig_d.reindex(idxd).values],
            "macd_hist":   [float(x) if pd.notna(x) else None for x in macd_hist_d.reindex(idxd).values],
            "rsi14": [float(x) if pd.notna(x) else None for x in rsi14_d.reindex(idxd).values],
            "rsi10": [float(x) if pd.notna(x) else None for x in rsi10_d.reindex(idxd).values],
        }
        return payload

    # ---------- per-symbol compute ----------
    def compute_row(symbol, name, df_d):
        if df_d.empty:
            return None, "Brak danych dziennych", None

        last_date = df_d.index.max()
        d_start = last_date - pd.Timedelta(days=cfg["D_LOOKBACK_DAYS"])
        w_start = last_date - pd.Timedelta(days=cfg["W_LOOKBACK_DAYS"])

        d = df_d.loc[df_d.index >= d_start].copy()
        wsrc = df_d.loc[df_d.index >= w_start].copy()

        if d.empty:
            return None, f"Puste okno danych (d={len(d)})", None
        if len(df_d) < 120:
            return None, f"Za mało danych dziennych (len={len(df_d)})", None

        dc_u, dc_l = donchian(d["high"], d["low"], cfg["DONCHIAN_N"])
        dc_u_prev = dc_u.shift(1)

        atr = atr_wilder(d["high"], d["low"], d["close"], cfg["ATR_N"])
        adx = adx_wilder(d["high"], d["low"], d["close"], cfg["ADX_N"])

        ema_fast_d = ema(d["close"], cfg["EMA_FAST_D"])
        ema_slow_d = ema(d["close"], cfg["EMA_SLOW_D"])

        macd_line_d, macd_sig_d, macd_hist_d = macd(
            d["close"], cfg["MACD_FAST"], cfg["MACD_SLOW"], cfg["MACD_SIGNAL"]
        )

        rsi14 = rsi_wilder(d["close"], 14)
        rsi10 = rsi_wilder(d["close"], 10)
        last_rsi14 = float(rsi14.iloc[-1]) if len(rsi14) and pd.notna(rsi14.iloc[-1]) else np.nan
        last_rsi10 = float(rsi10.iloc[-1]) if len(rsi10) and pd.notna(rsi10.iloc[-1]) else np.nan

        w = ohlcv_to_weekly(wsrc) if not wsrc.empty else pd.DataFrame()

        ret_20d = return_nd(d["close"], cfg["RETURN_20D"])
        ret_60d = return_nd(d["close"], cfg["RETURN_60D"])

        last_atr = atr.iloc[-1] if len(atr) else np.nan
        last_close = d["close"].iloc[-1] if len(d) else np.nan
        atr_pct = float(last_atr / last_close) if pd.notna(last_atr) and pd.notna(last_close) and last_close != 0 else np.nan

        turnover_proxy = (d["close"] * d["vol"]).tail(cfg["TURNOVER_WINDOW"])
        turnover_med20 = float(turnover_proxy.median()) if len(turnover_proxy) else np.nan
        liquid_soft = bool(pd.notna(turnover_med20) and turnover_med20 >= cfg["MIN_TURNOVER_APPROX_PLN_MED20"])
        liquid_ok   = bool(pd.notna(turnover_med20) and turnover_med20 >= cfg["MIN_TURNOVER_APPROX_PLN_MED20_STRICT"])

        vol_sma = d["vol"].rolling(cfg["VOL_SMA_N"]).mean()
        vol_spike_ratio = float(d["vol"].iloc[-1] / vol_sma.iloc[-1]) if pd.notna(vol_sma.iloc[-1]) and vol_sma.iloc[-1] != 0 else np.nan

        score10 = score_10pt_daily(
            d["close"].iloc[-1], ema_fast_d.iloc[-1], ema_slow_d.iloc[-1],
            dc_u.iloc[-1], dc_l.iloc[-1],
            macd_line_d.iloc[-1], macd_sig_d.iloc[-1], macd_hist_d.iloc[-1],
            adx.iloc[-1]
        )
        score4 = score_4pt_daily(
            d["close"].iloc[-1], ema_fast_d.iloc[-1], ema_slow_d.iloc[-1],
            ret_60d, adx.iloc[-1]
        )

        dist_to_ema_fast = float(abs(d["close"].iloc[-1] - ema_fast_d.iloc[-1]) / ema_fast_d.iloc[-1]) if ema_fast_d.iloc[-1] != 0 else np.nan
        dist_to_ema_slow = float(abs(d["close"].iloc[-1] - ema_slow_d.iloc[-1]) / ema_slow_d.iloc[-1]) if ema_slow_d.iloc[-1] != 0 else np.nan

        Np = int(cfg["TREND_PERSIST_DAYS"])
        d_tail = d.tail(Np)
        ema_slow_tail = ema_slow_d.reindex(d_tail.index)
        trend_persist = float(((d_tail["close"] > ema_slow_tail).astype(int)).mean()) if len(d_tail) >= 20 else np.nan

        d_close = float(d["close"].iloc[-1])
        d_high  = float(d["high"].iloc[-1])
        don_u_prev = dc_u_prev.iloc[-1]

        is_breakout = False
        if pd.notna(don_u_prev):
            don_u_prev = float(don_u_prev)
            if cfg["BREAKOUT_MODE"] == "high_touch":
                is_breakout = bool(d_high > don_u_prev)
            else:
                is_breakout = bool(d_close >= cfg["CLOSE_NEAR_MULT"] * don_u_prev)

        rs_60d = compute_rs_60d(d["close"], bench_d["close"] if bench_d is not None else None, n=60)

        row = {
            "Symbol": symbol, "Nazwa": name,
            "Score10": int(score10), "Score4": int(score4),

            "TrendPersist40D": float(trend_persist) if pd.notna(trend_persist) else np.nan,

            "D_last": d.index.max().date().isoformat(),
            "D_close": float(d["close"].iloc[-1]),
            "D_high": float(d["high"].iloc[-1]),

            "EMA_fast_D": float(ema_fast_d.iloc[-1]),
            "EMA_slow_D": float(ema_slow_d.iloc[-1]),

            "MACD_D": float(macd_line_d.iloc[-1]),
            "MACD_signal_D": float(macd_sig_d.iloc[-1]),
            "MACD_hist_D": float(macd_hist_d.iloc[-1]),

            "Return_20D": float(ret_20d) if pd.notna(ret_20d) else np.nan,
            "Return_60D": float(ret_60d) if pd.notna(ret_60d) else np.nan,
            "RS_60D": float(rs_60d) if pd.notna(rs_60d) else np.nan,

            "DonchianU_20": float(dc_u.iloc[-1]) if pd.notna(dc_u.iloc[-1]) else np.nan,
            "DonchianU_20_prev": float(don_u_prev) if pd.notna(don_u_prev) else np.nan,
            "DonchianL_20": float(dc_l.iloc[-1]) if pd.notna(dc_l.iloc[-1]) else np.nan,

            "ADX14": float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else np.nan,
            "ATR14": float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else np.nan,
            "ATR14_pct": float(atr_pct) if pd.notna(atr_pct) else np.nan,

            "RSI14_D": float(last_rsi14) if pd.notna(last_rsi14) else np.nan,
            "RSI10_D": float(last_rsi10) if pd.notna(last_rsi10) else np.nan,

            "D_vol": float(d["vol"].iloc[-1]) if pd.notna(d["vol"].iloc[-1]) else np.nan,
            "VolSpikeRatio": float(vol_spike_ratio) if pd.notna(vol_spike_ratio) else np.nan,

            "TurnoverApproxPLN_med20": float(turnover_med20) if pd.notna(turnover_med20) else np.nan,
            "Liquid_OK": bool(liquid_ok),
            "Liquid_Soft": bool(liquid_soft),

            "IsBreakout": bool(is_breakout),
            "DistToEMA_fast_D": float(dist_to_ema_fast) if pd.notna(dist_to_ema_fast) else np.nan,
            "DistToEMA_slow_D": float(dist_to_ema_slow) if pd.notna(dist_to_ema_slow) else np.nan,

            "TQ": np.nan, "TQ_Label": None,
            "PQ": np.nan, "PQ_Label": None,
            "RQ": np.nan, "RQ_Label": None,
        }

        payload = {
            "d": d, "w": w,
            "ema_fast_d": ema_fast_d, "ema_slow_d": ema_slow_d,
            "macd_line_d": macd_line_d, "macd_sig_d": macd_sig_d, "macd_hist_d": macd_hist_d,
            "dc_u": dc_u, "dc_l": dc_l, "adx": adx,
            "rsi14": rsi14, "rsi10": rsi10,
        }
        return row, None, payload

    # ---------- run loop ----------
    rows, errors = [], []
    interactive_store = {}

    gpw_missing = gpw[gpw["ZipMember"].isna()]
    for r in gpw_missing.itertuples(index=False):
        errors.append({"Symbol": r.Symbol, "Nazwa": r.Nazwa, "ZipMember": None, "Stage": "zip_match",
                       "Error": "Brak pliku w ZIP dla tickera", "DailyLen": None})

    gpw_ok = gpw.dropna(subset=["ZipMember"]).copy()

    # ---------- optional: enrich DAILY series with today's (intraday) bar ----------
    tz = pytz.timezone("Europe/Warsaw")
    today_pl = datetime.now(tz).date()
    use_today = bool(cfg.get("INCLUDE_TODAY_INTRADAY", False))
    quote_provider = str(cfg.get("TODAY_QUOTE_PROVIDER", "stooq")).lower().strip()
    quote_timeout = float(cfg.get("TODAY_QUOTE_TIMEOUT", 8.0))
    http_sess = requests.Session() if (use_today and quote_provider == "stooq") else None

    for r in gpw_ok.itertuples(index=False):
        symbol, name, member = r.Symbol, r.Nazwa, r.ZipMember
        try:
            df_d, ticker_from_file = load_daily_from_zip(z, member)
            df_d = df_d.rename(columns=str.lower)

            # Jeśli ZIP nie ma jeszcze dzisiejszej świecy (w trakcie sesji),
            # to dociągnij "latest quote" i zrób upsert dzisiejszego wiersza.
            if use_today and http_sess is not None and (not df_d.empty):
                try:
                    last_day = df_d.index.max().date()
                    if last_day < today_pl:
                        qmap = fetch_stooq_live_quotes([symbol], session=http_sess, timeout=quote_timeout)
                        q = qmap.get(str(symbol).upper())
                        if q and q.day == today_pl:
                            df_d = upsert_today_bar_from_quote(df_d, q)
                except Exception:
                    # live quote jest "best effort" – nie blokuje całego skanu
                    pass

            row, reason, payload = compute_row(symbol, name, df_d)
            if row is None:
                dlen = int(len(df_d)) if df_d is not None else None
                errors.append({"Symbol": symbol, "Nazwa": name, "ZipMember": member, "Stage": "compute",
                               "Error": reason or "row=None", "DailyLen": dlen})
            else:
                row["ZipMember"] = member
                row["TickerFromFile"] = ticker_from_file
                rows.append(row)

                interactive_store[symbol] = build_interactive_payload(
                    symbol, name, row,
                    payload["d"], payload["w"],
                    payload["ema_fast_d"], payload["ema_slow_d"],
                    payload["macd_line_d"], payload["macd_sig_d"], payload["macd_hist_d"],
                    payload["dc_u"], payload["dc_l"], payload["adx"],
                    payload["rsi14"], payload["rsi10"],
                )

        except Exception as e:
            errors.append({"Symbol": symbol, "Nazwa": name, "ZipMember": member, "Stage": "exception",
                           "Error": str(e), "DailyLen": None})

    z.close()
    if http_sess is not None:
        http_sess.close()

    df_rank = pd.DataFrame(rows)
    df_err = pd.DataFrame(errors)
    if not df_rank.empty:
        df_rank = df_rank.sort_values(cfg["SORT_COLUMNS"], ascending=cfg["SORT_ASC"], na_position="last")

    # ---------- quality ----------
    def pct_rank(series: pd.Series, higher_is_better=True, neutral_if_all_nan=0.5):
        s = series.astype(float).copy()
        if s.notna().sum() == 0:
            return pd.Series([neutral_if_all_nan]*len(s), index=s.index)
        if not higher_is_better:
            s = -s
        med = float(s.median()) if s.notna().any() else 0.0
        s = s.fillna(med)
        return s.rank(pct=True, method="average").clip(0, 1)

    def label_from_thresholds(x, thresholds):
        for thr, lab in thresholds:
            if x >= thr:
                return lab
        return thresholds[-1][1]

    def build_quality(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df

        W = cfg["QUALITY_W"]

        p_score10 = pct_rank(df["Score10"], True)
        p_persist = pct_rank(df["TrendPersist40D"], True)
        p_adx     = pct_rank(df["ADX14"], True)
        tq = (W["TQ"]["Score10"]*p_score10 + W["TQ"]["TrendPersist40D"]*p_persist + W["TQ"]["ADX14"]*p_adx) * 100.0

        p_turn = pct_rank(df["TurnoverApproxPLN_med20"], True)
        p_vols = pct_rank(df["VolSpikeRatio"], True)
        bonus = df.apply(lambda r: 1.0 if r.get("Liquid_OK") else (0.5 if r.get("Liquid_Soft") else 0.0), axis=1)
        p_bonus = pct_rank(bonus, True)
        pq = (W["PQ"]["TurnoverApproxPLN_med20"]*p_turn + W["PQ"]["VolSpikeRatio"]*p_vols + W["PQ"]["LiquidBonus"]*p_bonus) * 100.0

        p_atr_low = pct_rank(df["ATR14_pct"], higher_is_better=False)
        heat = pd.concat([df["DistToEMA_fast_D"], df["DistToEMA_slow_D"]], axis=1).max(axis=1)
        p_heat_low = pct_rank(heat, higher_is_better=False)
        rq = (W["RQ"]["ATR14_pct_low"]*p_atr_low + W["RQ"]["Heat_low"]*p_heat_low) * 100.0

        df = df.copy()
        df["TQ"] = tq.round(1)
        df["PQ"] = pq.round(1)
        df["RQ"] = rq.round(1)

        df["TQ_Label"] = df["TQ"].apply(lambda v: label_from_thresholds(v, cfg["QUALITY_LABELS"]["TQ"]))
        df["PQ_Label"] = df["PQ"].apply(lambda v: label_from_thresholds(v, cfg["QUALITY_LABELS"]["PQ"]))
        df["RQ_Label"] = df["RQ"].apply(lambda v: label_from_thresholds(v, cfg["QUALITY_LABELS"]["RQ"]))
        return df

    df_rank = build_quality(df_rank)

    # update interactive_store with quality
    for sym, p in list(interactive_store.items()):
        rr = df_rank[df_rank["Symbol"] == sym].head(1)
        if len(rr):
            p["kpi"]["TQ"] = float(rr["TQ"].iloc[0]) if pd.notna(rr["TQ"].iloc[0]) else None
            p["kpi"]["TQ_Label"] = rr["TQ_Label"].iloc[0]
            p["kpi"]["PQ"] = float(rr["PQ"].iloc[0]) if pd.notna(rr["PQ"].iloc[0]) else None
            p["kpi"]["PQ_Label"] = rr["PQ_Label"].iloc[0]
            p["kpi"]["RQ"] = float(rr["RQ"].iloc[0]) if pd.notna(rr["RQ"].iloc[0]) else None
            p["kpi"]["RQ_Label"] = rr["RQ_Label"].iloc[0]

    # ---------- filters ----------
    df_leaders = df_rank[(df_rank["Liquid_OK"] == True) & (df_rank["Score10"] >= cfg["LEADERS_SCORE10_MIN"])]

    df_breakouts_watch = df_rank[
        (df_rank["IsBreakout"] == True) &
        (df_rank["Score10"] >= cfg["BREAKOUTS_WATCH_SCORE10_MIN"])
    ].sort_values(["Score10","VolSpikeRatio","TurnoverApproxPLN_med20"], ascending=[False,False,False], na_position="last")

    df_breakouts_strict = df_rank[
        (df_rank["IsBreakout"] == True) &
        (df_rank["Liquid_OK"] == True) &
        (df_rank["Score10"] >= cfg["BREAKOUTS_STRICT_SCORE10_MIN"]) &
        (df_rank["MACD_D"] > df_rank["MACD_signal_D"]) &
        (df_rank["VolSpikeRatio"].fillna(0) >= cfg["VOL_SPIKE_MULT_STRICT"])
    ].sort_values(["Score10","VolSpikeRatio","TurnoverApproxPLN_med20"], ascending=[False,False,False], na_position="last")

    df_pullbacks = df_rank[
        (df_rank["Liquid_OK"] == True) &
        (df_rank["Score10"] >= cfg["PULLBACKS_SCORE10_MIN"]) &
        (
            (df_rank["DistToEMA_fast_D"].fillna(999) <= cfg["PULLBACK_PCT_TO_EMA_FAST_D"]) |
            (df_rank["DistToEMA_slow_D"].fillna(999) <= cfg["PULLBACK_PCT_TO_EMA_SLOW_D"])
        )
    ].sort_values(["Score10","DistToEMA_fast_D","DistToEMA_slow_D"], ascending=[False,True,True], na_position="last")

    # ---------- outputs (bytes) ----------
    excel_bytes = write_excel_bytes(cfg, df_rank, df_leaders, df_breakouts_watch, df_breakouts_strict, df_pullbacks, df_err)
    html_str = build_interactive_html(cfg, df_leaders, df_breakouts_watch, df_breakouts_strict, df_pullbacks, interactive_store)
    html_bytes = html_str.encode("utf-8")

    run_ts = datetime.now(timezone.utc).isoformat()
    audit = {
        "run_ts_utc": run_ts,
        "breakout_mode": cfg["BREAKOUT_MODE"],
        "close_near_mult": cfg["CLOSE_NEAR_MULT"],
        "benchmark_symbol": cfg["BENCHMARK_SYMBOL"],
        "counts": {
            "rank_rows": int(len(df_rank)),
            "errors_rows": int(len(df_err)),
            "leaders": int(len(df_leaders)),
            "breakouts_watch": int(len(df_breakouts_watch)),
            "breakouts_strict": int(len(df_breakouts_strict)),
            "pullbacks": int(len(df_pullbacks)),
        },
    }
    audit_jsonl_bytes = (json.dumps(audit, ensure_ascii=False) + "\n").encode("utf-8")

    return {
        "df_rank": df_rank,
        "df_err": df_err,
        "df_leaders": df_leaders,
        "df_breakouts_watch": df_breakouts_watch,
        "df_breakouts_strict": df_breakouts_strict,
        "df_pullbacks": df_pullbacks,
        "xlsx_bytes": excel_bytes,
        "interactive_html_bytes": html_bytes,
        "audit_jsonl_bytes": audit_jsonl_bytes,
        "meta": audit,
    }
