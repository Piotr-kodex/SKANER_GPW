import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    # Fallback to Streamlit secrets if environment variables are not set
    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        pass

if not url or not key:
    raise ValueError("Supabase URL and Key must be set in environment variables or Streamlit secrets.")

supabase: Client = create_client(url, key)

BUCKET_NAME = "notowania"

def upload_file(file_path: str, destination_path: str):
    """
    Uploads a file to a Supabase storage bucket.
    """
    try:
        with open(file_path, 'rb') as f:
            supabase.storage.from_(BUCKET_NAME).upload(destination_path, f.read())
        print(f"Successfully uploaded {file_path} to {destination_path}")
    except Exception as e:
        # Handle cases where the file might already exist
        if "Duplicate" in str(e):
            print(f"File {destination_path} already exists in Supabase, skipping upload.")
        else:
            print(f"Error uploading {file_path}: {e}")


def download_file(source_path: str, destination_path: str):
    """
    Downloads a file from a Supabase storage bucket.
    """
    try:
        with open(destination_path, 'wb+') as f:
            res = supabase.storage.from_(BUCKET_NAME).download(source_path)
            f.write(res)
        print(f"Successfully downloaded {source_path} to {destination_path}")
    except Exception as e:
        print(f"Error downloading {source_path}: {e}")

def list_files(path: str = ""):
    """
    Lists ALL files in a directory in the Supabase storage bucket using pagination.
    """
    all_files = []
    offset = 0
    limit = 1000  # Pobieramy po 1000 plików na raz (maksimum dla Supabase to zazwyczaj 1000)

    while True:
        try:
            results = supabase.storage.from_(BUCKET_NAME).list(path, {"limit": limit, "offset": offset})
            
            if not results:
                break
                
            all_files.extend(results)
            
            # Jeśli pobrano mniej niż limit, to znaczy, że to już koniec
            if len(results) < limit:
                break
                
            offset += limit
            
        except Exception as e:
            print(f"Error listing files in {path} (offset {offset}): {e}")
            # W razie błędu zwracamy to co udało się pobrać lub pustą listę, 
            # ale bezpieczniej przerwać pętlę
            break
            
    return all_files

def upload_file_bytes(data: bytes, destination_path: str):
    """
    Uploads bytes to a file in a Supabase storage bucket.
    """
    try:
        supabase.storage.from_(BUCKET_NAME).upload(destination_path, data)
        print(f"Successfully uploaded bytes to {destination_path}")
    except Exception as e:
        if "Duplicate" in str(e):
            print(f"File {destination_path} already exists in Supabase, skipping upload.")
        else:
            print(f"Error uploading to {destination_path}: {e}")

def download_file_bytes(source_path: str) -> bytes | None:
    """
    Downloads a file as bytes from a Supabase storage bucket.
    """
    try:
        res = supabase.storage.from_(BUCKET_NAME).download(source_path)
        return res
    except Exception as e:
        print(f"Error downloading {source_path}: {e}")
        return None

def delete_files(file_paths: list[str]):
    """
    Deletes a list of files from the Supabase storage bucket.
    """
    if not file_paths:
        return
    try:
        supabase.storage.from_(BUCKET_NAME).remove(file_paths)
        print(f"Successfully deleted {len(file_paths)} files.")
    except Exception as e:
        print(f"Error deleting files: {e}")
