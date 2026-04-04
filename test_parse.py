import os
from src.etl.parse import parse_quarter

# Test on first available extracted quarter
extract_dir = "data/raw/faers_ascii_2023q1/ASCII"

tables = parse_quarter(extract_dir)

for table_name, df in tables.items():
    print(f"\n{table_name.upper()}")
    print(f"  Rows: {len(df)}")
    print(f"  Columns: {list(df.columns)}")
    if len(df) > 0:
        print(f"  Sample:\n{df.head(2)}")