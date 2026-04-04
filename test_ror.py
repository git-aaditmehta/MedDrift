import logging
logging.basicConfig(level=logging.INFO)

from src.stats.ror import get_significant_signals
from config import DRUG_CATEGORIES

category = DRUG_CATEGORIES["biologics_immunosuppressants"]
target = ["humira"]
peers = [d for d in category if d != "humira"]

signals = get_significant_signals(
    target_drugs=target,
    peer_drugs=peers
)

print(f"\nSignals found: {len(signals)}")
print(signals.head(20))