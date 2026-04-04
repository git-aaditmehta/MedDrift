import logging
logging.basicConfig(level=logging.INFO)

from src.stats.ror import get_significant_signals

# Peers auto-selected from DRUG_CATEGORIES in config
signals = get_significant_signals(target_drugs=["humira"])

print(f"\nSignals found: {len(signals)}")
print(signals.to_string())