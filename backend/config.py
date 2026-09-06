"""Configuration for the Antarctic Navigator prototype."""
from __future__ import annotations
import numpy as np
GRID_LAT_MIN=-75.0; GRID_LAT_MAX=-65.0; GRID_LON_MIN=0.0; GRID_LON_MAX=90.0
GRID_ROWS=60; GRID_COLS=180
INDIAN_STATIONS={"Maitri":{"lat":-70.7667,"lon":11.7333},"Bharati":{"lat":-69.4068,"lon":76.1953}}
def latlon_grids():
    lats=np.linspace(GRID_LAT_MIN,GRID_LAT_MAX,GRID_ROWS); lons=np.linspace(GRID_LON_MIN,GRID_LON_MAX,GRID_COLS)
    return np.meshgrid(lats,lons,indexing="ij")
def latlon_to_rc(lat:float,lon:float):
    r=int(round((lat-GRID_LAT_MIN)/(GRID_LAT_MAX-GRID_LAT_MIN)*(GRID_ROWS-1))); c=int(round((lon-GRID_LON_MIN)/(GRID_LON_MAX-GRID_LON_MIN)*(GRID_COLS-1)))
    return max(0,min(GRID_ROWS-1,r)),max(0,min(GRID_COLS-1,c))
def rc_to_latlon(row:int,col:int):
    return (float(GRID_LAT_MIN+row/(GRID_ROWS-1)*(GRID_LAT_MAX-GRID_LAT_MIN)),float(GRID_LON_MIN+col/(GRID_COLS-1)*(GRID_LON_MAX-GRID_LON_MIN)))
