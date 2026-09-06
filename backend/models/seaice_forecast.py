"""Lightweight transparent sea-ice forecast baseline."""
from __future__ import annotations
import numpy as np
def forecast_concentration(concentration,day_of_year,lat_grid,horizon_days=3):
    h=max(1,min(7,int(horizon_days))); base=np.asarray(concentration,dtype=float)
    lat_norm=(lat_grid-lat_grid.min())/max(1e-9,lat_grid.max()-lat_grid.min()); amp=0.10+0.08*(1-lat_norm)
    phase=2*np.pi*(day_of_year-60)/365.25; out=[]
    for d in range(1,h+1):
        alpha=max(0.18,0.88-0.09*(d-1)); shift=amp*0.18*np.sin(phase+d/14.0); out.append(np.clip(alpha*base+(1-alpha)*np.clip(base+shift,0,1),0,1))
    return np.stack(out)
