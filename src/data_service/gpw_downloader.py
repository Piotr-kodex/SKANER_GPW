import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import io
import holidays
import concurrent.futures

from .supabase_client import upload_file_bytes, download_file_bytes, list_files, delete_files

# --- KONFIGURACJA ---
GPW_URL_TEMPLATE = "https://www.gpw.pl/archiwum-notowan?fetch=1&type=10&instrument=&date={date}"

# --- FUNKCJE POMOCNICZE ---

def get_existing_dates():
    """
    Skanuje bucket Supabase i zwraca zbiór (set) dat, dla których mamy już pliki.
    """
    files = list_files()
    existing_dates = set()
    for f in files:
        try:
            # Nazwa pliku: gpw_2026-03-04.parquet -> wyciągamy 2026-03-04
            filename = f.get('name')
            if not filename or not filename.startswith("gpw_") or not filename.endswith(".parquet"):
                continue
                
            date_str = filename.replace("gpw_", "").replace(".parquet", "")
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            existing_dates.add(dt)
        except ValueError:
            continue
    return existing_dates


def parse_gpw_content(content, date_obj):
    """
    Pomocnicza funkcja parsująca surowe bajty (HTML/XLS) do czystego DataFrame.
    Zwraca DataFrame lub None w przypadku błędu/braku danych.
    """
    try:
        # Próba odczytu jako Excel lub HTML (GPW miesza formaty)
        try:
            temp_df = pd.read_excel(io.BytesIO(content))
        except:
            dfs = pd.read_html(io.BytesIO(content), decimal=',', thousands=' ')
            if dfs:
                temp_df = dfs[0]
            else:
                return None

        # Czyszczenie nazw kolumn
        temp_df.columns = [c.strip() for c in temp_df.columns]

        # Weryfikacja struktury
        if 'Nazwa' in temp_df.columns and 'Kurs zamknięcia' in temp_df.columns:
            
            # Lista kolumn liczbowych do przetworzenia
            numeric_cols = ['Kurs zamknięcia', 'Kurs otwarcia', 'Kurs max', 'Kurs min', 'Wolumen']
            
            for col in numeric_cols:
                if col in temp_df.columns:
                    # Konwersja liczb (jeśli są stringami)
                    if temp_df[col].dtype == 'object':
                        temp_df[col] = temp_df[col].astype(str).str.replace(',', '.').str.replace(' ', '')
                        temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
            
            # Dodanie/Formatowanie daty
            temp_df['Data'] = pd.to_datetime(date_obj)
            
            # Zwracamy Data, Nazwa oraz dostępne kolumny liczbowe
            cols_to_return = ['Data', 'Nazwa'] + [c for c in numeric_cols if c in temp_df.columns]
            return temp_df[cols_to_return]
    except Exception:
        return None
    return None

def cleanup_old_files(days_back):
    """
    Usuwa pliki starsze niż days_back.
    """
    cutoff_date = datetime.now().date() - timedelta(days=days_back)
    
    existing_dates = get_existing_dates()
    files_to_delete = []
    
    for dt in existing_dates:
        if dt < cutoff_date:
            file_name = f"gpw_{dt.strftime('%Y-%m-%d')}.parquet"
            files_to_delete.append(file_name)
            
    if files_to_delete:
        print(f"Usuwanie {len(files_to_delete)} starych plików...")
        delete_files(files_to_delete)
        return len(files_to_delete)
    return 0

