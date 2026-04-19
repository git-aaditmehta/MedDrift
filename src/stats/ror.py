import pandas as pd
import numpy as np
from scipy import stats
import logging
import mysql.connector
from config import DB_CONFIG, ROR_THRESHOLD, P_VALUE_THRESHOLD, MIN_REPORT_COUNT
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

def get_connection():
    from config import DB_CONFIG
    url = (
        f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )
    return create_engine(url)

def fetch_drug_reaction_counts(target_drugs: list, peer_drugs: list = None) -> pd.DataFrame:
    """
    Fetches drug-reaction counts from materialized view.
    """
    engine = get_connection()
    all_drugs = list(set(target_drugs + (peer_drugs or [])))

    # MySQL connector needs %(name)s style parameters
    placeholders = ', '.join([f'%(drug_{i})s' for i in range(len(all_drugs))])
    query = f"""
        SELECT drug_name, reaction, pair_count
        FROM drug_reac_summary
        WHERE drug_name IN ({placeholders})
    """

    params = {f'drug_{i}': drug for i, drug in enumerate(all_drugs)}

    logger.info(f"Fetching pairs for {len(all_drugs)} drugs...")
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params)

    logger.info(f"Fetched {len(df)} drug-reaction pairs")
    return df

def calculate_ror(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates Reporting Odds Ratio for every drug-reaction pair.
    
    For each pair:
    A = reports of this drug WITH this reaction
    B = reports of this drug WITHOUT this reaction  
    C = reports of OTHER drugs WITH this reaction
    D = reports of OTHER drugs WITHOUT this reaction
    
    ROR = (A/B) / (C/D)
    """
    # Total reports per drug
    drug_totals = df.groupby('drug_name')['pair_count'].sum().reset_index()
    drug_totals.columns = ['drug_name', 'drug_total']
    
    # Total reports per reaction
    reaction_totals = df.groupby('reaction')['pair_count'].sum().reset_index()
    reaction_totals.columns = ['reaction', 'reaction_total']
    
    # Total reports in entire database
    total_reports = df['pair_count'].sum()
    
    # Merge totals back
    df = df.merge(drug_totals, on='drug_name')
    df = df.merge(reaction_totals, on='reaction')
    
    # Calculate 2x2 contingency table values
    df['A'] = df['pair_count']                                    # drug + reaction
    df['B'] = df['drug_total'] - df['A']                         # drug + no reaction
    df['C'] = df['reaction_total'] - df['A']                     # other drugs + reaction
    df['D'] = total_reports - df['A'] - df['B'] - df['C']        # other drugs + no reaction
    
    # Calculate ROR — avoid division by zero
    df['ROR'] = (df['A'] / df['B'].replace(0, np.nan)) / \
                (df['C'] / df['D'].replace(0, np.nan))
    
    # Chi-square test for statistical significance
    def chi_square_p(row):
        table = [[row['A'], row['B']], 
                 [row['C'], row['D']]]
        # Skip if any cell is zero
        if min(row['A'], row['B'], row['C'], row['D']) <= 0:
            return 1.0
        _, p, _, _ = stats.chi2_contingency(table)
        return p
    
    logger.info("Calculating chi-square p-values...")
    df['p_value'] = df.apply(chi_square_p, axis=1)
    
    # Flag significant signals
    df['is_signal'] = (
        (df['ROR'] >= ROR_THRESHOLD) & 
        (df['p_value'] <= P_VALUE_THRESHOLD) &
        (df['A'] >= MIN_REPORT_COUNT)
    )
    
    df['ROR'] = df['ROR'].round(2)
    df['p_value'] = df['p_value'].apply(lambda x: float(f'{x:.2e}'))
    logger.info(f"Columns after calculate_ror: {list(df.columns)}")
    return df.sort_values('ROR', ascending=False)

def get_significant_signals(target_drugs: list, peer_drugs: list = None) -> pd.DataFrame:
    """
    Full ROR pipeline with class-stratified comparison.
    """
    df = fetch_drug_reaction_counts(
        target_drugs=target_drugs,
        peer_drugs=peer_drugs
    )

    if df.empty:
        logger.warning("No data returned")
        return pd.DataFrame()

    # Mark which rows are target vs peer
    df['is_target'] = df['drug_name'].isin(target_drugs)

    df = calculate_ror(df)

    # Only report signals for target drugs
    signals = df[
        df['is_signal'] & df['is_target']
    ].copy()

    logger.info(f"Found {len(signals)} significant signals for target drugs")
    return signals[['drug_name', 'reaction', 'pair_count', 'ROR', 'p_value']]
    