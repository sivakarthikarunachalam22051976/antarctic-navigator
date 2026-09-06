"""Simplified iceberg free-drift approximation."""
from __future__ import annotations
import math
def advect_iceberg(lat,lon,current_uv,wind_uv,dt_hours=6.0):
    uc,vc=map(float,current_uv); uw,vw=map(float,wind_uv); angle=math.radians(20+18*max(0,min(1,(abs(lat)-60)/20)))
    uwr=uw*math.cos(angle)-vw*math.sin(angle); vwr=uw*math.sin(angle)+vw*math.cos(angle)
    u=uc+0.018*uwr; v=vc+0.018*vwr; sec=float(dt_hours)*3600; mlat=111320; mlon=max(10000,111320*math.cos(math.radians(lat)))
    return lat+v*sec/mlat,lon+u*sec/mlon
