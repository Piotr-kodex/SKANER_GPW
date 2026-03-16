\
# -*- coding: utf-8 -*-
from __future__ import annotations
import io, os, re, zipfile
import pandas as pd
from .utils import norm_ticker

COLS = ["ticker","per","date","time","open","high","low","close","vol","openint"]

def load_gpw_list_from_bytes(list_bytes: bytes) -> pd.DataFrame:
    """
    Lista w stylu:
      SYMBOL|Nazwa
    Separator: | ; , tab
    Jeśli tylko SYMBOL, Nazwa=SYMBOL.
    """
    txt = list_bytes.decode("utf-8", errors="ignore")
    rows = []
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        for sep in ["|", "; ", ";", ",", "\t"]:
            if sep in ln:
                a, b = ln.split(sep, 1)
                rows.append((a.strip(), b.strip()))
                break
        else:
            rows.append((ln.strip(), ln.strip()))
    df = pd.DataFrame(rows, columns=["Symbol", "Nazwa"])
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    df["Nazwa"]  = df["Nazwa"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)
    df["Key"] = df["Symbol"].map(norm_ticker)
    return df

def open_zip_from_bytes(zip_bytes: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(zip_bytes), "r")

def build_zip_index(z: zipfile.ZipFile) -> dict:
    """
    Mapuje norm_ticker(filename_without_ext) -> member_name
    """
    members_all = [m for m in z.namelist() if m.lower().endswith(".txt")]
    zip_index = {}
    for m in members_all:
        base = os.path.basename(m)
        t = os.path.splitext(base)[0].upper()
        key = norm_ticker(t)
        if key and key not in zip_index:
            zip_index[key] = m
    return zip_index

def parse_stooq_ascii_lines(lines):
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
        return pd.DataFrame(columns=["open","high","low","close","vol"]), None

    df = pd.DataFrame(good, columns=COLS)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    for c in ["open","high","low","close","vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["date","close"]).sort_values("date").set_index("date")
    ticker_from_file = str(df["ticker"].iloc[-1]).upper() if len(df) else None
    return df[["open","high","low","close","vol"]].copy(), ticker_from_file

def load_daily_from_zip(z: zipfile.ZipFile, member_name: str):
    raw = z.read(member_name).decode("utf-8", errors="ignore").splitlines()
    return parse_stooq_ascii_lines(raw)
