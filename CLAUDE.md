# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MedDrift is a pharmaceutical safety signal detection system that processes FDA FAERS (Adverse Event Reporting System) data (2020–2024) to identify adverse drug reactions using statistical methods. The three-stage pipeline is: **ETL → Signal Detection → Output**.

## Environment Setup

```bash
python -m venv venv
source venv/Scripts/activate      # Windows
pip install -r requirements.txt
# Configure .env with MySQL credentials before running anything
```

Required: MySQL running locally with a `meddrift` database. Credentials live in `.env` (loaded via `python-dotenv`); `config.py` reads them.

## Running the Pipeline

```bash
# Step 1: Download all 20 quarters of FAERS data
python download_all.py

# Step 2: Parse + load into MySQL (skip_download=True if data already exists)
python -c "from src.etl.pipeline import run_pipeline; run_pipeline(skip_download=True)"

# Step 3: Generate ROR signals (prerequisite for CUSUM/EWMA)
python test_ror.py        # → outputs/ror_signals.csv

# Step 4: Run temporal detection
python test_cusum.py      # → outputs/cusum_charts/*.png, outputs/cusum_summary.csv
python test_ewma.py       # → outputs/ewma_charts/*.png, outputs/ewma_summary.csv
```

## Running Tests

There is no pytest config. Tests are standalone scripts run directly:

```bash
python test_parse.py     # Validates FAERS table parsing on a single quarter
python test_download.py  # Validates download + ZIP extraction for one quarter
```

## Architecture

### Data Flow
```
FDA FAERS ZIPs → parse.py (5 ASCII tables) → load.py (MySQL) → materialized views
                                                                        ↓
                                          ror.py (2×2 table) → ror_signals.csv
                                                                        ↓
                                    cusum.py / ewma.py → alert charts + summaries
```

### Key Source Files

| File | Role |
|------|------|
| `config.py` | All thresholds, paths, drug lists, baseline years — change parameters here |
| `src/etl/pipeline.py` | Master ETL orchestrator |
| `src/etl/download.py` | Downloads quarterly ZIPs from FDA with retry/backoff |
| `src/etl/parse.py` | Parses DEMO/DRUG/REAC/OUTC/RPSR tables; normalizes drug names (lowercase, strips doses) |
| `src/etl/load.py` | Loads into MySQL using INSERT IGNORE in 1000-row chunks |
| `src/stats/ror.py` | ROR calculation (class-stratified, chi-square p-value) |
| `src/detection/cusum.py` | CUSUM control chart with baseline-aware alert detection |
| `src/detection/ewma.py` | EWMA smoothing with baseline-aware alert line |

### MySQL Database (`meddrift`)

**Core tables**: `demo`, `drug`, `reac`, `outc`, `rpsr`

**Materialized views queried by detection algorithms**:
- `drug_reac_quarterly` — year/quarter/report_count (used by CUSUM & EWMA)
- `drug_reac_summary` — drug_name/reaction/pair_count (used by ROR)

### Detection Algorithms

**ROR** (`src/stats/ror.py`): Computes `(A/B)/(C/D)` from a 2×2 contingency table. Signals flagged when ROR > 5.0 and p < 0.05, with minimum 25 reports. Comparison is class-stratified (target drug vs. its therapeutic class peers defined in `config.py`).

**CUSUM** (`src/detection/cusum.py`): Standardizes quarterly counts against a baseline mean/std, accumulates positive deviations, resets on negative. Alert threshold = 5.0. Supports drug-specific baseline overrides (e.g., zantac → 2021 due to market withdrawal).

**EWMA** (`src/detection/ewma.py`): Smooths quarterly counts with λ=0.2. Alert line = baseline_mean + 3×baseline_std. Baseline falls back to first 4 available quarters if the configured baseline year has no data.

## Key Configuration (`config.py`)

- **Target drugs**: humira, zantac, jardiance
- **Baseline year**: 2022 globally; zantac/ranitidine override to 2021
- **Drug categories**: biologics_immunosuppressants, acid_reflux, cardiovascular (used for ROR class comparison)
- **Thresholds**: CUSUM=5.0, EWMA λ=0.2, EWMA alert=3σ, ROR=5.0, p=0.05, min_reports=25

## Unimplemented Areas

`src/viz/`, `dashboard/`, and `notebooks/` are empty — no visualization or dashboard code exists yet.
