"""FastAPI API for Antarctic Navigator."""
from __future__ import annotations
import json,math,os
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from fastapi import FastAPI,HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware
from config import INDIAN_STATIONS,latlon_to_rc,rc_to_latlon
from models.drift_model import advect_iceberg
from models.router import VESSEL_PROFILES,find_route
from models.seaice_forecast import forecast_concentration
app=FastAPI(title='Antarctic Navigator API',version='1.0.0',description='Sea-ice, iceberg trajectory and route decision support prototype.')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
BASE=Path(__file__).resolve().parent; SYN=BASE/'data'/'sample'/'synthetic_dataset.json'; REAL=BASE/'data'/'real'/'navigator_bundle.json'; USE_REAL=os.getenv('USE_REAL_DATA','0')=='1'; _dataset=None

def _load(path):
    with path.open(encoding='utf-8') as f:return json.load(f)
def get_dataset():
    global _dataset
    if _dataset is not None:return _dataset
    path=REAL if USE_REAL and REAL.exists() else SYN
    if not path.exists():raise RuntimeError(f'Dataset not found: {path}')
    raw=_load(path); shape=np.asarray(raw['concentration']).shape
    _dataset={'meta':raw['meta'],'lat_grid':np.asarray(raw['lat_grid'],float),'lon_grid':np.asarray(raw['lon_grid'],float),'concentration':np.asarray(raw['concentration'],float),'current_u':np.asarray(raw.get('current_u',np.zeros(shape)),float),'current_v':np.asarray(raw.get('current_v',np.zeros(shape)),float),'wind_u':np.asarray(raw.get('wind_u',np.zeros(shape)),float),'wind_v':np.asarray(raw.get('wind_v',np.zeros(shape)),float),'icebergs':raw.get('icebergs',[])}
    return _dataset

def _distance(points):
    total=0.; R=6371.0088
    for a,b in zip(points,points[1:]):
        p1,p2=math.radians(a[0]),math.radians(b[0]); dp=math.radians(b[0]-a[0]); dl=math.radians(b[1]-a[1]); x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; total+=R*2*math.asin(min(1,math.sqrt(x)))
    return float(total)

def iceberg_risk_grid(icebergs,shape,hours):
    d=get_dataset(); risk=np.zeros(shape,float); rows,cols=shape
    for berg in icebergs:
        lat,lon=float(berg['lat']),float(berg['lon'])
        for _ in range(max(1,math.ceil(hours/6))):
            r,c=latlon_to_rc(lat,lon); lat,lon=advect_iceberg(lat,lon,(d['current_u'][r,c],d['current_v'][r,c]),(d['wind_u'][r,c],d['wind_v'][r,c]),6)
        r,c=latlon_to_rc(lat,lon); radius=max(1,int(round(max(1,float(berg.get('length_km',2)))/20)))
        for rr in range(max(0,r-radius),min(rows,r+radius+1)):
            for cc in range(max(0,c-radius),min(cols,c+radius+1)):
                risk[rr,cc]=max(risk[rr,cc],math.exp(-math.hypot(rr-r,cc-c)**2/max(1,radius**2)))
    return np.clip(risk,0,1)

@app.get('/api/health')
def health():
    d=get_dataset(); return {'status':'ok','time':datetime.now(timezone.utc).isoformat(),'dataset_kind':d['meta'].get('dataset_kind','unknown'),'source':d['meta'].get('source','unknown')}
@app.get('/api/config')
def config():return {'stations':INDIAN_STATIONS,'vessel_profiles':list(VESSEL_PROFILES)}
@app.get('/api/demo')
def demo():return {'dataset':get_dataset()['meta'],'stations':INDIAN_STATIONS,'vessel_profiles':list(VESSEL_PROFILES)}
@app.get('/api/seaice/grid')
def seaice_grid():
    d=get_dataset(); return {'lat':d['lat_grid'].tolist(),'lon':d['lon_grid'].tolist(),'concentration':d['concentration'].tolist(),'meta':d['meta']}
@app.get('/api/seaice/forecast')
def seaice_forecast(horizon_days:int=Query(3,ge=1,le=7)):
    d=get_dataset(); x=forecast_concentration(d['concentration'],int(d['meta'].get('day_of_year',1)),d['lat_grid'],horizon_days); return {'horizon_days':horizon_days,'forecast':x.tolist()}
@app.get('/api/icebergs')
def icebergs():return {'icebergs':get_dataset()['icebergs']}
@app.get('/api/icebergs/projected')
def icebergs_projected(hours_ahead:int=Query(24,ge=1,le=240)):
    d=get_dataset(); out=[]
    for berg in d['icebergs']:
        lat,lon=float(berg['lat']),float(berg['lon'])
        for _ in range(max(1,math.ceil(hours_ahead/6))):
            r,c=latlon_to_rc(lat,lon); lat,lon=advect_iceberg(lat,lon,(d['current_u'][r,c],d['current_v'][r,c]),(d['wind_u'][r,c],d['wind_v'][r,c]),6)
        out.append({**berg,'projected_lat':lat,'projected_lon':lon,'hours_ahead':hours_ahead})
    return {'icebergs':out}
@app.get('/api/route')
def route(start_lat:float,start_lon:float,goal_lat:float,goal_lon:float,horizon_days:int=Query(3,ge=1,le=7),vessel_profile:str=Query('standard')):
    if vessel_profile not in VESSEL_PROFILES:raise HTTPException(400,'Unknown vessel_profile.')
    d=get_dataset(); start=latlon_to_rc(start_lat,start_lon); goal=latlon_to_rc(goal_lat,goal_lon); forecast=forecast_concentration(d['concentration'],int(d['meta'].get('day_of_year',1)),d['lat_grid'],horizon_days); target=forecast[horizon_days-1]; projected=icebergs_projected(horizon_days*24)['icebergs']; risk=iceberg_risk_grid(projected,target.shape,horizon_days*24)
    try:path_rc,total_cost=find_route(target,start,goal,risk,vessel_profile)
    except ValueError as e:raise HTTPException(422,str(e)) from e
    path=[rc_to_latlon(r,c) for r,c in path_rc]; iv=np.array([target[r,c] for r,c in path_rc]); rv=np.array([risk[r,c] for r,c in path_rc])
    return {'path':[{'lat':a,'lon':b} for a,b in path],'waypoints':len(path),'total_cost':total_cost,'distance_km':_distance(path),'mean_ice_concentration':float(iv.mean()),'max_ice_concentration':float(iv.max()),'high_ice_fraction':float(np.mean(iv>=.75)),'max_iceberg_risk':float(rv.max()),'horizon_days':horizon_days,'vessel_profile':vessel_profile,'forecast_dataset':d['meta']}
@app.post('/api/reload')
def reload_dataset():
    global _dataset; _dataset=None; get_dataset(); return {'status':'reloaded'}
