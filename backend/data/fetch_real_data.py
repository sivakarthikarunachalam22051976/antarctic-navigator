"""Download public NSIDC sea-ice source data for offline processing."""
from __future__ import annotations
import os
from pathlib import Path
DEFAULT_SHORT_NAME=os.getenv('NSIDC_SHORT_NAME','G10016'); RAW_DIR=Path(__file__).resolve().parent/'real'/'raw'
def download_nsidc(product_short_name=DEFAULT_SHORT_NAME):
    try:import earthaccess
    except ImportError as e:raise RuntimeError('Install earthaccess from requirements.txt first.') from e
    RAW_DIR.mkdir(parents=True,exist_ok=True); earthaccess.login(strategy='interactive',persist=True); results=earthaccess.search_data(short_name=product_short_name,count=5)
    if not results:raise RuntimeError(f'No Earthdata records found for {product_short_name}.')
    return [str(p) for p in earthaccess.download(results,local_path=str(RAW_DIR))]
def main():
    for p in download_nsidc():print(p)
    print('Next: run backend/data/convert_nsidc_bundle.py')
if __name__=='__main__':main()
