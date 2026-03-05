# -*- coding: utf-8 -*-
"""Live quotes (intraday) helpers.

Core scan uses historical end-of-day OHLCV from the user-provided Stooq ZIP.
To show *today's* still-forming daily bar on charts (D1), we can enrich the
series with Stooq's "latest quote" endpoint:

  https://stooq.pl/q/l/?s=SYMBOL&e=xml

Important nuance: the field called "close" in the endpoint response is actually
the **last price** during the session.

We parse the response defensively as CSV-like rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, Optional

import pandas as pd
import requests


@dataclass(frozen=True)
class StooqLiveQuote:
    symbol: str
    day: date
    time_hhmmss: str
    open: float
    high: float
    low: float
    last: float  # "close" in response = last price
    volume: float


def _parse_stooq_rows(text: str) -> Dict[str, StooqLiveQuote]:
    """Parse Stooq /q/l response.

    Expected fields:
      symbol,date,time,open,high,low,close,volume,...

    We accept rows with at least 8 fields.
    """

    out: Dict[str, StooqLiveQuote] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue

        sym = parts[0].upper()
        ds = parts[1]
        ts = parts[2]

        try:
            day = pd.to_datetime(ds, format="%Y%m%d", errors="raise").date()
        except Exception:
            continue

        def _f(x: str) -> float:
            try:
                return float(x)
            except Exception:
                return float("nan")

        o = _f(parts[3])
        h = _f(parts[4])
        l = _f(parts[5])
        c = _f(parts[6])
        v = _f(parts[7])

        out[sym] = StooqLiveQuote(
            symbol=sym,
            day=day,
            time_hhmmss=str(ts),
            open=o,
            high=h,
            low=l,
            last=c,
            volume=v,
        )

    return out


def fetch_stooq_live_quotes(
    symbols: Iterable[str],
    session: Optional[requests.Session] = None,
    timeout: float = 8.0,
) -> Dict[str, StooqLiveQuote]:
    """Fetch *latest* quotes from Stooq for one or many symbols.

    Stooq supports multiple tickers by concatenating them with '+':
      https://stooq.pl/q/l/?s=KGH+PKN&e=xml

    Returns dict keyed by UPPERCASE symbol.
    """

    syms = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not syms:
        return {}

    url = "https://stooq.pl/q/l/?s=" + "+".join(syms) + "&e=xml"

    close_session = False
    if session is None:
        session = requests.Session()
        close_session = True

    try:
        r = session.get(url, timeout=timeout, headers={"User-Agent": "gpw-scan/1.0"})
        r.raise_for_status()
        return _parse_stooq_rows(r.text)
    finally:
        if close_session:
            session.close()


def upsert_today_bar_from_quote(df_d: pd.DataFrame, quote: StooqLiveQuote) -> pd.DataFrame:
    """Upsert today's intraday bar into a daily OHLCV dataframe."""

    if df_d is None or df_d.empty:
        return df_d

    idx = pd.Timestamp(quote.day)

    last = float(quote.last) if pd.notna(quote.last) else float("nan")
    o = float(quote.open) if pd.notna(quote.open) else last
    h = float(quote.high) if pd.notna(quote.high) else last
    l = float(quote.low) if pd.notna(quote.low) else last
    v = float(quote.volume) if pd.notna(quote.volume) else 0.0

    # keep OHLC sane
    if pd.notna(last):
        h = max(h, o, l, last)
        l = min(l, o, h, last)

    row = pd.DataFrame(
        {"open": [o], "high": [h], "low": [l], "close": [last], "vol": [v]},
        index=pd.DatetimeIndex([idx], name=df_d.index.name or "date"),
    )

    out = df_d.copy()
    if idx in out.index:
        out.loc[idx, ["open", "high", "low", "close", "vol"]] = row.iloc[0].values
    else:
        out = pd.concat([out, row]).sort_index()

    return out
