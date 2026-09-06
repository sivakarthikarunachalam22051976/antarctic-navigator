from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from config import INDIAN_STATIONS, latlon_to_rc
from main import get_dataset, iceberg_risk_grid
from models.router import find_route
from models.seaice_forecast import forecast_concentration

d=get_dataset(); f=forecast_concentration(d['concentration'],int(d['meta'].get('day_of_year',1)),d['lat_grid'],3); r=iceberg_risk_grid(d['icebergs'],f[-1].shape,72)
a=latlon_to_rc(INDIAN_STATIONS['Maitri']['lat'],INDIAN_STATIONS['Maitri']['lon']); b=latlon_to_rc(INDIAN_STATIONS['Bharati']['lat'],INDIAN_STATIONS['Bharati']['lon']); path,c=find_route(f[-1],a,b,r,'standard')
print('SMOKE_OK', d['meta']['dataset_kind'], f.shape, len(path), round(c,2))
