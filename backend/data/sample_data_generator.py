"""Create an offline, explicitly synthetic demo field."""
from __future__ import annotations
import json,os,sys
from pathlib import Path
import numpy as np
BACKEND_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(BACKEND_DIR))
from config import GRID_COLS,GRID_ROWS,latlon_grids
OUT=Path(__file__).resolve().parent/'sample'/'synthetic_dataset.json'
def main():
    rng=np.random.default_rng(42); lat,lon=latlon_grids(); south=np.clip((-lat-65)/10,0,1); bands=0.12*(0.5+0.5*np.sin((lon-10)/8)); noise=rng.normal(0,0.035,lat.shape)
    conc=np.clip(0.08+0.55*south+bands+noise,0,0.98); wall=(lon>34)&(lon<41)&(lat<-68.5)&(lat>-72.8); gap=(lon>36.8)&(lon<38.5)&(lat>-69.3)&(lat<-68.2); conc[wall&~gap]=np.maximum(conc[wall&~gap],0.94)
    cu=0.12*np.cos(np.radians(lat*5)); cv=0.08*np.sin(np.radians(lon*2)); wu=7+2*np.sin(np.radians(lon*2.5)); wv=-2+2.5*np.cos(np.radians(lat*3))
    locs=[(-69.2,24),(-70.1,28),(-68.7,33),(-71,43),(-69.6,48),(-70.4,54),(-68.8,61),(-71.1,67),(-69,73),(-70,80),(-67.9,18),(-72,12),(-68.2,42),(-71.7,58),(-69.3,7),(-67.5,85)]
    ice=[{"id":f"A-{i:02d}","lat":la,"lon":lo,"length_km":round(1.5+(i%7)*0.7,1)} for i,(la,lo) in enumerate(locs,1)]
    data={"meta":{"dataset_kind":"synthetic","source":"Offline synthetic demo generator","day_of_year":245,"generated_seed":42,"grid":{"rows":GRID_ROWS,"cols":GRID_COLS}},"lat_grid":lat.tolist(),"lon_grid":lon.tolist(),"concentration":conc.tolist(),"current_u":cu.tolist(),"current_v":cv.tolist(),"wind_u":wu.tolist(),"wind_v":wv.tolist(),"icebergs":ice}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
if __name__=='__main__': main()