def download_data_incremental(days_back, progress_bar=None):
    """
    Pobiera TYLKO brakujące pliki z zadanego okresu, pomijając weekendy i święta.
    """
    # 1. Ustalenie zakresu dat, który nas interesuje
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)
    
    # Pobieramy polskie święta dla lat objętych zakresem
    years = list(range(start_date.year, end_date.year + 1))
    pl_holidays = holidays.PL(years=years)

    target_dates = set()
    for i in range(days_back + 1):
        d = end_date - timedelta(days=i)
        
        # 1. Pomijamy weekendy (0=Poniedziałek, 4=Piątek)
        if d.weekday() >= 5:
            continue
            
        # 2. Pomijamy święta państwowe
        if d in pl_holidays:
            continue
            
        target_dates.add(d)

    # 2. Sprawdzenie co już mamy w Supabase
    existing_dates = get_existing_dates()

    # 3. Wyznaczenie różnicy (co trzeba pobrać)
    missing_dates = sorted(list(target_dates - existing_dates))

    total_to_download = len(missing_dates)

    if total_to_download == 0:
        return 0

    downloaded_count = 0

    # 4. Pobieranie tylko brakujących
    for i, current_date in enumerate(missing_dates):
        date_str_url = current_date.strftime("%d-%m-%Y")  # URL format
        date_str_file = current_date.strftime("%Y-%m-%d")  # Filename format
        file_name = f"gpw_{date_str_file}.parquet"

        # Aktualizacja paska postępu
        if progress_bar:
            progress = (i + 1) / total_to_download
            progress_bar.progress(progress, text=f"Pobieranie braku: {date_str_url} ({i + 1}/{total_to_download})")

        url = GPW_URL_TEMPLATE.format(date=date_str_url)

        try:
            response = requests.get(url, timeout=10)
            # Zapisujemy tylko jeśli plik ma sensowną treść
            if response.status_code == 200 and len(response.content) > 1000:
                # PARSUJEMY OD RAZU DO PARQUET
                df_clean = parse_gpw_content(response.content, current_date)
                
                if df_clean is not None and not df_clean.empty:
                    # Zapis do bufora w pamięci
                    buffer = io.BytesIO()
                    df_clean.to_parquet(buffer, index=False)
                    buffer.seek(0)
                    
                    # Upload do Supabase
                    upload_file_bytes(buffer.getvalue(), file_name)
                    downloaded_count += 1
            else:
                # Nie zapisujemy pustego pliku, po prostu logujemy problem
                print(f"Pominięto (mały plik/brak danych): {date_str_url}")

            # Krótka pauza
            time.sleep(0.1)

        except Exception as e:
            print(f"Błąd pobierania {date_str_url}: {e}")
            continue

    return downloaded_count


def load_and_process_data():
    """
    Wczytuje wszystkie pliki .parquet z Supabase RÓWNOLEGLE.
    """
    files = list_files()  # Twoja funkcja listująca
    parquet_files = [f.get('name') for f in files if f.get('name', '').endswith(".parquet")]

    dfs = []

    # Funkcja pomocnicza dla jednego pliku
    def fetch_single_file(filename):
        try:
            # Tu używamy Twojej funkcji pobierającej bajty
            file_bytes = download_file_bytes(filename)
            if file_bytes:
                return pd.read_parquet(io.BytesIO(file_bytes))
        except Exception as e:
            print(f"Błąd przy pliku {filename}: {e}")
        return None

    # Uruchamiamy pobieranie równoległe (np. 10 wątków naraz)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        # map uruchamia funkcję fetch_single_file dla każdego elementu z listy parquet_files
        results = executor.map(fetch_single_file, parquet_files)

        # Zbieramy wyniki (pomijając None, czyli błędy)
        for df in results:
            if df is not None:
                dfs.append(df)

    if not dfs: return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    return df.sort_values(by=['Nazwa', 'Data'])


def prepare_data_for_strategy(df):
    """
    Przygotowuje dane do formatu wymaganego przez compute_row.
    Zmienia nazwy kolumn na angielskie (open, high, low, close, vol) i upewnia się co do typów.
    """
    if df.empty:
        return pd.DataFrame()

    # Mapa kolumn: PL -> EN
    col_map = {
        'Kurs otwarcia': 'open',
        'Kurs max': 'high',
        'Kurs min': 'low',
        'Kurs zamknięcia': 'close',
        'Wolumen': 'vol'
    }
    
    # Kopiujemy, żeby nie modyfikować oryginału w miejscu
    df_ready = df.copy()
    
    # Zmiana nazw kolumn
    df_ready.rename(columns=col_map, inplace=True)
    
    # Upewnienie się, że Data jest typu datetime
    if not pd.api.types.is_datetime64_any_dtype(df_ready['Data']):
        df_ready['Data'] = pd.to_datetime(df_ready['Data'])
        
    return df_ready
