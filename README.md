# GPW_SCAN v19b — Streamlit (Swing D1)

Repozytorium zawiera wersję **cloud-ready** skanera GPW (D1-only) z GUI w **Streamlit**.

## Co robi aplikacja
- Uploadujesz:
  1) ZIP ze Stooq (pliki TXT w formacie Stooq)
  2) listę spółek (np. `wig_lista.txt`) w formacie: `SYMBOL|Nazwa` (separator: `| ; , \t`)
- Aplikacja liczy:
  - Score10 / Score4 (D1: close)
  - EMA10D / EMA30D (konfigurowalne)
  - Return_20D / Return_60D
  - MACD(D), ADX(D), ATR(D), Donchian(D)
  - RSI Wilder(14) i Wilder(10)
  - Quality gauges: TQ / PQ / RQ (percentyle w obrębie raportu)
- Generuje:
  - Excel: `gpw_ranking_with_errors.xlsx`
  - Interaktywny HTML: `report_interactive.html` (Plotly z payloadem)

## Uruchomienie lokalne
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deployment (na szybko)
- Streamlit Community Cloud / Hugging Face Spaces (Streamlit):
  - wrzuć repo na GitHub
  - wskaż `app.py`
  - ustaw `requirements.txt`

## Dane wejściowe
### ZIP (Stooq)
W środku pliki `.txt` z liniami CSV:
`<TICKER>,D,YYYYMMDD,000000,open,high,low,close,vol,openint`

### Lista spółek
Przykład (`wig_lista.txt`):
```
PKN|ORLEN
KGH|KGHM
...
```

## Licencja
Do użytku własnego. Zrób co chcesz, ale pamiętaj o ryzyku inwestycyjnym :)
