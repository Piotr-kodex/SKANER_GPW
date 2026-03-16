# -*- coding: utf-8 -*-
from __future__ import annotations

import numpy as np


def default_config() -> dict:
    """
    Konfiguracja bazowa. UI Streamlit robi patch (nadpisywanie wybranych kluczy).
    Wszystkie parametry trzymamy w jednym miejscu (łatwe przenoszenie / testowanie).

    Uwaga dot. "dzisiejszej" świecy D1:
    - ZIP Stooq = historyczne dane EOD.
    - Opcjonalnie dokładamy dzisiejszą świecę *w trakcie sesji* z endpointu Stooq /q/l
      (close w odpowiedzi = last price). To wpływa na wykresy D1 i – jeżeli zostawisz
      włączone – także na scoring/Returny liczone na bazie ostatniego punktu.
    - Weekly świeca nadal jest „ostatni zamknięty tydzień” (mechanizm dropuje
      niezamknięty tydzień).
    """

    return {
        # ============ LIVE (dzisiejsza świeca D1) ============
        # Czy próbować dołożyć dzisiejszą świecę do danych D1 (intraday).
        "INCLUDE_TODAY_INTRADAY": True,
        # Provider (na razie tylko stooq)
        "TODAY_QUOTE_PROVIDER": "stooq",
        # Timeout na pojedynczy request do quote endpointu.
        "TODAY_QUOTE_TIMEOUT": 8.0,

        # Swing 3–6 tygodni -> wystarczy kilka miesięcy danych
        "D_LOOKBACK_DAYS": 180,
        # weekly tylko do poglądu na wykresie
        "W_LOOKBACK_DAYS": 360,

        # Kanał wybicia (D1)
        "DONCHIAN_N": 20,

        # Trend/zmienność/siła trendu (D1)
        "ADX_N": 14,
        "ATR_N": 14,
        "VOL_SMA_N": 20,

        # MACD (D1)
        "MACD_FAST": 12,
        "MACD_SLOW": 26,
        "MACD_SIGNAL": 9,

        # Momentum (D1)
        "RETURN_20D": 20,
        "RETURN_60D": 60,

        # Trend daily (Twoja preferencja)
        "EMA_FAST_D": 10,
        "EMA_SLOW_D": 30,

        # KPI payload (wykresy)
        "PAYLOAD_WEEKLY_TAIL": 80,
        "PAYLOAD_DAILY_TAIL": 260,

        # Płynność (proxy close*vol)
        "TURNOVER_WINDOW": 20,
        "MIN_TURNOVER_APPROX_PLN_MED20": 20_000,        # Liquid_Soft
        "MIN_TURNOVER_APPROX_PLN_MED20_STRICT": 50_000, # Liquid_OK

        # Breakout definicja (D1)
        "BREAKOUT_MODE": "close_near",   # close_near lub high_touch
        "CLOSE_NEAR_MULT": 0.995,

        # Benchmark (opcjonalnie, do RS)
        "BENCHMARK_SYMBOL": "WIG",

        # Trend persist na daily
        "TREND_PERSIST_DAYS": 40,    # ~8 tygodni sesji

        # Pullback do EMA (D1)
        "PULLBACK_PCT_TO_EMA_FAST_D": 0.04,  # 4% do EMA10D
        "PULLBACK_PCT_TO_EMA_SLOW_D": 0.06,  # 6% do EMA30D

        # Listy
        "LEADERS_SCORE10_MIN": 8,
        "PULLBACKS_SCORE10_MIN": 7,
        "BREAKOUTS_WATCH_SCORE10_MIN": 5,
        "BREAKOUTS_STRICT_SCORE10_MIN": 7,
        "VOL_SPIKE_MULT_STRICT": 1.1,

        # Score10: progi
        "SCORE10_ADX_THRESHOLD": 18,
        "SCORE10_DONCHIAN_NEAR_MULT": 0.99,
        "SCORE10_DONCHIAN_POS_THRESHOLD": 0.75,

        # Score4: progi
        "SCORE4_ADX_THRESHOLD": 18,

        # ADX line in charts
        "ADX_REF_LINE": 18,

        # Sort (swing)
        "SORT_COLUMNS": ["Score10", "Score4", "Return_60D", "Return_20D", "ADX14", "TurnoverApproxPLN_med20"],
        "SORT_ASC":     [False,     False,    False,       False,       False,   False],

        # Excel formats
        "PLN_FORMAT": '#,##0.00" PLN"',
        "PCT_FORMAT": "0.00%",
        "NUM_FORMAT": "0.0",

        # Quality: percentyle względem spółek w raporcie
        "QUALITY_W": {
            "TQ": {"Score10": 0.50, "TrendPersist40D": 0.30, "ADX14": 0.20},
            "PQ": {"TurnoverApproxPLN_med20": 0.65, "VolSpikeRatio": 0.20, "LiquidBonus": 0.15},
            "RQ": {"ATR14_pct_low": 0.60, "Heat_low": 0.40},
        },

        "QUALITY_LABELS": {
            "TQ": [(85, "Elite"), (70, "Solid"), (50, "Mixed"), (-np.inf, "Weak")],
            "PQ": [(80, "Institutional"), (55, "Tradable"), (-np.inf, "Thin")],
            "RQ": [(80, "Smooth"), (55, "Normal"), (-np.inf, "Wild")],
        },

        "GAUGE_THRESHOLDS": {"RED_LT": 50, "YELLOW_LE": 75},
        "TOP_N_TABLES": 30,

        # Highlight w Excelu
        "HIGHLIGHT_RULES": {
            "STRONG": {"Score10": [10], "Score4": [4]},
            "GOOD": {"Score10": [9, 8], "Score4": [4]},
            "FILL_STRONG": "00A9D08E",
            "FILL_GOOD": "00C6EFCE",
        },
    }


def deep_update(d: dict, u: dict) -> dict:
    out = dict(d)
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_update(out[k], v)
        else:
            out[k] = v
    return out
