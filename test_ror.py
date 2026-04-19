import logging
import pandas as pd
logging.basicConfig(level=logging.INFO)

from src.stats.ror import get_significant_signals
from config import TARGET_DRUGS, DRUG_CATEGORIES

all_signals = []

for drug in TARGET_DRUGS:
    # Find peers from category
    peers = []
    for category, members in DRUG_CATEGORIES.items():
        if drug in members:
            peers = [d for d in members if d != drug]
            break
    
    print(f"\nAnalyzing: {drug} vs peers: {peers}")
    signals = get_significant_signals(
        target_drugs=[drug],
        peer_drugs=peers
    )
    all_signals.append(signals)
    print(f"Signals found: {len(signals)}")
    print(signals.head(5).to_string())

# Combine all signals
final = pd.concat(all_signals, ignore_index=True)
print(f"\nTotal signals across all drugs: {len(final)}")

# Save to outputs
final.to_csv('outputs/ror_signals.csv', index=False)
print("Saved to outputs/ror_signals.csv")