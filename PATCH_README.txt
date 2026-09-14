ANTARCTIC NAVIGATOR v0.6.1 - RELEASE VALIDATION FIX

This patch fixes the two failures reported by:
  python scripts\run_full_validation.py --horizon 3 --vessel standard

FIX 1 - self_check.py
The route API contract requires geometry.projection = EPSG:3031.
This patch restores/verifies that contract through the patched backend/main.py.

FIX 2 - route_robustness.py
The previous script relied on environment defaults after importing backend.main.
If a stale module state or shell setting was present, get_dataset() could report
real_data_active=false even though navigator_bundle.json existed and
validate_real_bundle.py passed.

The patched script explicitly forces:
  api.USE_REAL = True
  api.ALLOW_SYNTHETIC_FALLBACK = False
and checks that the real navigator bundle exists before loading it.
It also passes the real OSCAR/ERA5 forcing into the sea-ice forecast so the
robustness test uses the same environmental inputs as the application model.

IMPORTANT:
- Do NOT delete backend/data/real/navigator_bundle.json.
- Do NOT enable synthetic fallback for release validation.
- This patch does not fabricate or repair missing scientific observations.
- The historical BYU and NSIDC checks remain data-dependent and are reported
  as BLOCKED only if the historical archives are not present in the project.

VALIDATED ON THE CONSOLIDATED v0.6.1 PACKAGE:
  self_check: PASS
  real_bundle: PASS
  route_robustness: PASS
  full validation exit code: 0

Expected key result:
  SELF_CHECK_OK ... 'mission_aware_routes': ['A', 'B', 'C']
  route_robustness data_mode: real_seaice_usnic_icebergs
  route_robustness reroute_success_rate: 1.0 for 5/10/20 km tests

INSTALL:
1. Close the running FastAPI/Vite terminals.
2. Back up your project folder.
3. Extract this patch into:
   C:\Users\user\Documents\antarctic-navigator\
   and allow replacement of the five listed files.
4. Do not extract the patch as an extra nested project folder.
5. Run the validation commands in the response supplied with this patch.
