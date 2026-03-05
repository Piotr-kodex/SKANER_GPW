\
# -*- coding: utf-8 -*-
from __future__ import annotations

import streamlit as st
from gpw_scan.config import default_config, deep_update
from gpw_scan.engine import run_gpw_scan

st.set_page_config(page_title="GPW_SCAN v19b (D1)", layout="wide")

st.title("GPW_SCAN v19b — Swing (D1) • Streamlit")
st.caption("Upload ZIP (Stooq) + lista spółek → RUN → pobierz Excel/HTML + podgląd raportu.")

colA, colB = st.columns(2)
with colA:
    zip_file = st.file_uploader("1) ZIP ze Stooq (TXT w środku)", type=["zip"])
with colB:
    list_file = st.file_uploader("2) Lista spółek (wig_lista.txt lub CSV/TXT)", type=["txt", "csv"])

cfg0 = default_config()

with st.sidebar:
    st.header("Parametry (D1)")
    patch = {}

    patch["INCLUDE_TODAY_INTRADAY"] = st.checkbox(
        "Dociągaj dzisiejszą świecę (intraday) do danych D1",
        value=bool(cfg0.get("INCLUDE_TODAY_INTRADAY", True)),
        help=(
            "ZIP Stooq to EOD. Ta opcja dociąga dzisiejsze OHLCV z endpointu Stooq /q/l "
            "(w odpowiedzi close = last). Weekly pozostaje: ostatni zamknięty tydzień."
        ),
    )

    patch["TOP_N_TABLES"] = st.slider("TOP_N (tabele po lewej)", 10, 100, int(cfg0["TOP_N_TABLES"]), step=5)
    patch["BREAKOUT_MODE"] = st.selectbox("Breakout mode", ["close_near", "high_touch"], index=0)
    patch["CLOSE_NEAR_MULT"] = st.slider("close* (dla close_near)", 0.970, 1.020, float(cfg0["CLOSE_NEAR_MULT"]), step=0.001)

    patch["ADX_REF_LINE"] = st.slider("ADX linia na wykresie", 10, 40, int(cfg0["ADX_REF_LINE"]), step=1)
    patch["SCORE10_ADX_THRESHOLD"] = st.slider("ADX≥ (Score10)", 10, 30, int(cfg0["SCORE10_ADX_THRESHOLD"]), step=1)
    patch["SCORE4_ADX_THRESHOLD"] = patch["SCORE10_ADX_THRESHOLD"]

    patch["EMA_FAST_D"] = st.slider("EMA fast (D)", 5, 20, int(cfg0["EMA_FAST_D"]), step=1)
    patch["EMA_SLOW_D"] = st.slider("EMA slow (D)", 15, 60, int(cfg0["EMA_SLOW_D"]), step=1)

    st.divider()
    st.subheader("Listy (progi Score10)")
    patch["LEADERS_SCORE10_MIN"] = st.slider("Leaders ≥", 0, 10, int(cfg0["LEADERS_SCORE10_MIN"]), step=1)
    patch["BREAKOUTS_WATCH_SCORE10_MIN"] = st.slider("Breakouts Watch ≥", 0, 10, int(cfg0["BREAKOUTS_WATCH_SCORE10_MIN"]), step=1)
    patch["BREAKOUTS_STRICT_SCORE10_MIN"] = st.slider("Breakouts Strict ≥", 0, 10, int(cfg0["BREAKOUTS_STRICT_SCORE10_MIN"]), step=1)
    patch["PULLBACKS_SCORE10_MIN"] = st.slider("Pullbacks ≥", 0, 10, int(cfg0["PULLBACKS_SCORE10_MIN"]), step=1)

    st.divider()
    st.subheader("Płynność (proxy close*vol)")
    patch["MIN_TURNOVER_APPROX_PLN_MED20"] = st.number_input("Turn soft (Liquid_Soft)", min_value=0, value=int(cfg0["MIN_TURNOVER_APPROX_PLN_MED20"]), step=1000)
    patch["MIN_TURNOVER_APPROX_PLN_MED20_STRICT"] = st.number_input("Turn ok (Liquid_OK)", min_value=0, value=int(cfg0["MIN_TURNOVER_APPROX_PLN_MED20_STRICT"]), step=1000)

    st.caption("TurnoverApproxPLN_med20 = mediana(close*vol) z 20 sesji. Liquid_OK wymagane w Leaders/Pullbacks/Breakouts Strict.")

cfg = deep_update(cfg0, patch)

run = st.button("RUN — Skanuj GPW (D1)")

if run:
    if not zip_file or not list_file:
        st.error("Wgraj ZIP i listę spółek.")
    else:
        with st.spinner("Liczenie…"):
            res = run_gpw_scan(cfg, zip_file.getvalue(), list_file.getvalue())

        st.success("Gotowe.")

        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Ranking (top 25)")
            st.dataframe(res["df_rank"].head(25), use_container_width=True)
        with c2:
            st.subheader("Statystyki")
            st.json(res["meta"]["counts"])

        st.download_button(
            "Pobierz Excel",
            data=res["xlsx_bytes"],
            file_name="gpw_ranking_with_errors.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Pobierz HTML (interactive)",
            data=res["interactive_html_bytes"],
            file_name="report_interactive.html",
            mime="text/html",
        )
        st.download_button(
            "Pobierz audit.jsonl",
            data=res["audit_jsonl_bytes"],
            file_name="audit.jsonl",
            mime="application/jsonl",
        )

        st.divider()
        st.subheader("Podgląd interaktywnego HTML (wbudowany)")
        st.components.v1.html(res["interactive_html_bytes"].decode("utf-8"), height=900, scrolling=True)

        if len(res["df_err"]):
            st.divider()
            st.subheader("Errors (top 20)")
            st.dataframe(res["df_err"].head(20), use_container_width=True)
