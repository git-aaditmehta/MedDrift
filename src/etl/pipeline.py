import os
import logging
import mysql.connector
from src.etl.download import download_all_quarters
from src.etl.parse import parse_quarter
from src.etl.load import load_quarter, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

def run_pipeline(skip_download: bool = False) -> None:
    """
    Master ETL pipeline for MedDrift.
    
    Steps:
    1. Download all FAERS quarters (skippable if already done)
    2. Parse each quarter's ASCII files
    3. Load into MySQL
    """
    # ── Step 1: Download ──────────────────────────────────
    if skip_download:
        logger.info("Skipping download — using existing raw data")
        from config import DATA_RAW_PATH, START_YEAR, END_YEAR, QUARTERS
        extracted_dirs = []
        for year in range(START_YEAR, END_YEAR + 1):
            for quarter in QUARTERS:
                path = os.path.join(
                    DATA_RAW_PATH,
                    f"faers_ascii_{year}{quarter}"
                )
                if os.path.exists(path):
                    extracted_dirs.append(path)
                else:
                    logger.warning(f"Missing quarter: {year}{quarter}")
    else:
        extracted_dirs = download_all_quarters()

    logger.info(f"Processing {len(extracted_dirs)} quarters")

    # ── Step 2 & 3: Parse + Load ──────────────────────────
    connection = get_connection()

    try:
        for extract_dir in extracted_dirs:
            quarter_name = os.path.basename(extract_dir)
            logger.info(f"Processing: {quarter_name}")

            # Parse all five tables for this quarter
            tables = parse_quarter(extract_dir)

            # Load into MySQL
            load_quarter(tables, connection)

            logger.info(f"Completed: {quarter_name}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise

    finally:
        connection.close()
        logger.info("Pipeline complete. MySQL connection closed.")

if __name__ == "__main__":
    # skip_download=True since we already have all 20 quarters
    run_pipeline(skip_download=True)