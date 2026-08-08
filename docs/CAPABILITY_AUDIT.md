# DDFS capability audit

Version 1.0 - 8 August 2026 - Avia Solutions

Run against the `baseline-24Jul2026` tag, which is the tool exactly as it stood on 24 July 2026 after
being separated from the Greenwich financial model. Method per `HANDOVER_Tool_To_Git_08Aug2026.md`
section 3. The audit is run after reconciliation, not before, so the orphan list is the real one.

Tracked: 67 files, 9 Python modules, 4 HTML surfaces, 2 JavaScript report generators, 43 fixtures,
2 packs.

---

## 1. Capability built and not reachable

| Item | Size | Reachable from | Position |
|---|---|---|---|
| `ddfs_report_gen_v02.js` | 18,741 bytes | nothing | The superset Design Day report generator of note 36. No Python module, HTML surface or batch file references it. The service whitelist is three HTML files and serves no JavaScript. The live page contains no report or `.docx` generation. |
| `ddfs_report_gen_v01.js` | 14,122 bytes | nothing | Superseded by v02. Attic. |
| `ddfs_bridge.py`, 21 of 23 functions | 21,796 bytes | two constants only | `ddfs_service.py` imports `MIN_TURN` and `MAX_TURN`. The canonical and CAST emit chain, the AOG ledger, the transfer sheet, the growth and time-of-day build and the oracle diff are called by nothing in the running tool. |
| 24 `canonical_ahb_*`, `cast_ahb_*`, `aog_ahb_*` fixtures | circa 320KB | `ddfs_bridge` selftests | Fixtures for a chain the live tool does not call. Keep while the module is kept. |

The report generator produced the client deliverable in the 19 July Jess Pack. It was produced beside
the tool, not from it, so the tool as it stands cannot make that report.

Source: `grep` for cross-references across `*.py`, `*.html`, `*.js` and `*.bat` in the tracked tree,
8 August 2026.

## 2. Orphaned modules

None. Every Python module is imported by at least one other, or is an entry point. The orphan problem
in DDFS is at the JavaScript and function level, not the module level, which is why section 1 rather
than this section carries the finding.

## 3. Config keys read and never written

| Variable | Read in | Written or documented anywhere |
|---|---|---|
| `AVIA_*` (store root) | `ddfs_oag_expand.py:44` | No |
| `AVIA_ENGINE_BUNDLE` | `ddfs_pack_emit.py:30` | No |
| `DDFS_ORACLE_OUT` | `ddfs_zagreb_oracle.py:118` | No |
| `PORT` | `ddfs_service.py:47` | `Run Avia DDFS.bat` |
| `DDFS_PASSWORD` / `FORECAST_PASSWORD` | `ddfs_service.py` docstring | No |

There is no `config.py` and no single resolver. Three of the five are set by nobody, so the fallback
branch is what actually runs, and section 5 shows where those fallbacks point.

## 4. Data files named in code and absent from the repo

| Named | Where | Status |
|---|---|---|
| `avia_forecast_build/webapp/data/cockpit.json` | `ddfs_pack_emit.py:33` | The Atlas engine bundle, 5,554,450 bytes as at 20 July 2026. Correctly outside the repo. Needs a committed cut-down fixture so the emitter can be exercised without it. |
| `method_comparison.tsv` | generated output | Not a missing input. |
| `oag.duckdb`, `sabre.duckdb` | `ddfs_oag_expand.py` | Stores. Correctly outside the repo, resolved from the data root. |
| `2025 Towerlog.xlsx` | `ddfs_towerlog.py` | Client AODB export. Correctly outside the repo. |

Nothing required by the tool is missing from the repo. Everything absent is data, and belongs on the
workstation data root.

## 5. Path resolution faults

Three modules resolve a store by globbing a Claude session mount, then fall back to a fixed drive
letter. Neither branch is right on the workstation.

| Module | Line | Resolution |
|---|---|---|
| `ddfs_oag_expand.py` | 47, 51 | `/sessions/*/mnt/C:--Avia/<name>` then `C:\Avia\<name>` |
| `ddfs_pack_emit.py` | 34, 38 | `/sessions/*/mnt/C:--Avia/<rel>` then `C:\Avia\<rel>` |
| `ddfs_towerlog.py` | 259, 263 | `/sessions/*/mnt/C:--Avia/2025 Towerlog.xlsx` then `C:\Avia\2025 Towerlog.xlsx` |

