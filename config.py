import os

# ── Database ──────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

# Base directory — always points to MedDrift root regardless of where script is run
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED_PATH = os.path.join(BASE_DIR, "data", "processed")

# ── Data Source ───────────────────────────────────────────
# FAERS data has a 2-3 quarter publication lag
# Using 2020-2024 gives 20 complete, verified quarters
FAERS_BASE_URL = "https://fda.gov/files/drugs/published/faers-ascii-data-files-q"
DATA_RAW_PATH = "data/raw/"
DATA_PROCESSED_PATH = "data/processed/"

# ── Signal Detection Thresholds ───────────────────────────
# CUSUM: flags when cumulative deviation exceeds 5 (industry standard baseline)
CUSUM_THRESHOLD = 5

# EWMA: lambda=0.2 means 20% weight to recent, 80% to historical trend
# Balances sensitivity to new signals vs stability against noise
EWMA_LAMBDA = 0.2
EWMA_THRESHOLD = 3

# ── Statistical Validation ────────────────────────────────
# ROR > 2.0 = drug appears 2x more in this reaction than expected (WHO guideline)
ROR_THRESHOLD = 5.0

# p < 0.05 = less than 5% probability result occurred by chance
P_VALUE_THRESHOLD = 0.05

# chi-square test unreliable below 25 reports — small sample invalid
MIN_REPORT_COUNT = 25

# ── Analysis Scope ────────────────────────────────────────
START_YEAR = 2020
END_YEAR = 2024
QUARTERS = ["q1", "q2", "q3", "q4"]

# ── Drug Categories for Class-Stratified ROR ─────────────
# Each target compared against therapeutic class peers only
DRUG_CATEGORIES = {
    "biologics_immunosuppressants": [
        "humira",
        "dupixent",
        "methotrexate",
        "vedolizumab",
        "inflectra"
    ],
    "acid_reflux": [
        "zantac",
        "omeprazole",
        "pantoprazole"
    ],
    "cardiovascular": [
        "jardiance",
        "metoprolol",
        "lisinopril",
        #"prednisone"
        "atorvastatin" 
    ]
}

# Target drugs — signals reported for these specifically
# Covers biologics, withdrawn drug (zantac), and cardiovascular
TARGET_DRUGS = ["humira", "zantac", "jardiance"]

# Configurable — swap any drug names for your analysis scope
# Default set validated against cardiovascular and metabolic drug profiles
# Baseline configuration
BASELINE_YEAR = 2022

DRUG_BASELINE_PERIODS = {
    "zantac":     2021,   # post-withdrawal, pre-data-thinning
    "ranitidine": 2021,   # same — generic name for zantac
}
