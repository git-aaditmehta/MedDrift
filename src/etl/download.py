import os
import requests
import zipfile
import logging
from tqdm import tqdm
from config import DATA_RAW_PATH, START_YEAR, END_YEAR, QUARTERS

# ── Logging Setup ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ── FAERS Download URL Pattern ────────────────────────────
# FDA URL format: faers_ascii_2020q1.zip
BASE_URL = "https://fis.fda.gov/content/Exports/faers_ascii_{year}{quarter}.zip"

def download_faers_quarter(year: int, quarter: str, max_retries: int = 3) -> str:
    """
    Downloads a single FAERS quarterly ZIP file from FDA.
    Retries up to max_retries times on connection failure.
    Returns the local file path if successful.
    """
    filename = f"faers_ascii_{year}{quarter}.zip"
    local_path = os.path.join(DATA_RAW_PATH, filename)

    # Skip if already downloaded and valid
    if os.path.exists(local_path):
        try:
            with zipfile.ZipFile(local_path, "r") as z:
                z.namelist()
            logger.info(f"Already exists and valid, skipping: {filename}")
            return local_path
        except zipfile.BadZipFile:
            logger.warning(f"Corrupt ZIP found, re-downloading: {filename}")
            os.remove(local_path)

    url = BASE_URL.format(year=year, quarter=quarter)

    for attempt in range(1, max_retries + 1):
        logger.info(f"Downloading: {url} (attempt {attempt}/{max_retries})")
        try:
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            with open(local_path, "wb") as f, tqdm(
                desc=filename,
                total=total_size,
                unit="iB",
                unit_scale=True
            ) as progress:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    progress.update(len(chunk))

            logger.info(f"Downloaded successfully: {filename}")
            return local_path

        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:

            logger.warning(f"Attempt {attempt} failed: {e}")

            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"Removed incomplete file: {filename}")

            if attempt < max_retries:
                wait_time = 2 ** attempt  # 2s, 4s, 8s
                logger.info(f"Waiting {wait_time}s before retry...")
                import time
                time.sleep(wait_time)
            else:
                logger.error(f"All {max_retries} attempts failed for {filename}")
                return None

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for {filename}: {e}")
            return None

def extract_zip(zip_path: str) -> str:
    """
    Extracts a FAERS ZIP file into a quarter-specific subdirectory.
    Returns the extraction directory path.
    """
    # Create subdirectory named after the ZIP file
    extract_dir = zip_path.replace(".zip", "")
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)
        logger.info(f"Extracted to: {extract_dir}")

    return extract_dir

def download_all_quarters() -> list:
    """
    Downloads and extracts all FAERS quarters defined in config.
    Returns list of extraction directories.
    """
    os.makedirs(DATA_RAW_PATH, exist_ok=True)
    extracted_dirs = []

    for year in range(START_YEAR, END_YEAR + 1):
        for quarter in QUARTERS:
            zip_path = download_faers_quarter(year, quarter)
            if zip_path:
                extract_dir = extract_zip(zip_path)
                extracted_dirs.append(extract_dir)

    logger.info(f"Pipeline complete. {len(extracted_dirs)} quarters ready.")
    return extracted_dirs

if __name__ == "__main__":
    download_all_quarters()