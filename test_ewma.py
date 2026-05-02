import logging
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
logging.basicConfig(level=logging.INFO)

from src.detection.ewma import fetch_quarterly_counts, calculate_ewma
os.makedirs('outputs/ewma_charts', exist_ok=True)

signals = pd.read_csv('outputs/ror_signals.csv')
top_signals = (signals
    .sort_values('ROR', ascending=False)
    .groupby('drug_name')
    .head(5)
    .reset_index(drop=True))

ewma_summary = []

for _, row in top_signals.iterrows():
    drug = row['drug_name']
    reaction = row['reaction']
    ror = row['ROR']

    ts = fetch_quarterly_counts(drug, reaction)
    if ts.empty:
        continue

    result = calculate_ewma(ts, drug_name=drug)
    if result.empty:
        continue

    alert_quarters = result['ewma_alert'].sum()
    max_ewma = result['ewma'].max()

    ewma_summary.append({
        'drug_name': drug,
        'reaction': reaction,
        'ROR': ror,
        'quarters_available': len(result),
        'alert_quarters': alert_quarters,
        'max_ewma': round(max_ewma, 2),
        'ewma_signal': alert_quarters > 0
    })

    # Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle(f'{drug.upper()} — {reaction}',
                 fontsize=13, fontweight='bold')

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

    ax2.plot(result['period'], result['ewma'],
             marker='s', linewidth=2, color='purple',
             label='EWMA')
    ax2.axhline(y=result['ewma_alert_line'].iloc[0],
                color='red', linestyle='--', linewidth=2,
                label=f"Alert line ({result['ewma_alert_line'].iloc[0]:.1f})")
    ax2.axhline(y=result['baseline_mean'].iloc[0],
                color='green', linestyle=':', linewidth=1.5,
                label=f"Baseline ({result['baseline_mean'].iloc[0]:.1f})")

    for idx, r in result[result['ewma_alert']].iterrows():
        pos = result['period'].tolist().index(r['period'])
        ax2.axvspan(pos - 0.4, pos + 0.4,
                    alpha=0.25, color='red')

    ax2.set_ylabel('EWMA Value')
    ax2.set_xlabel('Quarter')
    ax2.legend(fontsize=9)
    ax2.tick_params(axis='x', rotation=45)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    safe_name = (f"{drug}_{reaction[:25].replace(' ', '_')}"
                 .replace('/', '_'))
    plt.savefig(f'outputs/ewma_charts/{safe_name}.png',
                dpi=150, bbox_inches='tight')
    plt.close()

summary_df = pd.DataFrame(ewma_summary)
summary_df.to_csv('outputs/ewma_summary.csv', index=False)

print("\n" + "="*60)
print("EWMA SUMMARY")
print("="*60)
print(summary_df.to_string(index=False))

confirmed = summary_df[summary_df['ewma_signal']]
print(f"\nSignals confirmed by EWMA: {len(confirmed)}")