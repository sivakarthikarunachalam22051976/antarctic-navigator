"""Local environment/data readiness check for Antarctic Navigator."""
from __future__ import annotations
import importlib.util, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REQUIRED=['fastapi','numpy','pandas','scipy','xarray','netCDF4','earthaccess','requests','bs4','pydantic','pyproj']

def main():
    missing=[x for x in REQUIRED if importlib.util.find_spec(x) is None]
    bundle=ROOT/'backend'/'data'/'real'/'navigator_bundle.json'
    hist=ROOT/'backend'/'data'/'real'/'historical'
    result={
      'python':sys.version.split()[0],
      'dependencies_missing':missing,
      'real_bundle_present':bundle.exists(),
      'historical_byu_present':any((hist/'byu_v8.0').rglob('*.csv')) if (hist/'byu_v8.0').exists() else False,
      'historical_nsidc_present':any(hist.rglob('*.nc')) if hist.exists() else False,
      'USE_REAL_DATA':os.getenv('USE_REAL_DATA','1'),
      'ALLOW_SYNTHETIC_FALLBACK':os.getenv('ALLOW_SYNTHETIC_FALLBACK','0'),
      'status':'ok' if not missing and bundle.exists() else 'needs_setup'
    }
    print(json.dumps(result,indent=2)); return 0 if result['status']=='ok' else 1
if __name__=='__main__': raise SystemExit(main())
