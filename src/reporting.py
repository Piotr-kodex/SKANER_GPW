from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd


def _apply_number_formats(workbook, worksheet, df: pd.DataFrame):
    money_cols = {"D_close", "EMA_fast_D", "EMA_slow_D", "DonchianU_20", "DonchianU_20_prev", "DonchianL_20", "TurnoverApproxPLN_med20"}
    pct_cols = {"Return_20D", "Return_60D", "ATR14_pct", "DistToEMA_fast_D", "DistToEMA_slow_D", "RS_60D", "TrendPersist40D"}
    num_cols = {"TQ", "PQ", "RQ", "ADX14", "VolSpikeRatio", "RSI14_D", "RSI10_D"}

    fmt_money = workbook.add_format({"num_format": '#,##0.00" PLN"'})
    fmt_pct = workbook.add_format({"num_format": '0.00%'})
    fmt_num = workbook.add_format({"num_format": '0.0'})

    for idx, col in enumerate(df.columns):
        width = min(max(len(str(col)), 12) + 2, 42)
        if col in money_cols:
            worksheet.set_column(idx, idx, width, fmt_money)
        elif col in pct_cols:
            worksheet.set_column(idx, idx, width, fmt_pct)
        elif col in num_cols:
            worksheet.set_column(idx, idx, width, fmt_num)
        else:
            worksheet.set_column(idx, idx, width)


def make_excel_bytes(artifacts) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        sheets = {
            "Ranking": artifacts.df_rank,
            "Leaders": artifacts.df_leaders,
            "Breakouts_Watch": artifacts.df_breakouts_watch,
            "Breakouts_Strict": artifacts.df_breakouts_strict,
            "Pullbacks": artifacts.df_pullbacks,
            "Errors": artifacts.df_err,
        }
        for sheet_name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            _apply_number_formats(writer.book, writer.sheets[sheet_name], df)
    output.seek(0)
    return output.read()


def make_audit_jsonl_bytes(audit_rows: list[dict[str, Any]]) -> bytes:
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in audit_rows) + "\n"
    return payload.encode("utf-8")


def make_summary_html(artifacts) -> bytes:
    counts = artifacts.summary.get("counts", {})
    html = f"""
    <html>
    <head><meta charset="utf-8"><title>GPW_SCAN Summary</title></head>
    <body style="font-family: Arial, sans-serif; margin: 24px;">
      <h1>GPW_SCAN Streamlit — Summary</h1>
      <p><b>Run UTC:</b> {artifacts.summary.get('run_ts_utc', '—')}</p>
      <ul>
        <li>Ranking rows: {counts.get('rank_rows', 0)}</li>
        <li>Errors rows: {counts.get('errors_rows', 0)}</li>
        <li>Leaders: {counts.get('leaders', 0)}</li>
        <li>Breakouts Watch: {counts.get('breakouts_watch', 0)}</li>
        <li>Breakouts Strict: {counts.get('breakouts_strict', 0)}</li>
        <li>Pullbacks: {counts.get('pullbacks', 0)}</li>
      </ul>
    </body>
    </html>
    """
    return html.encode("utf-8")
