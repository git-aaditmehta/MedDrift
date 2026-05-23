import logging
import pandas as pd
import os
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_full_signal_pipeline():
    """
    Master signal detection pipeline.
    Runs ROR → CUSUM → EWMA → combines into master_signals.csv
    """
    from src.stats.ror import get_significant_signals
    from src.detection.cusum import fetch_quarterly_counts, calculate_cusum
    from src.detection.ewma import calculate_ewma
    from src.stats.combine_signals import combine_signals
    from config import TARGET_DRUGS, DRUG_CATEGORIES

    os.makedirs('outputs/cusum_charts', exist_ok=True)
    os.makedirs('outputs/ewma_charts', exist_ok=True)

    # ── Phase 1: ROR ─────────────────────────────────────
    logger.info("Phase 1: Running ROR signal detection...")
    all_signals = []

    for drug in TARGET_DRUGS:
        peers = []
        for category, members in DRUG_CATEGORIES.items():
            if drug in members:
                peers = [d for d in members if d != drug]
                break

        signals = get_significant_signals(
            target_drugs=[drug],
            peer_drugs=peers
        )
        all_signals.append(signals)
        logger.info(f"{drug}: {len(signals)} ROR signals")

    ror_df = pd.concat(all_signals, ignore_index=True)
    ror_df.to_csv('outputs/ror_signals.csv', index=False)
    logger.info(f"ROR complete: {len(ror_df)} total signals")

    # ── Phase 2: CUSUM ────────────────────────────────────
    logger.info("Phase 2: Running CUSUM...")
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    top_signals = (ror_df
        .sort_values('ROR', ascending=False)
        .groupby('drug_name')
        .head(5)
        .reset_index(drop=True))

    cusum_summary = []
    for _, row in top_signals.iterrows():
        drug, reaction, ror = row['drug_name'], row['reaction'], row['ROR']
        ts = fetch_quarterly_counts(drug, reaction)
        if ts.empty:
            continue
        result = calculate_cusum(ts, drug_name=drug)
        if result.empty:
            continue

        cusum_summary.append({
            'drug_name': drug,
            'reaction': reaction,
            'ROR': ror,
            'alert_quarters': result['cusum_alert'].sum(),
            'max_cusum': result['cusum'].max().round(2),
            'cusum_signal': result['cusum_alert'].any()
        })

    cusum_df = pd.DataFrame(cusum_summary)
    cusum_df.to_csv('outputs/cusum_summary.csv', index=False)
    logger.info(f"CUSUM complete: {cusum_df['cusum_signal'].sum()} signals confirmed")

    # ── Phase 3: EWMA ─────────────────────────────────────
    logger.info("Phase 3: Running EWMA...")
    from src.detection.ewma import fetch_quarterly_counts as ewma_fetch
    from src.detection.ewma import calculate_ewma

    ewma_summary = []
    for _, row in top_signals.iterrows():
        drug, reaction, ror = row['drug_name'], row['reaction'], row['ROR']
        ts = ewma_fetch(drug, reaction)
        if ts.empty:
            continue
        result = calculate_ewma(ts, drug_name=drug)
        if result.empty:
            continue

        ewma_summary.append({
            'drug_name': drug,
            'reaction': reaction,
            'ROR': ror,
            'alert_quarters': result['ewma_alert'].sum(),
            'max_ewma': result['ewma'].max().round(2),
            'ewma_signal': result['ewma_alert'].any()
        })

    ewma_df = pd.DataFrame(ewma_summary)
    ewma_df.to_csv('outputs/ewma_summary.csv', index=False)
    logger.info(f"EWMA complete: {ewma_df['ewma_signal'].sum()} signals confirmed")

    # ── Phase 4: Combine ──────────────────────────────────
    logger.info("Phase 4: Combining signals...")
    # ── Phase 4: Demographics ─────────────────────────────
    logger.info("Phase 4: Running demographics analysis...")
    from src.stats.demographics import analyze_all_signals
    analyze_all_signals()
    logger.info("Demographics complete.")

    master = combine_signals()

    triple = master[master['confidence_label'] == 'High — All three methods']
    logger.info(f"Pipeline complete. {len(triple)} triple-confirmed signals.")
    return master

    

if __name__ == "__main__":
    run_full_signal_pipeline()

