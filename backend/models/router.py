"""Explainable A* routing over an ice + iceberg risk field."""
from __future__ import annotations
import heapq, math
import numpy as np
VESSEL_PROFILES={"standard":{"ice_penalty":11.0,"ice_exponent":2.0,"blocked_threshold":0.90,"iceberg_weight":18.0},"ice_capable":{"ice_penalty":6.0,"ice_exponent":1.7,"blocked_threshold":0.98,"iceberg_weight":12.0}}
def _heuristic(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
def _step_cost(ice,diag,risk,profile):
    distance=math.sqrt(2.0) if diag else 1.0
    return distance*(1.0+profile["ice_penalty"]*max(0.0,ice)**profile["ice_exponent"]+profile["iceberg_weight"]*max(0.0,risk))
def find_route(concentration,start,goal,iceberg_risk=None,vessel_profile="standard"):
    profile=VESSEL_PROFILES.get(vessel_profile,VESSEL_PROFILES["standard"]); rows,cols=concentration.shape
    risk=np.zeros_like(concentration,dtype=float) if iceberg_risk is None else np.asarray(iceberg_risk,dtype=float)
    if concentration[start]>=profile["blocked_threshold"] or concentration[goal]>=profile["blocked_threshold"]: raise ValueError("Start or destination lies inside an impassable ice cell for this vessel profile.")
    frontier=[(0.0,start)]; came={start:None}; cost={start:0.0}
    for _ in range(rows*cols*4):
        if not frontier: break
        _,cur=heapq.heappop(frontier)
        if cur==goal: break
        r,c=cur
        for dr,dc in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            nr,nc=r+dr,c+dc
            if nr<0 or nr>=rows or nc<0 or nc>=cols or concentration[nr,nc]>=profile["blocked_threshold"]: continue
            nxt=(nr,nc); new=cost[cur]+_step_cost(float(concentration[nr,nc]),dr!=0 and dc!=0,float(risk[nr,nc]),profile)
            if nxt not in cost or new<cost[nxt]: cost[nxt]=new; came[nxt]=cur; heapq.heappush(frontier,(new+_heuristic(nxt,goal),nxt))
    if goal not in came: raise ValueError("No safe route exists through the current forecast risk field.")
    path=[]; cur=goal
    while cur is not None: path.append(cur); cur=came[cur]
    path.reverse(); return path,float(cost[goal])
