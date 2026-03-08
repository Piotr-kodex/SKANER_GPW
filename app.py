from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import (
    config_to_bytes,
    deep_update,
    load_config_from_bytes,
    load_default_config,
    load_user_config,
    save_user_config,
)
from src.reporting import make_audit_jsonl_bytes, make_excel_bytes, make_summary_html
from src.scanner import ScanArtifacts, run_scan


st.set_page_config(page_title="GPW_SCAN Terminal", layout="wide", page_icon="📈")


# =========================
# Helpers: formatting / state
# =========================
def ensure_state() -> None:
    if "config" not in st.session_state:
        st.session_state.config = load_user_config()
    if "artifacts" not in st.session_state:
        st.session_state.artifacts = None
    if "selected_symbol" not in st.session_state:
        st.session_state.selected_symbol = None
    if "shortlist_mode" not in st.session_state:
        st.session_state.shortlist_mode = "leaders"
    if "run_nonce" not in st.session_state:
        st.session_state.run_nonce = 0
    if "return_range" not in st.session_state:
        st.session_state.return_range = None


def fmt_num(x: Any, digits: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{float(x):.{digits}f}"


def fmt_pct(x: Any, digits: int = 1) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{float(x) * 100:.{digits}f}%"


def fmt_pln(x: Any) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{float(x):,.0f} PLN".replace(",", " ")


def pick_selected_symbol(artifacts: ScanArtifacts) -> str | None:
    symbols = list(artifacts.interactive_store.keys())
    if not symbols:
        return None
    current = st.session_state.selected_symbol
    if current in symbols:
        return current
    if not artifacts.df_leaders.empty:
        return str(artifacts.df_leaders.iloc[0]["Symbol"])
    return symbols[0]


# =========================
# Styling
# =========================
def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --bg: #0b1020;
          --bg2: #111827;
          --panel: #0f172a;
          --panel2: #111827;
          --line: rgba(148,163,184,0.18);
          --line-soft: rgba(148,163,184,0.10);
          --text: #e5e7eb;
          --muted: #94a3b8;
          --green: #22c55e;
          --blue: #38bdf8;
          --yellow: #f59e0b;
          --red: #ef4444;
          --violet: #8b5cf6;
        }

        .stApp {
          background:
            radial-gradient(circle at top right, rgba(56,189,248,0.08), transparent 28%),
            radial-gradient(circle at left top, rgba(139,92,246,0.08), transparent 24%),
            linear-gradient(180deg, #090d18 0%, #0b1020 100%);
        }

        .block-container {
          padding-top: 1.1rem;
          padding-bottom: 2rem;
          max-width: 100%;
        }

        [data-testid="stSidebar"] {
          background: linear-gradient(180deg, rgba(17,24,39,0.98), rgba(15,23,42,0.98));
          border-right: 1px solid var(--line-soft);
        }

        .tv-header {
          display:flex;
          justify-content:space-between;
          align-items:flex-start;
          gap:16px;
          padding:18px 20px;
          background: linear-gradient(180deg, rgba(17,24,39,0.92), rgba(15,23,42,0.84));
          border:1px solid var(--line);
          border-radius:20px;
          box-shadow: 0 16px 40px rgba(0,0,0,0.24);
          margin-bottom: 14px;
        }
        .tv-kicker { font-size:11px; color:#7dd3fc; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; }
        .tv-title { font-size:28px; font-weight:900; color:var(--text); line-height:1.1; margin-top:4px; }
        .tv-sub { font-size:12px; color:var(--muted); margin-top:8px; max-width: 860px; }
        .tv-pills { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
        .tv-pill {
          font-size:11px; font-weight:800; color:#dbeafe;
          padding:7px 10px; border-radius:999px;
          border:1px solid var(--line); background: rgba(255,255,255,0.03);
        }

        .panel-card {
          background: linear-gradient(180deg, rgba(17,24,39,0.94), rgba(15,23,42,0.92));
          border: 1px solid var(--line);
          border-radius: 18px;
          padding: 14px 16px;
          box-shadow: 0 14px 36px rgba(0,0,0,0.18);
        }
        .panel-title { font-size:13px; font-weight:900; color:var(--text); }
        .panel-sub { font-size:12px; color:var(--muted); margin-top:4px; }

        .symbol-card {
          background: linear-gradient(180deg, rgba(255,255,255,0.014), rgba(255,255,255,0.008));
          border: 1px solid rgba(148,163,184,0.12);
          border-radius: 14px;
          padding: 10px 12px;
          margin-bottom: 8px;
          box-shadow: 0 6px 16px rgba(0,0,0,0.10);
          transition: all 0.18s ease;
        }
        .symbol-card:hover {
          border-color: rgba(96,165,250,0.20);
          background: linear-gradient(180deg, rgba(255,255,255,0.020), rgba(255,255,255,0.010));
        }
        .symbol-card.active {
          border-color: rgba(56,189,248,0.42);
          background: linear-gradient(180deg, rgba(56,189,248,0.085), rgba(255,255,255,0.012));
          box-shadow: 0 10px 24px rgba(2,132,199,0.10);
        }
        .symbol-head { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
        .symbol-ticker { font-size:17px; font-weight:800; color:#f8fafc; letter-spacing:0.02em; }
        .symbol-name { font-size:11px; color:var(--muted); margin-top:3px; line-height:1.25; }
        .symbol-score {
          min-width:56px; text-align:center; border-radius:12px; padding:6px 8px;
          background: rgba(56,189,248,0.07); border:1px solid rgba(56,189,248,0.16);
        }
        .symbol-score-lab { font-size:9px; color:#93c5fd; font-weight:800; letter-spacing:0.08em; }
        .symbol-score-val { font-size:16px; font-weight:900; color:#e0f2fe; line-height:1.05; }
        .badge-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }

        .symbol-stats {
          display:grid;
          grid-template-columns: repeat(3, minmax(0,1fr));
          gap:8px;
          margin-top: 10px;
        }
        .symbol-stat {
          border: 1px solid rgba(148,163,184,0.12);
          border-radius: 12px;
          padding: 8px 9px;
          background: rgba(255,255,255,0.018);
        }
        .symbol-stat-lab {
          font-size: 10px;
          line-height: 1.2;
          color: var(--muted);
          text-transform: uppercase;
          letter-spacing: 0.06em;
          font-weight: 700;
        }
        .symbol-stat-val {
          font-size: 13px;
          line-height: 1.25;
          color: #f8fafc;
          font-weight: 800;
          margin-top: 5px;
        }
        .symbol-stat-val.pos { color: #86efac; }
        .symbol-stat-val.neg { color: #fca5a5; }
        .symbol-open-btn {
          margin-top: 10px;
        }

        .btag {
          padding:5px 9px; border-radius:999px; font-size:11px; font-weight:800; border:1px solid transparent;
        }
        .b-green { background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.30); color:#86efac; }
        .b-blue { background: rgba(56,189,248,0.12); border-color: rgba(56,189,248,0.30); color:#7dd3fc; }
        .b-yellow { background: rgba(245,158,11,0.12); border-color: rgba(245,158,11,0.30); color:#fde68a; }
        .b-red { background: rgba(239,68,68,0.12); border-color: rgba(239,68,68,0.30); color:#fca5a5; }
        .b-gray { background: rgba(148,163,184,0.12); border-color: rgba(148,163,184,0.28); color:#cbd5e1; }

        .metric-grid {
          display:grid;
          grid-template-columns: repeat(5, minmax(0,1fr));
          gap:10px;
          margin-top:12px;
        }
        .metric-box {
          padding:11px 12px; border-radius:16px; border:1px solid var(--line);
          background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015));
        }
        .metric-lab { font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; }
        .metric-val { font-size:18px; color:#f8fafc; font-weight:900; line-height:1.15; margin-top:5px; }
        .metric-hint { font-size:11px; color:var(--muted); margin-top:4px; }

        .toolbar-note { font-size:12px; color:var(--muted); margin-top:4px; }

        .shortlist-pill {
          display:inline-block; padding:6px 10px; border-radius:999px; font-size:11px; font-weight:800;
          border:1px solid var(--line); background:rgba(255,255,255,0.03); color:#dbeafe;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <div class="tv-header">
          <div>
            <div class="tv-kicker">GPW_SCAN TERMINAL</div>
            <div class="tv-title">Momentum & Trend Dashboard</div>
            <div class="tv-sub">Dashboard do selekcji swingowych setupów na D1/Weekly. Ciemny układ inspirowany terminalami tradingowymi, shortlisty po lewej i pełna analiza wybranego waloru po prawej.</div>
          </div>
          <div class="tv-pills">
            <div class="tv-pill">📈 Trend</div>
            <div class="tv-pill">⚡ Momentum</div>
            <div class="tv-pill">🛡️ Risk</div>
            <div class="tv-pill">🇵🇱 GPW</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# Sidebar / config
# =========================
def config_panel() -> tuple[bytes | None, bytes | None, dict]:
    with st.sidebar:
        st.markdown("### ⚙️ Ustawienia")
        st.caption("Upload danych, konfiguracja skanera i eksport ustawień.")

        zip_file = st.file_uploader("ZIP Stooq", type=["zip"], key="zip_file")
        list_file = st.file_uploader("wig_lista.txt", type=["txt"], key="list_file")
        cfg_upload = st.file_uploader("Wczytaj config.json", type=["json"], key="cfg_upload")

        if cfg_upload is not None:
            try:
                loaded = load_config_from_bytes(cfg_upload.getvalue())
                st.session_state.config = deep_update(load_default_config(), loaded)
                st.success("Wczytano konfigurację JSON.")
            except Exception as exc:
                st.error(f"Błąd wczytywania configu: {exc}")

        cfg = dict(st.session_state.config)

        st.markdown("---")
        st.markdown("#### 🎯 Setup")
        c1, c2 = st.columns(2)
        cfg["BREAKOUT_MODE"] = c1.selectbox("Breakout", ["close_near", "high_touch"], index=["close_near", "high_touch"].index(cfg["BREAKOUT_MODE"]))
        cfg["CLOSE_NEAR_MULT"] = c2.number_input("close*", min_value=0.97, max_value=1.02, value=float(cfg["CLOSE_NEAR_MULT"]), step=0.001, format="%.3f")

        c3, c4, c5 = st.columns(3)
        cfg["EMA_FAST_D"] = c3.number_input("EMA fast", min_value=5, max_value=20, value=int(cfg["EMA_FAST_D"]))
        cfg["EMA_SLOW_D"] = c4.number_input("EMA slow", min_value=15, max_value=60, value=int(cfg["EMA_SLOW_D"]))
        cfg["ADX_REF_LINE"] = c5.number_input("ADX line", min_value=10, max_value=40, value=int(cfg["ADX_REF_LINE"]))

        st.markdown("#### 📋 Shortlisty")
        c6, c7, c8 = st.columns(3)
        cfg["LEADERS_SCORE10_MIN"] = c6.number_input("Leaders ≥", min_value=0, max_value=10, value=int(cfg["LEADERS_SCORE10_MIN"]))
        cfg["BREAKOUTS_WATCH_SCORE10_MIN"] = c7.number_input("Watch ≥", min_value=0, max_value=10, value=int(cfg["BREAKOUTS_WATCH_SCORE10_MIN"]))
        cfg["BREAKOUTS_STRICT_SCORE10_MIN"] = c8.number_input("Strict ≥", min_value=0, max_value=10, value=int(cfg["BREAKOUTS_STRICT_SCORE10_MIN"]))
        cfg["PULLBACKS_SCORE10_MIN"] = st.number_input("Pullbacks ≥", min_value=0, max_value=10, value=int(cfg["PULLBACKS_SCORE10_MIN"]))

        st.markdown("#### 💧 Płynność")
        c9, c10 = st.columns(2)
        cfg["MIN_TURNOVER_APPROX_PLN_MED20"] = c9.number_input("Turn soft", min_value=0, value=int(cfg["MIN_TURNOVER_APPROX_PLN_MED20"]), step=1000)
        cfg["MIN_TURNOVER_APPROX_PLN_MED20_STRICT"] = c10.number_input("Turn ok", min_value=0, value=int(cfg["MIN_TURNOVER_APPROX_PLN_MED20_STRICT"]), step=1000)

        st.markdown("#### 🧮 Widok")
        cfg["TOP_N_TABLES"] = st.slider("Top N", min_value=10, max_value=100, value=int(cfg["TOP_N_TABLES"]), step=5)
        cfg["SCORE10_ADX_THRESHOLD"] = st.slider("ADX threshold", min_value=10, max_value=30, value=int(cfg["SCORE10_ADX_THRESHOLD"]), step=1)
        cfg["SCORE4_ADX_THRESHOLD"] = cfg["SCORE10_ADX_THRESHOLD"]

        st.markdown("---")
        b1, b2 = st.columns(2)
        if b1.button("💾 Zapisz lokalnie", use_container_width=True):
            save_user_config(cfg)
            st.session_state.config = dict(cfg)
            st.success("Zapisano user_config.json")
        if b2.button("↺ Reset", use_container_width=True):
            st.session_state.config = load_default_config()
            st.rerun()

        st.download_button(
            "⬇️ Pobierz config.json",
            data=config_to_bytes(cfg),
            file_name="config.json",
            mime="application/json",
            use_container_width=True,
        )

        st.session_state.config = dict(cfg)
        return zip_file.getvalue() if zip_file else None, list_file.getvalue() if list_file else None, cfg


# =========================
# Run scan
# =========================
@st.cache_data(show_spinner=False)
def run_scan_cached(zip_bytes: bytes, list_bytes: bytes, cfg_json: str, nonce: int) -> ScanArtifacts:
    cfg = json.loads(cfg_json)
    return run_scan(zip_bytes, list_bytes, cfg)


# =========================
# Shortlist UI
# =========================
def shortlist_map(artifacts: ScanArtifacts) -> dict[str, tuple[str, pd.DataFrame, str]]:
    return {
        "leaders": ("Leaders", artifacts.df_leaders, "Liquid_OK=True oraz SCORE powyżej progu."),
        "watch": ("Watchlist", artifacts.df_breakouts_watch, "Breakout candidates do obserwacji."),
        "strict": ("Strict", artifacts.df_breakouts_strict, "Breakout + płynność + wolumen + MACD."),
        "pullbacks": ("Pullbacks", artifacts.df_pullbacks, "Spółki blisko EMA fast/slow w trendzie."),
    }


def get_badge_html(badges: list[dict[str, str]]) -> str:
    if not badges:
        return '<span class="btag b-gray">No tag</span>'
    classes = {"green": "b-green", "blue": "b-blue", "yellow": "b-yellow", "red": "b-red", "gray": "b-gray"}
    return "".join([f'<span class="btag {classes.get(b.get("kind"), "b-gray")}">{b.get("label", "Tag")}</span>' for b in badges])


def render_shortlist_controls(artifacts: ScanArtifacts) -> None:
    mapping = shortlist_map(artifacts)
    st.markdown('<div class="panel-card"><div class="panel-title">📋 Shortlisty</div><div class="panel-sub">Bardziej dyskretny panel selekcji. Najważniejsze: symbol, score, 1D close i 1D return.</div></div>', unsafe_allow_html=True)
    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)
    buttons = [
        (r1c1, "leaders", "Leaders"),
        (r1c2, "watch", "Watchlist"),
        (r2c1, "strict", "Strict"),
        (r2c2, "pullbacks", "Pullbacks"),
    ]
    for col, key, label in buttons:
        type_ = "primary" if st.session_state.shortlist_mode == key else "secondary"
        if col.button(label, use_container_width=True, type=type_):
            st.session_state.shortlist_mode = key

    title, df, desc = mapping[st.session_state.shortlist_mode]
    st.markdown(f'<div class="panel-card" style="margin-top:12px;"><div class="panel-title">{title}</div><div class="panel-sub">{desc}</div><div style="margin-top:8px;"><span class="shortlist-pill">Pozycji: {len(df)}</span></div></div>', unsafe_allow_html=True)

    if df is None or df.empty:
        st.info("Brak pozycji na wybranej shortliście.")
        return

    show_n = min(int(st.session_state.config["TOP_N_TABLES"]), len(df))
    for _, row in df.head(show_n).iterrows():
        sym = str(row["Symbol"])
        p = artifacts.interactive_store.get(sym, {})
        badges = p.get("badges", [])[:3]
        badges_html = get_badge_html(badges)
        daily = p.get("daily", {}) or {}
        closes = [x for x in (daily.get("close") or []) if x is not None]
        close_1d = closes[-1] if closes else row.get("D_close")
        ret_1d = None
        if len(closes) >= 2 and closes[-2] not in (None, 0):
            ret_1d = (float(closes[-1]) / float(closes[-2])) - 1.0

        active_class = " active" if st.session_state.selected_symbol == sym else ""
        ret_class = ""
        if ret_1d is not None and not pd.isna(ret_1d):
            ret_class = " pos" if ret_1d >= 0 else " neg"

        st.markdown(
            f"""
            <div class="symbol-card{active_class}">
              <div class="symbol-head">
                <div>
                  <div class="symbol-ticker">{sym}</div>
                  <div class="symbol-name">{row.get('Nazwa', '—')}</div>
                </div>
                <div class="symbol-score">
                  <div class="symbol-score-lab">SCORE</div>
                  <div class="symbol-score-val">{int(row.get('Score10', 0))}</div>
                </div>
              </div>
              <div class="badge-row">{badges_html}</div>
              <div class="symbol-stats">
                <div class="symbol-stat">
                  <div class="symbol-stat-lab">20D</div>
                  <div class="symbol-stat-val">{fmt_pct(row.get('Return_20D'))}</div>
                </div>
                <div class="symbol-stat">
                  <div class="symbol-stat-lab">1D Close</div>
                  <div class="symbol-stat-val">{fmt_pln(close_1d)}</div>
                </div>
                <div class="symbol-stat">
                  <div class="symbol-stat-lab">1D Return</div>
                  <div class="symbol-stat-val{ret_class}">{fmt_pct(ret_1d)}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        btn_type = "primary" if st.session_state.selected_symbol == sym else "secondary"
        if st.button(f"↗ Otwórz {sym}", key=f"open_{st.session_state.shortlist_mode}_{sym}", use_container_width=True, type=btn_type):
            st.session_state.selected_symbol = sym
            st.rerun()
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)


def metric_row(counts: dict[str, Any]) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Ranking", counts.get("rank_rows", 0))
    c2.metric("Errors", counts.get("errors_rows", 0))
    c3.metric("Leaders", counts.get("leaders", 0))
    c4.metric("Watchlist", counts.get("breakouts_watch", 0))
    c5.metric("Strict", counts.get("breakouts_strict", 0))
    c6.metric("Pullbacks", counts.get("pullbacks", 0))


# =========================
# Detail panel / charts
# =========================
def kpi_html(label: str, value: str, hint: str) -> str:
    return f'<div class="metric-box"><div class="metric-lab">{label}</div><div class="metric-val">{value}</div><div class="metric-hint">{hint}</div></div>'


def render_kpi_cards(payload: dict[str, Any]) -> None:
    k = payload.get("kpi", {})
    html = (
        '<div class="metric-grid">'
        + kpi_html("SCORE", str(k.get("Score10", "—")), "0–10 (trend + setup)")
        + kpi_html("1D Close", fmt_num(k.get("D_close"), 2), f"dzień: {k.get('D_last', '—')}")
        + kpi_html("Return 20D", fmt_pct(k.get("Return_20D")), "ok. 1 miesiąc")
        + kpi_html("Return 60D", fmt_pct(k.get("Return_60D")), "ok. 3 miesiące")
        + kpi_html("ADX14", fmt_num(k.get("ADX14"), 1), f"≥ {st.session_state.config['ADX_REF_LINE']} = trend")
        + kpi_html("ATR%", fmt_pct(k.get("ATR14_pct")), "zmienność")
        + kpi_html("RSI14 / RSI10", f"{fmt_num(k.get('RSI14_D'),1)} / {fmt_num(k.get('RSI10_D'),1)}", "OZ factor")
        + kpi_html("VolSpike", fmt_num(k.get("VolSpikeRatio"), 2), "D_vol / SMA20")
        + kpi_html("Turnover med20", fmt_pln(k.get("TurnoverApproxPLN_med20")), "close × vol")
        + kpi_html("TQ / PQ / RQ", f"{fmt_num(k.get('TQ'),0)} / {fmt_num(k.get('PQ'),0)} / {fmt_num(k.get('RQ'),0)}", f"{k.get('TQ_Label','—')} · {k.get('PQ_Label','—')} · {k.get('RQ_Label','—')}")
        + '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def nearest_daily_levels(dsr: dict[str, Any], last_close: float | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if last_close is None or pd.isna(last_close):
        return None, None
    supports = [
        {"key": "Swing Low", "y": dsr.get("swing_low"), "color": "#22c55e", "dash": "dot", "width": 2.0},
        {"key": "20D Low", "y": dsr.get("low_20"), "color": "#10b981", "dash": "dash", "width": 1.3},
        {"key": "60D Low", "y": dsr.get("low_60"), "color": "#06b6d4", "dash": "longdash", "width": 1.2},
    ]
    resistances = [
        {"key": "Swing High", "y": dsr.get("swing_high"), "color": "#ef4444", "dash": "dot", "width": 2.0},
        {"key": "20D High", "y": dsr.get("high_20"), "color": "#f59e0b", "dash": "dash", "width": 1.3},
        {"key": "60D High", "y": dsr.get("high_60"), "color": "#8b5cf6", "dash": "longdash", "width": 1.2},
    ]
    supports = [x for x in supports if x["y"] is not None and not pd.isna(x["y"]) and x["y"] <= last_close]
    resistances = [x for x in resistances if x["y"] is not None and not pd.isna(x["y"]) and x["y"] >= last_close]
    supports.sort(key=lambda x: x["y"], reverse=True)
    resistances.sort(key=lambda x: x["y"])
    return (supports[0] if supports else None, resistances[0] if resistances else None)


COMMON_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font={"color": "#e5e7eb"},
    margin={"t": 14, "r": 110, "b": 40, "l": 60},
    hovermode="x unified",
    hoverlabel={
        "bgcolor": "rgba(15,23,42,0.92)",
        "bordercolor": "rgba(148,163,184,0.35)",
        "font": {"color": "#e5e7eb", "size": 12},
    },
    legend={"orientation": "h", "y": 1.12, "x": 0, "bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}},
)


def apply_layout(fig: go.Figure, y_title: str, x_title: str = "Date", with_slider: bool = False) -> go.Figure:
    fig.update_layout(**COMMON_LAYOUT)
    fig.update_xaxes(
        title=x_title,
        gridcolor="rgba(255,255,255,0.05)",
        zerolinecolor="rgba(255,255,255,0.05)",
        rangeslider_visible=with_slider,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="rgba(255,255,255,0.25)",
        spikethickness=1,
    )
    fig.update_yaxes(title=y_title, gridcolor="rgba(255,255,255,0.05)", zerolinecolor="rgba(255,255,255,0.05)")
    return fig


def chart_daily(payload: dict[str, Any], days: int) -> go.Figure:
    d = payload["daily"]
    x = d["dates"][-days:]
    open_ = d["open"][-days:]
    high = d["high"][-days:]
    low = d["low"][-days:]
    close = d["close"][-days:]
    ema_fast = d["ema_fast"][-days:]
    ema_slow = d["ema_slow"][-days:]
    dsr = d.get("sr", {})

    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=x, open=open_, high=high, low=low, close=close, name="OHLC (D)", increasing_line_color="#22c55e", decreasing_line_color="#ef4444"))
    fig.add_trace(go.Scatter(x=x, y=ema_fast, mode="lines", name=f"EMA{st.session_state.config['EMA_FAST_D']}D", line={"color": "#f59e0b", "width": 2.6}))
    fig.add_trace(go.Scatter(x=x, y=ema_slow, mode="lines", name=f"EMA{st.session_state.config['EMA_SLOW_D']}D", line={"color": "#60a5fa", "width": 3.0}))

    last_close = close[-1] if close else None
    support, resistance = nearest_daily_levels(dsr, last_close)
    for lvl, label in [(support, "Nearest Support"), (resistance, "Nearest Resistance")]:
        if lvl:
            fig.add_hline(y=lvl["y"], line_color=lvl["color"], line_dash=lvl["dash"], line_width=lvl["width"], annotation_text=f"{label} ({lvl['key']}) {lvl['y']:.2f}", annotation_position="top right")

    return apply_layout(fig, "Price", "Day", with_slider=True)


def chart_rsi(payload: dict[str, Any], days: int) -> go.Figure:
    d = payload["daily"]
    x = d["dates"][-days:]
    r14 = d["rsi14"][-days:]
    r10 = d["rsi10"][-days:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=r14, mode="lines", name="RSI14"))
    fig.add_trace(go.Scatter(x=x, y=r10, mode="lines", name="RSI10"))
    for level in [30, 50, 70]:
        fig.add_trace(go.Scatter(x=x, y=[level] * len(x), mode="lines", name=str(level), line={"dash": "dot"}))
    fig = apply_layout(fig, "RSI", "Day", with_slider=False)
    fig.update_yaxes(range=[0, 100])
    return fig


def chart_macd(payload: dict[str, Any], days: int) -> go.Figure:
    d = payload["daily"]
    x = d["dates"][-days:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=d["macd"][-days:], mode="lines", name="MACD(D)"))
    fig.add_trace(go.Scatter(x=x, y=d["macd_signal"][-days:], mode="lines", name="Signal"))
    fig.add_trace(go.Bar(x=x, y=d["macd_hist"][-days:], name="Hist"))
    return apply_layout(fig, "MACD", "Day", with_slider=False)


def chart_volume(payload: dict[str, Any], days: int) -> go.Figure:
    d = payload["daily"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["dates"][-days:], y=d["vol"][-days:], name="Vol"))
    return apply_layout(fig, "Volume", "Day", with_slider=False)


def chart_donchian(payload: dict[str, Any], days: int) -> go.Figure:
    d = payload["daily"]
    x = d["dates"][-days:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=d["close"][-days:], mode="lines", name="Close"))
    fig.add_trace(go.Scatter(x=x, y=d["don_u"][-days:], mode="lines", name="DonchianU"))
    fig.add_trace(go.Scatter(x=x, y=d["don_l"][-days:], mode="lines", name="DonchianL"))
    return apply_layout(fig, "Price", "Day", with_slider=False)


def chart_adx(payload: dict[str, Any], days: int) -> go.Figure:
    d = payload["daily"]
    x = d["dates"][-days:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=d["adx14"][-days:], mode="lines", name="ADX"))
    fig.add_trace(go.Scatter(x=x, y=[st.session_state.config["ADX_REF_LINE"]] * len(x), mode="lines", name=f"ADX={st.session_state.config['ADX_REF_LINE']}", line={"dash": "dot"}))
    return apply_layout(fig, "ADX", "Day", with_slider=False)


def chart_weekly(payload: dict[str, Any], weeks: int) -> go.Figure:
    w = payload["weekly"]
    x = w["dates"][-weeks:]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=x, open=w["open"][-weeks:], high=w["high"][-weeks:], low=w["low"][-weeks:], close=w["close"][-weeks:], name="OHLC (W)", increasing_line_color="#22c55e", decreasing_line_color="#ef4444"))
    sr = w.get("sr", {})
    levels = [
        (sr.get("swing_low"), "W Swing Low", "#22c55e", "dot", 2.0),
        (sr.get("swing_high"), "W Swing High", "#ef4444", "dot", 2.0),
        (sr.get("low_26"), "26W Low", "#10b981", "dash", 1.3),
        (sr.get("high_26"), "26W High", "#f59e0b", "dash", 1.3),
        (sr.get("low_52"), "52W Low", "#06b6d4", "longdash", 1.2),
        (sr.get("high_52"), "52W High", "#8b5cf6", "longdash", 1.2),
    ]
    for y, label, color, dash, width in levels:
        if y is not None and not pd.isna(y):
            fig.add_hline(y=y, line_color=color, line_dash=dash, line_width=width, annotation_text=f"{label} {y:.2f}", annotation_position="top right")
    return apply_layout(fig, "Price", "Week", with_slider=True)


def chart_return_rebased(payload: dict[str, Any], days: int) -> tuple[go.Figure, tuple[str, str] | None]:
    d = payload["daily"]
    x_all = d["dates"][-days:]
    c_all = d["close"][-days:]
    if not x_all or not c_all:
        return go.Figure(), None

    slider_key = f"return_range_{st.session_state.selected_symbol}_{days}"
    default_range = (x_all[0], x_all[-1])
    if slider_key not in st.session_state:
        st.session_state[slider_key] = default_range

    selected_range = st.select_slider(
        "Zakres Daily Return (relative)",
        options=x_all,
        value=st.session_state[slider_key],
        key=slider_key,
        label_visibility="collapsed",
    )

    start_idx = x_all.index(selected_range[0])
    end_idx = x_all.index(selected_range[1])
    if end_idx < start_idx:
        start_idx, end_idx = end_idx, start_idx

    x = x_all[start_idx:end_idx + 1]
    c = c_all[start_idx:end_idx + 1]
    base = None
    for val in c:
        if val is not None and not pd.isna(val) and float(val) != 0:
            base = float(val)
            break
    y = [((float(v) / base) - 1.0) * 100.0 if (base is not None and v is not None and not pd.isna(v)) else None for v in c]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Close"))
    fig.add_hline(y=0, line_color="rgba(148,163,184,0.55)", line_dash="dot")
    fig = apply_layout(fig, "Return %", "Day", with_slider=False)
    return fig, selected_range


def render_selected_symbol(artifacts: ScanArtifacts, payload: dict[str, Any]) -> None:
    sym = st.session_state.selected_symbol
    badges_html = get_badge_html(payload.get("badges", []))
    st.markdown(
        f"""
        <div class="panel-card">
          <div class="panel-title">🎯 Aktywny instrument</div>
          <div class="symbol-head" style="margin-top:10px;">
            <div>
              <div class="symbol-ticker">{sym}</div>
              <div class="symbol-name">{payload.get('Nazwa', '—')}</div>
            </div>
            <div class="symbol-score">
              <div class="symbol-score-lab">SCORE</div>
              <div class="symbol-score-val">{int(payload.get('kpi', {}).get('Score10', 0) or 0)}</div>
            </div>
          </div>
          <div class="badge-row">{badges_html}</div>
          <div class="toolbar-note">Prawy panel jest celowo szerszy, a wszystkie wykresy są pełnej szerokości jak Daily i Weekly.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_kpi_cards(payload)

    c1, c2 = st.columns(2)
    day_window = c1.select_slider("Okno Daily", options=[10, 20, 40, 60, 120], value=40)
    week_window = c2.select_slider("Okno Weekly", options=[30, 52], value=30)

    st.markdown('<div class="panel-card"><div class="panel-title">Daily Candles + EMA + Support / Resistance</div><div class="panel-sub">Na wykresie dziennym pokazane są tylko najbliższe wsparcie i najbliższy opór względem ceny.</div></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_daily(payload, day_window), use_container_width=True)

    st.markdown('<div class="panel-card"><div class="panel-title">Daily RSI (Wilder)</div></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_rsi(payload, day_window), use_container_width=True)

    st.markdown('<div class="panel-card"><div class="panel-title">Daily MACD</div></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_macd(payload, day_window), use_container_width=True)

    st.markdown('<div class="panel-card"><div class="panel-title">Daily Volume</div></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_volume(payload, day_window), use_container_width=True)

    st.markdown('<div class="panel-card"><div class="panel-title">Daily Donchian</div></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_donchian(payload, day_window), use_container_width=True)

    st.markdown('<div class="panel-card"><div class="panel-title">Daily ADX</div></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_adx(payload, day_window), use_container_width=True)

    st.markdown('<div class="panel-card"><div class="panel-title">Weekly Candles + Support / Resistance</div><div class="panel-sub">Weekly zostaje w szerokim układzie z pełnym range sliderem.</div></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_weekly(payload, week_window), use_container_width=True)

    st.markdown('<div class="panel-card"><div class="panel-title">Daily Return (relative)</div><div class="panel-sub">Seria jest przeliczana od aktualnie wybranego zakresu na suwaku pod wykresem. Początek zakresu zawsze = 0%.</div></div>', unsafe_allow_html=True)
    fig_ret, selected_range = chart_return_rebased(payload, day_window)
    st.plotly_chart(fig_ret, use_container_width=True)
    if selected_range:
        st.caption(f"Zakres return: {selected_range[0]} → {selected_range[1]}")

    with st.expander("Ranking / dane źródłowe dla wybranego symbolu"):
        row = artifacts.df_rank[artifacts.df_rank["Symbol"] == sym]
        if not row.empty:
            st.dataframe(row, use_container_width=True, hide_index=True)


# =========================
# Main
# =========================
def main() -> None:
    ensure_state()
    inject_css()
    render_header()

    zip_bytes, list_bytes, cfg = config_panel()

    top_left, top_right = st.columns([0.68, 3.02], gap="large")

    if zip_bytes and list_bytes:
        try:
            artifacts = run_scan_cached(zip_bytes, list_bytes, json.dumps(cfg, ensure_ascii=False, sort_keys=True), st.session_state.run_nonce)
            st.session_state.artifacts = artifacts
        except Exception as exc:
            st.error(f"Błąd skanowania: {exc}")
            st.stop()

    artifacts = st.session_state.artifacts
    if artifacts is None:
        st.info("Wgraj ZIP Stooq i wig_lista.txt w panelu po lewej, aby uruchomić skaner.")
        return

    with top_right:
        metric_row(artifacts.summary.get("counts", {}))

        download1, download2, download3 = st.columns(3)
        download1.download_button("⬇️ Excel", data=make_excel_bytes(artifacts), file_name="gpw_ranking.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        download2.download_button("⬇️ Summary HTML", data=make_summary_html(artifacts), file_name="summary.html", mime="text/html", use_container_width=True)
        download3.download_button("⬇️ Audit JSONL", data=make_audit_jsonl_bytes(artifacts.audit_rows), file_name="audit.jsonl", mime="application/json", use_container_width=True)

    with top_left:
        render_shortlist_controls(artifacts)
        st.markdown('<div class="panel-card" style="margin-top:12px;"><div class="panel-title">🔎 Pełna lista symboli</div><div class="panel-sub">Wyszukiwarka całego rankingu, niezależna od shortlisty.</div></div>', unsafe_allow_html=True)
        symbols = artifacts.df_rank["Symbol"].tolist() if not artifacts.df_rank.empty else []
        selected = st.selectbox("Wybierz symbol", options=symbols, index=symbols.index(pick_selected_symbol(artifacts)) if symbols and pick_selected_symbol(artifacts) in symbols else 0)
        if selected != st.session_state.selected_symbol:
            st.session_state.selected_symbol = selected
            st.rerun()

        if not artifacts.df_err.empty:
            with st.expander(f"⚠️ Errors ({len(artifacts.df_err)})"):
                st.dataframe(artifacts.df_err, use_container_width=True, hide_index=True)

    st.session_state.selected_symbol = pick_selected_symbol(artifacts)
    if st.session_state.selected_symbol is None:
        st.warning("Brak symboli do pokazania.")
        return

    payload = artifacts.interactive_store.get(st.session_state.selected_symbol)
    if payload is None:
        st.warning("Brak payloadu dla wybranego symbolu.")
        return

    with top_right:
        render_selected_symbol(artifacts, payload)


if __name__ == "__main__":
    main()
