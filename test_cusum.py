import logging
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # non-interactive backend for saving files
import matplotlib.pyplot as plt
import os
logging.basicConfig(level=logging.INFO)

from src.detection.cusum import (
    fetch_quarterly_counts, 
    calculate_cusum,
    run_cusum_for_signals
)

os.makedirs('outputs/cusum_charts', exist_ok=True)

# Load ROR signals
signals = pd.read_csv('outputs/ror_signals.csv')
print(f"Total ROR signals loaded: {len(signals)}")

# Run CUSUM for top 5 signals per drug
top_signals = (signals
    .groupby('drug_name')
    .apply(lambda x: x.nlargest(5, 'ROR'))
    .reset_index(drop=True))

print(f"Running CUSUM for {len(top_signals)} drug-reaction pairs")

cusum_summary = []

for _, row in top_signals.iterrows():
    drug = row['drug_name']
    reaction = row['reaction']
    ror = row['ROR']
    key = f"{drug}|{reaction}"

    ts = fetch_quarterly_counts(drug, reaction)

    if ts.empty:
        print(f"No data: {key}")
        continue

    result = calculate_cusum(ts, drug_name=drug)

    if result.empty:
        print(f"Insufficient quarters: {key}")
        continue

    alert_quarters = result['cusum_alert'].sum()
    max_cusum = result['cusum'].max()

    cusum_summary.append({
        'drug_name': drug,
        'reaction': reaction,
        'ROR': ror,
        'quarters_available': len(result),
        'alert_quarters': alert_quarters,
        'max_cusum': round(max_cusum, 2),
        'cusum_signal': alert_quarters > 0
    })

    # ── Plot ─────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle(f'{drug.upper()} — {reaction}', 
                 fontsize=13, fontweight='bold')

    # Report count chart
    ax1.plot(result['period'], result['report_count'],
             marker='o', linewidth=2, color='steelblue',
             label='Quarterly Reports')
    ax1.axhline(y=result['baseline_mean'].iloc[0],
                color='green', linestyle='--', linewidth=1.5,
                label=f"Baseline mean ({result['baseline_year'].iloc[0]})")
    ax1.set_ylabel('Quarterly Reports')
    ax1.legend(fontsize=9)
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(alpha=0.3)

    # CUSUM chart
    periods = result['period'].tolist()
    ax2.plot(periods, result['cusum'],
             marker='s', linewidth=2, color='darkorange',
             label='CUSUM')
    ax2.axhline(y=5, color='red', linestyle='--',
                linewidth=2, label='Alert threshold (5)')

    # Shade alert quarters red
    for idx, r in result[result['cusum_alert']].iterrows():
        pos = periods.index(r['period'])
        ax2.axvspan(pos - 0.4, pos + 0.4,
                    alpha=0.25, color='red')

    ax2.set_ylabel('CUSUM Value')
    ax2.set_xlabel('Quarter')
    ax2.legend(fontsize=9)
    ax2.tick_params(axis='x', rotation=45)
    ax2.grid(alpha=0.3)

    plt.tight_layout()

    safe_name = (f"{drug}_{reaction[:25].replace(' ', '_')}"
                 .replace('/', '_'))
    filepath = f'outputs/cusum_charts/{safe_name}.png'
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()

# Save summary
summary_df = pd.DataFrame(cusum_summary)
summary_df.to_csv('outputs/cusum_summary.csv', index=False)

print("\n" + "="*60)
print("CUSUM SUMMARY")
print("="*60)
print(summary_df.to_string(index=False))
print(f"\nCharts saved to outputs/cusum_charts/")
print(f"Summary saved to outputs/cusum_summary.csv")

# Key finding
confirmed = summary_df[summary_df['cusum_signal']]
print(f"\nSignals confirmed by BOTH ROR and CUSUM: {len(confirmed)}")
print(confirmed[['drug_name','reaction','ROR','max_cusum']].to_string())