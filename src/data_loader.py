from __future__ import annotations

import io
import os
import re
import zipfile
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd

COLS = ["ticker", "per", "date", "time", "open", "high", "low", "close", "vol", "openint"]


def norm_ticker(x: str) -> str:
    x = str(x).strip().upper().replace(".PL", "")
    return re.sub(r"[^A-Z0-9]", "", x)


def load_gpw_list_from_bytes(content: bytes) -> pd.DataFrame:
    rows = []
    text = content.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        for sep in ["|", "; ", ";", ",", "\t"]:
            if sep in ln:
                a, b = ln.split(sep, 1)
                rows.append((a.strip(), b.strip()))
                break
        else:
            rows.append((ln, ln))
    df = pd.DataFrame(rows, columns=["Symbol", "Nazwa"])
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    df["Nazwa"] = df["Nazwa"].astype(str).str.strip()
    df["Key"] = df["Symbol"].map(norm_ticker)
    return df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)


def open_zip_from_bytes(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content), "r")


def build_zip_index(zip_obj: zipfile.ZipFile) -> Dict[str, str]:
    index: Dict[str, str] = {}
    members = [m for m in zip_obj.namelist() if m.lower().endswith(".txt")]
    for member in members:
        base = os.path.basename(member)
        ticker = os.path.splitext(base)[0].upper()
        key = norm_ticker(ticker)
        if key and key not in index:
            index[key] = member
    return index


def parse_stooq_ascii_lines(lines: Iterable[str]) -> Tuple[pd.DataFrame, Optional[str]]:
    good = []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("<TICKER>") or ln.startswith("#"):
            continue
        parts = ln.split(",")
        if len(parts) != 10 or parts[1] != "D":
            continue
        if not re.fullmatch(r"\d{8}", parts[2]):
            continue
        good.append(parts)

    if not good:
        return pd.DataFrame(columns=["open", "high", "low", "close", "vol"]), None

    df = pd.DataFrame(good, columns=COLS)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    for col in ["open", "high", "low", "close", "vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").set_index("date")
    ticker_from_file = str(df["ticker"].iloc[-1]).upper() if len(df) else None
    return df[["open", "high", "low", "close", "vol"]].copy(), ticker_from_file


def load_daily_from_zip(zip_obj: zipfile.ZipFile, member_name: str) -> Tuple[pd.DataFrame, Optional[str]]:
    raw = zip_obj.read(member_name).decode("utf-8", errors="ignore").splitlines()
    return parse_stooq_ascii_lines(raw)
