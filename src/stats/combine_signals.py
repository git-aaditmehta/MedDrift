import pandas as pd
import logging
import os
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def combine_signals():
    """
    Combines ROR, CUSUM, and EWMA results into master signal table.
    Triple-confirmed signals are highest confidence.
    """
    # Load outputs
    ror = pd.read_csv('outputs/ror_signals.csv')
    cusum = pd.read_csv('outputs/cusum_summary.csv')
    ewma = pd.read_csv('outputs/ewma_summary.csv')

    # Merge on drug_name + reaction
    merged = ror.merge(
        cusum[['drug_name', 'reaction', 'max_cusum', 
               'alert_quarters', 'cusum_signal']],
        on=['drug_name', 'reaction'],
        how='left'
    )

    merged = merged.merge(
        ewma[['drug_name', 'reaction', 'max_ewma',
              'ewma_signal']],
        on=['drug_name', 'reaction'],
        how='left'
    )

    # Confidence scoring
    merged['cusum_signal'] = merged['cusum_signal'].fillna(False)
    merged['ewma_signal'] = merged['ewma_signal'].fillna(False)

    merged['confidence_score'] = (
        1 +                                    # ROR always counts (already filtered)
        merged['cusum_signal'].astype(int) +   # +1 if CUSUM confirms
        merged['ewma_signal'].astype(int)      # +1 if EWMA confirms
    )

    merged['confidence_label'] = merged['confidence_score'].map({
        1: 'Low — ROR only',
        2: 'Medium — ROR + one method',
        3: 'High — All three methods'
    })

    # Sort by confidence then ROR
    merged = merged.sort_values(
        ['confidence_score', 'ROR'],
        ascending=[False, False]
    )

    # Save
    os.makedirs('outputs', exist_ok=True)
    merged.to_csv('outputs/master_signals.csv', index=False)

    # Print summary
    print("\n" + "="*70)
    print("MASTER SIGNAL TABLE")
    print("="*70)

    for label in ['High — All three methods', 
                  'Medium — ROR + one method',
                  'Low — ROR only']:
        subset = merged[merged['confidence_label'] == label]
        print(f"\n{label}: {len(subset)} signals")
        if label == 'High — All three methods':
            print(subset[['drug_name', 'reaction', 
                          'ROR', 'max_cusum', 'max_ewma']].to_string())

    print(f"\nTotal signals: {len(merged)}")
    print("Saved to outputs/master_signals.csv")
    
    return merged

if __name__ == "__main__":
    combine_signals()