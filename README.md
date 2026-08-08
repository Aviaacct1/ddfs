# ddfs

Design day flight schedules. An Avia Solutions tool, and a module other Avia tools use.

Repo `ddfs` on `Aviaacct1`, private. One name for the product, the engine and the repo, per the
naming and structure register of 8 August 2026.

## What it is

A schedule-level design day builder and forecaster. `ddfs_service.py` serves the unified tool at
`ddfs_live.html` on port 8030, exposed as `ddfs.aviacortex.com` through the existing Cloudflare tunnel.
The tool runs five stages left to right: Base, Method, Design Day, Forecast, Outputs (note 41,
23 July 2026).

Growth reaches the tool through a **pack**. The pack is the interface: the Avia Global Forecast engine
(Atlas), an engagement pack such as the Zagreb oracle, and a client-supplied forecast all emit the
same pack grain, so everything downstream is identical whichever the source.

## Layout

```
ddfs_service.py            the service and the API
ddfs_live.html             the unified tool, served at / and /cockpit
ddfs_front_v1.html         the Studio, /demo: internal review on embedded fixtures
ddfs_oag_expand.py         schedule expansion off the OAG store
ddfs_method_module.py      the design day method catalogue
ddfs_pack_emit.py          engine bundle to DDFS pack
ddfs_hindcast.py           forecast from a pack, plus the ADAC 2024 acceptance run
ddfs_zagreb_oracle.py      the Zagreb engagement oracle, pack-driven
ddfs_ladder.py             the test ladder
ddfs_bridge.py             canonical / CAST / AOG emit chain
ddfs_towerlog.py           MZLZ AODB reconciliation
ddfs_report_gen_v02.js     superset Design Day report generator
config.py                  one resolver for every path the tool reads
check_env.py               host check, step 5 of provisioning
ddfs_aircraft.py           one owner for the ICAO code letter
ddfs_bridge_fixtures/      test pins, never run output
ddfs_packs/                emitted packs
runs/                      run output, gitignored
attic/                     superseded, with a reason each
docs/                      capability audit, migration plan, standing git note
```

## Data lives outside this repo

No store, no client model and no licensed data is ever committed here. The tool reads from the
workstation data root:

| What | Where |
|---|---|
| `oag.duckdb`, `sabre.duckdb` | data root |
| `2025 Towerlog.xlsx` | data root (MZLZ AODB export) |
| `cockpit.json` | the Atlas engine bundle, read-only |
| `Abha_DDFS_Engine_v2.xlsm`, `DesignDay_Template_v15.xlsm` | data root |

## Provisioning a host

Five steps, and the fifth is not optional.

1. `git clone <remote> C:\src\ddfs`
2. copy the data root
3. set `AVIA_LOCAL_CACHE` (and `AVIA_ENGINE_BUNDLE` if the Atlas bundle sits elsewhere)
4. `py -3.12 -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements.txt`
5. `.venv\Scripts\python check_env.py`

`check_env.py` exits non-zero when the interpreter, a package or a store is wrong, and reports the
coverage of each store it found, so any number the tool produces can be traced to the data behind it.
`python config.py` on its own prints where every store resolved from and why.

DDFS is pinned to Python 3.12. Give it its own virtual environment: the workstation runs several
tools, and installing one tool's dependencies into a shared interpreter changes every other tool.

## Working rule

Git is the single source of truth. Pull before editing, commit and push after. Editing happens on the
Dev PC, running happens on the workstation, and deploy means the workstation pulls and restarts the
service. Nothing is edited anywhere that is not synced to this repo.

Copyright Avia Solutions Limited. All rights reserved.
