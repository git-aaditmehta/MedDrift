import pandas as pd
import numpy as np
from scipy import stats
import logging
import mysql.connector
from config import DB_CONFIG, ROR_THRESHOLD, P_VALUE_THRESHOLD, MIN_REPORT_COUNT

logger = logging.getLogger(__name__)

def get_connection():
    config = DB_CONFIG.copy()
    config['ssl_disabled'] = True
    return mysql.connector.connect(**config)

def fetch_drug_reaction_counts(target_drugs: list, peer_drugs: list = None) -> pd.DataFrame:
    conn = get_connection()
    all_drugs = list(set(target_drugs + (peer_drugs or [])))
    placeholders = ', '.join(['%s'] * len(all_drugs))

    query = f"""
        SELECT 
            d.drug_name,
            r.reaction,
            COUNT(*) as pair_count
        FROM drug d
        JOIN reac r ON d.primaryid = r.primaryid
        JOIN demo dm ON d.primaryid = dm.primaryid
        WHERE d.drug_name IN ({placeholders})
        AND r.reaction IS NOT NULL
        AND dm.report_date >= %s
        AND dm.report_date <= %s
        GROUP BY d.drug_name, r.reaction
        HAVING COUNT(*) >= %s
    """
    
    from config import ANALYSIS_START_DATE, ANALYSIS_END_DATE
    params = all_drugs + [ANALYSIS_START_DATE, ANALYSIS_END_DATE, MIN_REPORT_COUNT]

    logger.info(f"Fetching pairs for {len(all_drugs)} drugs (2023-2024)...")
    df = pd.read_sql(query, conn, params=params)
    conn.close()

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
    # Preserve is_target column if it exists
    if 'is_target' in df.columns:
        pass  # already preserved through merges
    logger.info(f"Columns after calculate_ror: {list(df.columns)}")
    
    return df.sort_values('ROR', ascending=False)

def get_significant_signals(target_drugs: list = None) -> pd.DataFrame:
    """
    Full ROR pipeline.
    Automatically finds peer drugs from DRUG_CATEGORIES in config.
    Each target drug is compared against its therapeutic class peers.
    """
    from config import DRUG_CATEGORIES, TARGET_DRUGS

    if target_drugs is None:
        target_drugs = TARGET_DRUGS

    # Build peer list automatically from drug categories
    peer_drugs = []
    for drug in target_drugs:
        for category, members in DRUG_CATEGORIES.items():
            if drug in members:
                # peers = everyone in same category except the target itself
                peers = [d for d in members if d != drug]
                peer_drugs.extend(peers)
                logger.info(f"{drug} → category: {category}, peers: {peers}")

    # Deduplicate peers
    peer_drugs = list(set(peer_drugs))

    df = fetch_drug_reaction_counts(
        target_drugs=target_drugs,
        peer_drugs=peer_drugs
    )

    if df.empty:
        logger.warning("No data returned — check drug names exist in database")
        return pd.DataFrame()

    # Mark target vs peer rows
    df['is_target'] = df['drug_name'].isin(target_drugs)

    df = calculate_ror(df)

    # Only return signals for target drugs
    signals = df[
        df['is_signal'] & df['is_target']
    ].copy()

    logger.info(f"Found {len(signals)} significant signals")
    return signals[['drug_name', 'reaction', 'pair_count', 'ROR', 'p_value']]