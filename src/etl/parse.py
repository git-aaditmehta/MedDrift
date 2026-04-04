import os
import pandas as pd
import logging
from config import DATA_RAW_PATH, TARGET_DRUGS

logger = logging.getLogger(__name__)

# ── Column Definitions ────────────────────────────────────
# FAERS ASCII files have fixed columns — we only keep what we need
DEMO_COLS = ['primaryid', 'caseid', 'age', 'age_cod', 
             'sex', 'wt', 'event_dt', 'occr_country', 'rept_cod']

DRUG_COLS = ['primaryid', 'drugname', 'role_cod', 
             'dose_amt', 'dose_unit', 'route']

REAC_COLS = ['primaryid', 'pt', 'outc_cod']

OUTC_COLS = ['primaryid', 'outc_cod']

RPSR_COLS = ['primaryid', 'rpsr_cod']

# ── File prefix map per table ─────────────────────────────
FILE_PREFIX = {
    'demo': 'DEMO',
    'drug': 'DRUG',
    'reac': 'REAC',
    'outc': 'OUTC',
    'rpsr': 'RPSR'
}

def find_file(extract_dir: str, prefix: str) -> str:
    """
    Finds the ASCII file for a given table prefix.
    Searches both the extract directory and an ASCII subdirectory.
    """
    # Check for ASCII subdirectory first (most quarters have this)
    ascii_dir = os.path.join(extract_dir, 'ASCII')
    search_dir = ascii_dir if os.path.exists(ascii_dir) else extract_dir
    
    for fname in os.listdir(search_dir):
        if fname.upper().startswith(prefix) and fname.upper().endswith('.TXT'):
            return os.path.join(search_dir, fname)
    return None

def clean_drug_name(name: str) -> str:
    """
    Standardizes drug names:
    - Lowercase
    - Strip dose information e.g. 'aspirin 100mg' -> 'aspirin'
    - Strip special characters
    """
    if pd.isna(name):
        return None
    name = str(name).lower().strip()
    # Remove dose patterns like '100mg', '50 mg', '0.5mg'
    import re
    name = re.sub(r'\d+\.?\d*\s*(mg|mcg|ml|g|iu|%)', '', name)
    name = re.sub(r'[^a-z0-9\s]', '', name)
    return name.strip()

def parse_table(extract_dir: str, table: str, cols: list) -> pd.DataFrame:
    """
    Parses a single FAERS ASCII file into a dataframe.
    Returns cleaned dataframe with only required columns.
    """
    prefix = FILE_PREFIX[table]
    filepath = find_file(extract_dir, prefix)

    if not filepath:
        logger.warning(f"File not found for {prefix} in {extract_dir}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(
            filepath,
            sep='$',              # FAERS uses $ as delimiter
            encoding='latin-1',   # FDA files use latin-1 encoding
            dtype=str,            # read everything as string first
            low_memory=False
        )

        # Normalize column names to lowercase
        df.columns = df.columns.str.lower()

        # Keep only columns we need, ignore missing ones
        available = [c for c in cols if c in df.columns]
        df = df[available]

        # Apply drug name cleaning if this is the drug table
        if table == 'drug' and 'drugname' in df.columns:
            df['drugname'] = df['drugname'].apply(clean_drug_name)

        logger.info(f"Parsed {table.upper()}: {len(df)} rows from {os.path.basename(filepath)}")
        return df

    except Exception as e:
        logger.error(f"Error parsing {filepath}: {e}")
        return pd.DataFrame()

def parse_quarter(extract_dir: str) -> dict:
    """
    Parses all five FAERS tables for a single quarter.
    Returns dictionary of dataframes keyed by table name.
    """
    return {
        'demo': parse_table(extract_dir, 'demo', DEMO_COLS),
        'drug': parse_table(extract_dir, 'drug', DRUG_COLS),
        'reac': parse_table(extract_dir, 'reac', REAC_COLS),
        'outc': parse_table(extract_dir, 'outc', OUTC_COLS),
        'rpsr': parse_table(extract_dir, 'rpsr', RPSR_COLS)
    }