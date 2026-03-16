\
# -*- coding: utf-8 -*-
from __future__ import annotations
import re
import numpy as np
import pandas as pd

def norm_ticker(x: str) -> str:
    x = str(x).strip().upper().replace(".PL", "")
    return re.sub(r"[^A-Z0-9]", "", x)

def to_float(x):
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
