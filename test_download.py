from src.etl.download import download_faers_quarter, extract_zip

# Test with just one quarter first
zip_path = download_faers_quarter(2023, "q1")
if zip_path:
    extract_dir = extract_zip(zip_path)
    print(f"Success: {extract_dir}")
else:
    print("Download failed — check logs")