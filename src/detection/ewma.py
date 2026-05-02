import pandas as pd
import numpy as np
import logging
from sqlalchemy import create_engine
from config import (DB_CONFIG, EWMA_LAMBDA, EWMA_THRESHOLD,
                    BASELINE_YEAR, DRUG_BASELINE_PERIODS,
                    )

logger = logging.getLogger(__name__)

def get_engine():
    url = (
        f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )
    return create_engine(url)

def fetch_quarterly_counts(drug_name: str, reaction: str) -> pd.DataFrame:
    """
    Fetches quarterly counts from drug_reac_quarterly.
    Filters to START_YEAR-END_YEAR to avoid historical data artifacts.
    """
    engine = get_engine()
    
    query = """
        SELECT year, quarter, report_count
        FROM drug_reac_quarterly
        WHERE drug_name = %(drug)s
        AND reaction = %(reaction)s
        ORDER BY year, quarter
    """

    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={
            'drug': drug_name,
            'reaction': reaction
    })
    
    df['period'] = (df['year'].astype(str) + '-Q' + 
                    df['quarter'].astype(str))
    return df

def get_baseline(df: pd.DataFrame, drug_name: str) -> tuple:
    """
    Same baseline logic as CUSUM — drug-specific or global BASELINE_YEAR.
    Returns (baseline_mean, baseline_std, baseline_year_used)
    """
    if drug_name in DRUG_BASELINE_PERIODS:
        baseline_year = DRUG_BASELINE_PERIODS[drug_name]
    else:
        baseline_year = BASELINE_YEAR
    
    baseline_df = df[df['year'] == baseline_year]
    
    if len(baseline_df) < 2:
        logger.warning(f"{drug_name}: fallback to first 4 quarters")
        baseline_df = df.iloc[:4]
        baseline_year = "first4Q"
    
    baseline_mean = baseline_df['report_count'].mean()
    baseline_std = baseline_df['report_count'].std()
    
    if pd.isna(baseline_std) or baseline_std == 0:
        baseline_std = baseline_mean * 0.1
    
    return baseline_mean, baseline_std, baseline_year

def calculate_ewma(df: pd.DataFrame,
                   drug_name: str = None,
                   lam: float = EWMA_LAMBDA,
                   threshold: float = EWMA_THRESHOLD) -> pd.DataFrame:
    """
    Calculates EWMA control chart for a drug-reaction time series.
    
    Formula: EWMA_t = (lambda × X_t) + (1 - lambda) × EWMA_{t-1}
    
    EWMA starts at baseline mean.
    Alert when EWMA deviates more than threshold std above baseline mean.
    
    Why threshold in std units:
    Same risk-adjustment as CUSUM — volatile drugs need larger 
    absolute changes to trigger alerts.
    """
    if len(df) < 5:
        logger.warning(f"Only {len(df)} quarters — need at least 5")
        return pd.DataFrame()
    
    baseline_mean, baseline_std, baseline_year = get_baseline(df, drug_name)
    
    df = df.copy()
    df['baseline_mean'] = round(baseline_mean, 1)
    df['baseline_std'] = round(baseline_std, 1)
    df['baseline_year'] = baseline_year
    
    # EWMA starts at baseline mean
    ewma_values = []
    ewma = baseline_mean
    
    for count in df['report_count']:
        ewma = (lam * count) + ((1 - lam) * ewma)
        ewma_values.append(round(ewma, 3))
    
    df['ewma'] = ewma_values
    
    # Alert when EWMA exceeds baseline_mean + (threshold × baseline_std)
    alert_line = baseline_mean + (threshold * baseline_std)
    df['ewma_alert_line'] = round(alert_line, 1)
    df['ewma_alert'] = df['ewma'] > alert_line
    
    logger.info(
        f"{drug_name} EWMA baseline: "
        f"mean={baseline_mean:.1f}, "
        f"alert_line={alert_line:.1f}"
    )
    
    return df

def run_ewma_for_signals(signals: pd.DataFrame) -> dict:
    """
    Runs EWMA for every drug-reaction pair in signals dataframe.
    """
    results = {}
    total = len(signals)
    
    for i, (_, row) in enumerate(signals.iterrows()):
        drug = row['drug_name']
        reaction = row['reaction']
        key = f"{drug}|{reaction}"
        
        logger.info(f"[{i+1}/{total}] EWMA: {key}")
        
        ts = fetch_quarterly_counts(drug, reaction)
        
        if ts.empty:
            continue
            
        result = calculate_ewma(ts, drug_name=drug)
        
        if result.empty:
            continue
        
        results[key] = result
        
        alert_count = result['ewma_alert'].sum()
        if alert_count > 0:
            logger.info(f"ALERT: {key} — {alert_count} quarters")
    
    return results