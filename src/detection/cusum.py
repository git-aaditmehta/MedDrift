import pandas as pd
import numpy as np
import logging
from sqlalchemy import create_engine
from config import (DB_CONFIG, CUSUM_THRESHOLD, 
                    BASELINE_YEAR, DRUG_BASELINE_PERIODS)

logger = logging.getLogger(__name__)

def get_engine():
    url = (
        f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )
    return create_engine(url)

def fetch_quarterly_counts(drug_name: str, reaction: str) -> pd.DataFrame:
    """
    Fetches quarterly report counts from pre-computed materialized view.
    Uses drug_reac_quarterly — no raw JOIN needed, fast lookup via indexes.
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
        df = pd.read_sql(
            query, conn,
            params={'drug': drug_name, 'reaction': reaction}
        )
    
    # Create readable period label
    df['period'] = (df['year'].astype(str) + '-Q' + 
                    df['quarter'].astype(str))
    return df

def get_baseline(df: pd.DataFrame, drug_name: str) -> tuple:
    """
    Determines baseline mean and std for a drug.
    
    Priority:
    1. Drug-specific baseline year from DRUG_BASELINE_PERIODS
    2. Global BASELINE_YEAR from config
    3. First 4 quarters as fallback
    
    Returns (baseline_mean, baseline_std, baseline_year_used)
    """
    # Determine which baseline year to use
    if drug_name in DRUG_BASELINE_PERIODS:
        baseline_year = DRUG_BASELINE_PERIODS[drug_name]
        source = f"drug-specific override"
    else:
        baseline_year = BASELINE_YEAR
        source = f"global default"
    
    # Filter to baseline year
    baseline_df = df[df['year'] == baseline_year]
    
    # Fallback — baseline year has insufficient data
    if len(baseline_df) < 2:
        logger.warning(
            f"{drug_name}: insufficient data in baseline year "
            f"{baseline_year} ({len(baseline_df)} quarters), "
            f"falling back to first 4 quarters"
        )
        baseline_df = df.iloc[:4]
        baseline_year = f"first4Q"
        source = "fallback"
    
    baseline_mean = baseline_df['report_count'].mean()
    baseline_std = baseline_df['report_count'].std()
    
    # If std is 0 or NaN, assume 10% of mean as minimum variation
    if pd.isna(baseline_std) or baseline_std == 0:
        baseline_std = baseline_mean * 0.1
    
    logger.info(
        f"{drug_name} baseline ({source}): "
        f"year={baseline_year}, "
        f"mean={baseline_mean:.1f}, "
        f"std={baseline_std:.1f}"
    )
    
    return baseline_mean, baseline_std, baseline_year

def calculate_cusum(df: pd.DataFrame,
                    drug_name: str = None,
                    threshold: float = CUSUM_THRESHOLD) -> pd.DataFrame:
    """
    Calculates CUSUM control chart for a drug-reaction time series.
    
    Steps:
    1. Determine baseline mean and std (drug-specific or global)
    2. Standardize deviations: (actual - baseline_mean) / baseline_std
    3. Accumulate: CUSUM = max(0, CUSUM_prev + deviation)
    4. Flag when CUSUM > threshold
    
    Standardization ensures drugs with volatile history
    need larger absolute changes to trigger alerts (risk-adjusted).
    """
    if len(df) < 5:
        logger.warning(
            f"Only {len(df)} quarters available — "
            f"need at least 5 for reliable CUSUM"
        )
        return pd.DataFrame()
    
    baseline_mean, baseline_std, baseline_year = get_baseline(df, drug_name)
    
    df = df.copy()
    df['baseline_mean'] = round(baseline_mean, 1)
    df['baseline_std'] = round(baseline_std, 1)
    df['baseline_year'] = baseline_year
    
    # Standardized deviation from baseline
    df['deviation'] = (
        (df['report_count'] - baseline_mean) / baseline_std
    ).round(3)
    
    # Accumulate CUSUM — reset to 0 on negative
    cusum_values = []
    cumsum = 0
    for dev in df['deviation']:
        cumsum = max(0, cumsum + dev)
        cusum_values.append(round(cumsum, 3))
    
    df['cusum'] = cusum_values
    df['cusum_alert'] = df['cusum'] > threshold
    df['threshold'] = threshold
    
    return df

def run_cusum_for_signals(signals: pd.DataFrame) -> dict:
    """
    Runs CUSUM for every drug-reaction pair in signals dataframe.
    Returns dict keyed by 'drug|reaction' with CUSUM result dataframes.
    """
    results = {}
    total = len(signals)
    
    for i, (_, row) in enumerate(signals.iterrows()):
        drug = row['drug_name']
        reaction = row['reaction']
        key = f"{drug}|{reaction}"
        
        logger.info(f"[{i+1}/{total}] CUSUM: {key}")
        
        ts = fetch_quarterly_counts(drug, reaction)
        
        if ts.empty:
            logger.warning(f"No time series data for {key}")
            continue
        
        result = calculate_cusum(ts, drug_name=drug)
        
        if result.empty:
            continue
            
        results[key] = result
        
        alert_count = result['cusum_alert'].sum()
        if alert_count > 0:
            logger.info(
                f"ALERT: {key} — "
                f"{alert_count} quarters above threshold"
            )
    
    return results