Must resolve from `AVIA_LOCAL_CACHE` through a `config.py`. Per the Meridian lesson, the resolver
should search upward for a landmark file and report every path it tried when it fails, rather than
returning a default in silence.

## 6. Duplicate definitions and shadowed files

**`ICAO` aircraft class map defined three times**: `ddfs_ladder.py:21`, `ddfs_service.py:57`,
`ddfs_zagreb_oracle.py:24`. `ddfs_pack_emit.py` imports it from `ddfs_ladder`, so the service and the
oracle each use their own copy. One owner, imported by the rest.

**The oracle writes into the folder that holds its own regression pin.** `ddfs_zagreb_oracle.py:367`
defaults its output to `ddfs_bridge_fixtures/zagreb_oracle_run.tsv`, and the pin the regression
compares against is `ddfs_bridge_fixtures/zagreb_oracle_run_v02.tsv` in the same directory. The two
files are currently byte-identical (MD5 match, 77,937 bytes each). A run therefore writes a result
into the fixtures directory beside the pin that is meant to check it. This is the Meridian fault that
released a watcher early on a stale result, one step short of happening. Pins and outputs must not
share a directory: fixtures hold pins only, and the oracle writes to a gitignored output path or the
data root via `DDFS_ORACLE_OUT`.

`zagreb_oracle_run_v01.tsv` (82,019 bytes) is a superseded run output held in fixtures. Attic or delete.

**Three fixture pairs are byte-identical across different forecast years**: `cast_ahb_2040` equals
`cast_ahb_2045`, `aog_ahb_2040` equals `aog_ahb_2045`, `aog_ahb_2025` equals `aog_ahb_2030`. The
corresponding `canonical_ahb` files do differ between those years, so this is either flat growth in
those measures or a fixture copied and not regenerated. It needs confirming before either is used as
a test target, because a test that passes against a copied fixture proves nothing about the year it
claims to cover.

## 7. A control that enforces nothing

`ddfs_service.py:49` defines `WHITELIST = {"ddfs_live.html", "ddfs_front_v1.html",
"ddfs_cockpit.html"}` and the docstring states "Only whitelisted files are served; Model_refs holds
client models that must never go over the tunnel." The constant is referenced nowhere else in the
module. `_file()` opens whatever name it is passed and does not consult it.

Nothing is exposed today, because only three literal filenames reach `_file()` and no user input does.
The fault is that a stated control reads as enforced and is not, so the next person to add a route
will believe the whitelist is protecting them. Now that the repo root is `C:\src\ddfs` rather than
Model_refs, the client models are no longer beside the service, which reduces what a mistake would
cost. Either enforce the whitelist in `_file()` or delete it and the docstring claim. My view is
enforce it: the service runs behind a Cloudflare tunnel on licensed data.

## 8. Exception handling

19 handlers across 9 modules. One is silent: `ddfs_service.py:573`, in the Basic Auth path, where a
malformed header falls through to a 401. That is correct behaviour and needs no change. DDFS does not
have the Meridian fallback problem: no capability is lost inside a swallowed handler.

## 9. Default-off switches

Options are visibly present and honestly disabled in the unified page, with their ACI item numbers
against them, per note 41. That is the discipline the Meridian note asks for and it is already in
place. What is still needed is the register entry: each disabled option needs a named test that would
allow it to be turned on, so a switch cannot rest in the off position without an expiry.

Open items carried from note 41: ACI item 3 (per-season design days), item 4 (client-forecast
ingest), item 5 (annual and bi-annual emit), and the store-day rerun.

## 10. What a green suite does not test

The DDFS check counts are 54 unified page checks, 21 method module checks, 6 cockpit checks, plus the
module selftests and the byte-exact oracle regression. Six of eight Meridian defects on 8 August
passed a green suite and were found only by looking at the rendered output. The DDFS equivalent is
the chart palette, axis labelling, unit and period statements on every figure, and actual versus
forecast being clear. Those must be checked by eye on the rendered page before final testing signs off.

---

Avia Solutions Limited. All rights reserved.
