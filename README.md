# MedDrift — Pharmaceutical Safety Signal Detection

Automated detection of adverse drug event signals from FDA FAERS data using 
statistical pharmacovigilance methods.

## What This Does

MedDrift processes 20 quarters (2020–2024) of FDA adverse event reports to 
automatically identify drug-reaction pairs generating statistically significant 
safety signals — the same analytical function performed by enterprise 
pharmacovigilance software costing millions of dollars annually.

## Key Findings

7 signals confirmed by all three detection methods (ROR + CUSUM + EWMA):

| Drug | Reaction | ROR | Clinical Context |
|------|----------|-----|-----------------|
| Zantac | Colorectal cancer | 4,851 | Consistent with FDA 2020 NDMA withdrawal |
| Zantac | Bladder cancer | 1,286 | NDMA-related carcinogenicity |
| Zantac | Gastrointestinal carcinoma | 916 | NDMA-related carcinogenicity |
| Zantac | Prostate cancer | 810 | NDMA-related carcinogenicity |
| Zantac | Renal cancer | 722 | NDMA-related carcinogenicity |
| Humira | Device issue | 51 | Pen injector malfunctions — spike post-2020 COVID self-administration |
| Jardiance | Euglycaemic diabetic ketoacidosis | 39 | Emerging SGLT2 inhibitor signal — consistent with FDA warning |

Zantac findings validate the pipeline — these are the exact signals that led 
to FDA's 2020 market withdrawal decision.

## Methodology

### Signal Detection Pipeline
```
FAERS ZIPs → ETL → MySQL → ROR → CUSUM → EWMA → Master Signals
```

### Reporting Odds Ratio (ROR)
Measures disproportionate reporting of a drug-reaction pair versus 
therapeutic class peers. ROR = (A/B)/(C/D) from a 2×2 contingency table.
Signals flagged at ROR ≥ 5.0, p < 0.05, minimum 25 reports.
Comparison is class-stratified — biologics compared against biologics, 
not against the entire database.

### CUSUM Control Charts
Detects sustained upward trends in quarterly report counts. Standardizes 
deviations against a fixed baseline year (2022) to account for each drug's 
historical volatility. Resets to zero on negative deviation — only upward 
signals accumulate. Alert threshold = 5.0 standardized units.

### EWMA Smoothing
Exponentially Weighted Moving Average with λ=0.2 — gives 20% weight to 
current quarter, 80% to historical trend. More sensitive to recent 
acceleration than CUSUM. Alert line = baseline_mean + 3×baseline_std.

### Signal Confidence
- **High**: Confirmed by all three methods — strongest evidence
- **Medium**: Confirmed by ROR + one temporal method
- **Low**: ROR only — candidate for further investigation

## Known Limitations

**Notoriety Bias (Weber Effect)**: Zantac signals are inflated by mass 
retrospective reporting following the 2020 withdrawal announcement. 
Signal detection is correct but magnitudes reflect reporting behavior, 
not just clinical harm.

**Exposure Denominator**: FAERS captures only reported events — no 
denominator of total drug users. ROR normalizes within the database 
but cannot calculate true incidence rates.

**Drug Name Standardization**: Partial normalization only (lowercase, 
dose stripping). Full MedDRA coding not implemented — some drug name 
variants may be missed.

**Report Corrections**: INSERT IGNORE logic retains first submission. 
FDA-corrected reports are not processed — known limitation of current 
ETL design.

**Manual Class Stratification**: Drug categories defined manually in 
config.py. Production systems use RxNorm or WHO ATC classification.

## Tech Stack

- **Python**: pandas, scipy, sqlalchemy, matplotlib
- **Database**: MySQL 8.0 with materialized views for performance
- **Statistical Methods**: ROR, chi-square, CUSUM, EWMA
- **Dashboard**: Power BI (connected directly to MySQL)
- **Data Source**: FDA FAERS public database (open.fda.gov)

## Reproducing This Analysis

```bash
# 1. Setup
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
# Add MySQL credentials to .env

# 2. Download data
python download_all.py

# 3. Load into MySQL
python -c "from src.etl.pipeline import run_pipeline; run_pipeline(skip_download=True)"

# 4. Run complete signal pipeline
python -m src.stats.signal_pipeline
```

## Project Structure

```
MedDrift/
├── src/
│   ├── etl/          # download, parse, load, pipeline
│   ├── stats/        # ror, combine_signals, signal_pipeline
│   └── detection/    # cusum, ewma
├── outputs/          # signals CSVs, charts
├── dashboard/        # Power BI files
├── config.py         # all parameters and thresholds
└── README.md
```
