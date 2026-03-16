<<<<<<< HEAD
# GPW_SCAN Streamlit

Pierwsza kompletna wersja projektu do analizy GPW w Streamlit, przygotowana na bazie Twojego skryptu `GPW_SCAN v20e`.

## Co robi aplikacja

- przyjmuje ZIP z danymi Stooq (`.txt` w środku)
- przyjmuje plik `wig_lista.txt`
- liczy ranking, Leaders, Breakouts i Pullbacks
- pokazuje dashboard wybranego instrumentu
- rysuje wykresy Plotly w Streamlit
- pozwala pobrać:
  - Excel
  - summary HTML
  - audit JSONL

## Struktura projektu

```text
app.py
requirements.txt
README.md
config/default_config.json
src/
  config.py
  data_loader.py
  indicators.py
  scanner.py
  reporting.py
```

## Uruchomienie lokalnie

```bash
python -m venv .venv
source .venv/bin/activate
=======
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
>>>>>>> origin/main
pip install -r requirements.txt
streamlit run app.py
```

<<<<<<< HEAD
Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Dane wejściowe

W aplikacji wgraj:

1. ZIP ze Stooq zawierający pliki `.txt` z notowaniami dziennymi
2. `wig_lista.txt`

Format listy może być np.:

```text
KGH | KGHM
PKN | Orlen
DNP | Dino Polska
```

lub po prostu:

```text
KGH
PKN
DNP
```

## Deploy na Streamlit Community Cloud

1. Utwórz repo na GitHubie.
2. Wrzuć wszystkie pliki projektu.
3. Wejdź do Streamlit Community Cloud.
4. Wskaż repozytorium i plik startowy `app.py`.
5. Deploy.

## Co jeszcze warto zrobić w kolejnym kroku

- dodać zapis/odczyt konfiguracji JSON z GUI
- dodać obsługę automatycznego pobierania danych
- dodać filtry sektorowe i benchmarki alternatywne
- dodać testy jednostkowe dla wskaźników
- dodać osobny moduł generowania interaktywnego raportu HTML

## Ważna uwaga

To jest pierwsza działająca wersja projektu. Największa zmiana względem Colaba polega na tym, że:

- nie ma `google.colab`
- nie ma `ipywidgets`
- wykresy są renderowane bezpośrednio przez Streamlit + Plotly
- dane wejściowe są dostarczane przez upload plików


## Zapis konfiguracji
Aplikacja obsługuje trzy sposoby pracy z konfiguracją:
- **Pobierz config.json** – eksport bieżących ustawień do pliku JSON.
- **Wczytaj konfigurację JSON** – import wcześniej zapisanego pliku.
- **Zapisz config w projekcie** – zapis do `config/user_config.json` wewnątrz projektu.

Uwaga: na Streamlit Community Cloud lokalny plik `user_config.json` może nie być trwały między restartami środowiska, dlatego najbezpieczniej przechowywać własny plik JSON lokalnie i wczytywać go przez GUI.
=======
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
>>>>>>> origin/main
