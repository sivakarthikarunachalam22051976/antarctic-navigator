"""Run every validation that is actually executable with locally available data.

This is the release-level validation orchestrator. It never fabricates missing
scientific evidence: unavailable historical datasets are reported as BLOCKED,
while real-data routing/robustness checks are executed immediately.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

def run(cmd: list[str], env: dict[str,str]) -> dict:
    p = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)
    return {"command": cmd, "returncode": p.returncode, "stdout": p.stdout[-12000:], "stderr": p.stderr[-6000:]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--horizon',type=int,default=3,choices=range(1,8))
    ap.add_argument('--vessel',default='standard')
    ap.add_argument('--output',default='validation/full_validation_report.json')
    args=ap.parse_args()
    env=os.environ.copy(); env['USE_REAL_DATA']='1'; env['ALLOW_SYNTHETIC_FALLBACK']='0'
    report={"version":"release-validation","real_data_required":True,"checks":{}}

    # Core project regression checks.
    report['checks']['self_check']=run([PYTHON,'scripts/self_check.py'],env)
    report['checks']['real_bundle']=run([PYTHON,'scripts/validate_real_bundle.py'],env)
    report['checks']['route_robustness']=run([PYTHON,'scripts/route_robustness.py','--horizon',str(args.horizon),'--vessel',args.vessel],env)

    hist=ROOT/'backend'/'data'/'real'/'historical'
    byu=hist/'byu_v8.0'
    nc=hist/'nsidc'
    if any(byu.rglob('*.csv')):
        report['checks']['iceberg_historical']=run([PYTHON,'scripts/validate_iceberg_backtest.py','--tracks',str(byu)],env)
    else:
        report['checks']['iceberg_historical']={"status":"BLOCKED","reason":"BYU/NIC v8.0 historical CSV archive is not bundled; run backend/data/fetch_byu_historical.py first."}
    if any(nc.rglob('*.nc')):
        report['checks']['seaice_historical']=run([PYTHON,'scripts/validate_seaice_forecast.py','--data-dir',str(nc)],env)
    else:
        report['checks']['seaice_historical']={"status":"BLOCKED","reason":"Historical NSIDC NetCDF files are not bundled; supply them before scoring forecast skill."}

    out=ROOT/args.output; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    failed=[]
    for name,res in report['checks'].items():
        if isinstance(res,dict) and res.get('status')=='BLOCKED': continue
        if isinstance(res,dict) and res.get('returncode',0)!=0: failed.append(name)
    if failed:
        raise SystemExit('Release validation failed: '+', '.join(failed))

if __name__=='__main__': main()
