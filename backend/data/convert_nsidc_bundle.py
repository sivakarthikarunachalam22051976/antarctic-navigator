"""Convert an NSIDC South Polar NetCDF file into the app bundle."""
from __future__ import annotations
import json,sys
from pathlib import Path
import numpy as np,xarray as xr
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator
BACKEND_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(BACKEND_DIR))
from config import latlon_grids
RAW=BACKEND_DIR/'data'/'real'/'raw'; OUT=BACKEND_DIR/'data'/'real'/'navigator_bundle.json'
def main():
    files=sorted(RAW.glob('*.nc'))
    if not files:raise FileNotFoundError(f'No NetCDF files found in {RAW}')
    src=files[-1]
    with xr.open_dataset(src,mask_and_scale=True) as ds:
        names=[n for n in ('cdr_seaice_conc','nsidc_south','seaice_conc') if n in ds]
        if not names:names=[n for n in ds.data_vars if 'conc' in n.lower() and 'seaice' in n.lower()]
        if not names:raise ValueError('No sea-ice concentration variable found.')
        da=ds[names[0]].squeeze(drop=True); x=np.asarray(da['x']); y=np.asarray(da['y']); v=np.asarray(da.values,float)
        while v.ndim>2:v=v[0]
        v=np.where(np.isfinite(v),v,np.nan); finite=v[np.isfinite(v)]
        if finite.size and np.nanpercentile(finite,95)>1.5:v/=100
        v=np.clip(v,0,1); lat,lon=latlon_grids(); tx,ty=Transformer.from_crs('EPSG:4326','EPSG:3412',always_xy=True).transform(lon,lat)
        if y[0]>y[-1]:y=y[::-1];v=v[::-1,:]
        if x[0]>x[-1]:x=x[::-1];v=v[:,::-1]
        f=RegularGridInterpolator((y,x),v,bounds_error=False,fill_value=np.nan); conc=np.nan_to_num(f(np.column_stack([ty.ravel(),tx.ravel()])).reshape(lat.shape),nan=0); conc=np.clip(conc,0,1)
        doy=int(ds.attrs.get('day_of_year',1)) if ds.attrs else 1
    z=np.zeros_like(conc); bundle={'meta':{'dataset_kind':'real_seaice_only','source':f'NSIDC NetCDF: {src.name}','projection':'EPSG:3412','day_of_year':doy,'note':'Only sea-ice is real in this bundle; add real wind/current/iceberg adapters before claiming an all-real dataset.'},'lat_grid':lat.tolist(),'lon_grid':lon.tolist(),'concentration':conc.tolist(),'current_u':z.tolist(),'current_v':z.tolist(),'wind_u':z.tolist(),'wind_v':z.tolist(),'icebergs':[]}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(bundle,separators=(',',':')),encoding='utf-8'); print(OUT)
if __name__=='__main__':main()
