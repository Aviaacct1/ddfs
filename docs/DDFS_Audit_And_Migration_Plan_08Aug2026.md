# DDFS: copy audit, wiring audit and the order to move it into git

Version 1.0 - 8 August 2026 - Avia Solutions - DRAFT

Produced against the method in `HANDOVER_Tool_To_Git_08Aug2026.md` (the Meridian migration note) and
the estate index v9. Every finding below carries the file or command that produced it. Nothing here
is inferred from recall.

Repo name, per the naming register: `ddfs`, lowercase, private, on `Aviaacct1`. DDFS is a module other
tools use, so it takes no `avia-` prefix under the products rule and keeps its bare name.

---

## 1. Headline

The DDFS position is better than the Meridian position and worse in a different way.

There are **not** five divergent code trees. There is **one** code tree, at
`C:\Users\Carte\OneDrive\Avia\Model_refs`, and it holds every Python module, every fixture and every
pack. No second copy of any `.py` file exists anywhere searched.

What has fragmented is the **surfaces and the wiring**. Four separate copies of the front ends exist
at three different vintages, two of the three shipped HTML surfaces are superseded but still served,
and two substantial pieces of built work are reachable from nothing at all. Your instinct that the
work is not all wired to one engine is correct, and section 3 names exactly which parts.

Second point, and it changes the shape of the migration: **Model_refs is not a DDFS folder.** It holds
DDFS and the Greenwich financial model in the same directory, 87 entries, no subfolder separation. A
`git init` in Model_refs would put the financial model, its client demo workbooks and two 40MB `.xlsm`
engines into the `ddfs` repo. The migration is therefore a split, not a move.

Source: directory listing and file-by-file comparison of `C:\Users\Carte\OneDrive\Avia`, `C:\Avia`,
`E:\Avia`, `C:\src` and Egnyte `/Shared/Company Data/18 Products`, 8 August 2026.

---

## 2. The copies

| # | Location | What it holds | Vintage | Under git |
|---|---|---|---|---|
| 1 | `C:\Users\Carte\OneDrive\Avia\Model_refs` | 10 Python modules, 3 HTML surfaces, 2 JS report generators, 43 fixtures, 2 packs, the runner `.bat` | 18-24 July 2026 | No |
| 2 | `C:\Users\Carte\OneDrive\Avia\Jess Pack - DDFS - 19 July 2026` | `ddfs_front_v1.html`, `zagreb_oracle_run_v02.tsv`, four method comparison TSVs, the v0.2 report `.docx`, the oracle diff `.xlsx` | 19 July 2026 | No |
| 3 | Egnyte `/Shared/Company Data/18 Products/DDFS/Application` | `ddfs_front_v1.html` (426,738 bytes), README for Jess | 19 July 2026 | No |
| 4 | `C:\Users\Carte\OneDrive\Avia\09f DDFS Bridge Front End v0 - 18 July 2026.html` | an earlier v0 front end, MD5 differs from `Model_refs\ddfs_front_v0.html` | 18 July 2026 | No |
| 5 | `E:\Avia\Knowledge Programme` | 14 DDFS specification notes, including note 23 at v2 and v3 plus an unnumbered third variant | 18-20 July 2026 | No |
| 6 | `C:\Avia\Neptune` | `07_extract_ddfs.py`, `ddfs_schedules.parquet`, `Summary_DDFS_Tables.xlsx` | engagement work, not the tool | No |

Source: AviaSolutions Analysis, directory listings and MD5 comparison, 8 August 2026.

**No `.git` directory exists in any DDFS location.** The only repositories on the searched drives are
`C:\Avia\avia_forecast_build` (Atlas, no remote), `E:\Avia\Extract`, `E:\Avia\Claude Working\avia-website`,
`E:\Avia\Observatory Website` and `C:\src\meridian` (migrated today). So `git init` is correct for
DDFS, and there is no history at risk. This is the one Meridian trap that does not apply.

**Divergences found in the common set.** `ddfs_front_v1.html` exists at three sizes: 428,001 bytes in
Model_refs (23 July, v1.7), and 426,738 bytes in both the Jess Pack and on Egnyte (19 July). The two
19 July copies match each other by size; the Model_refs copy is four days newer and is the one the
service serves. `ddfs_front_v0.html` differs by MD5 from the OneDrive root copy of the same page.
`zagreb_oracle_run_v02.tsv` exists in both the Jess Pack and the fixtures folder, and the fixtures
copy is the one the live tool reads.

**Single-copy files.** None. Every DDFS file in copies 2, 3 and 4 has a counterpart in Model_refs.
This is the material difference from Meridian, where 15,331 lines existed on one side only.

---

## 3. What is built and not wired

This is the substance of your concern, and it is specific rather than general.

**The superset report generator is reachable from nothing.** `ddfs_report_gen_v01.js` (14,122 bytes)
and `ddfs_report_gen_v02.js` (18,741 bytes) are referenced by no Python module, no HTML surface and
no batch file. The service whitelist is three HTML files and serves no JavaScript. The live page
contains no report or `.docx` generation at all. The Design Day report that went to the Jess Pack as
a client deliverable therefore cannot be produced from the tool as it stands: it was produced beside
it. Note 36 specified that generator; it is built and it is orphaned.

**`ddfs_bridge.py` supplies two constants and nothing else.** The module holds 23 functions,
including the whole canonical and CAST emit chain (`canonical_rows`, `emit_canonical`, `emit_cast`),
the AOG ledger (`aog_ledger`, `emit_aog`), the transfer sheet (`emit_transfersheet`), the growth and
time-of-day build (`build_year_tables`, `generate_growth`, `read_tod`) and the oracle diff
(`run_oracle_diff`). `ddfs_service.py` line 195 imports `MIN_TURN` and `MAX_TURN` from it. Nothing
else in the running tool touches any of the 23 functions. The 43 `canonical_ahb_*`, `cast_ahb_*` and
`aog_ahb_*` fixtures exist to test a chain the live tool does not call.

**`ddfs_zagreb_oracle.py` is not imported by the service.** It is imported only by `ddfs_ladder.py`.
The live endpoint `/api/zagreb_forecast` reads the pinned file
`ddfs_bridge_fixtures/zagreb_oracle_run_v02.tsv` and returns rows from it. Its docstring says so
plainly, so this is deliberate and it holds up: the live answer always matches the pinned increment.
It does mean the tool ships a frozen Zagreb answer, and that a reader who assumes the forecast years
are computed on request will be wrong. State it on the page or accept that it will be asked in review.

**Two superseded surfaces are still served.** `/cockpit` now returns `ddfs_live.html` (correct, per
note 41), but `ddfs_cockpit.html` remains on disk and remains in the service whitelist, so it is
still reachable if any link points at it. `ddfs_front_v0.html` is superseded, is not whitelisted, and
is a straightforward orphan.

**The Studio runs on fixtures only.** `ddfs_front_v1.html` calls no `/api/` endpoint. That matches
note 41, which names it the internal review environment on embedded fixtures. Not a fault, but it
means the copy Jess has and the copy on Egnyte can never disagree with the engine, because they never
ask it.

**One owner per constant is broken.** The `ICAO` equipment class map is defined in `ddfs_service.py`
and again in `ddfs_ladder.py`; `ddfs_pack_emit.py` imports it from `ddfs_ladder`. Two definitions of
the same aircraft class table, and the service uses its own.

**Circular imports resolved by deferral.** `ddfs_service` imports `ddfs_towerlog` at module level,
while `ddfs_towerlog` imports `ddfs_service` inside two functions, and `ddfs_hindcast` imports
`ddfs_service` inside one. This works today and will fail the first time either module is imported in
a different order, which is exactly what a container or a service manager does differently.

---

## 4. Faults that will break on the workstation

These are the reasons a clone plus a data root will not run, and they need fixing before the clone
test can pass rather than after.

**Cowork session mount paths are compiled into the tool.** Three modules glob for a sandbox path that
only exists inside a Claude session:

| Module | Line | Hardcoded path |
|---|---|---|
| `ddfs_oag_expand.py` | 47, 51 | `/sessions/*/mnt/C:--Avia/` then `C:\Avia\` |
| `ddfs_pack_emit.py` | 34, 38 | `/sessions/*/mnt/C:--Avia/` then `C:\Avia\` |
| `ddfs_towerlog.py` | 259, 263 | `/sessions/*/mnt/C:--Avia/2025 Towerlog.xlsx` then `C:\Avia\...` |

Source: `grep` of `Model_refs\ddfs_*.py`, 8 August 2026.

The estate index records this as "session-portable store paths with stale-mount filtering", which is
what it was built for. On the workstation both branches are wrong: the glob finds nothing and the
fallback points at a drive letter that will not hold the stores. This must move to `AVIA_LOCAL_CACHE`
through a `config.py`, per the layout decision in the Meridian note.

**No `AVIA_LOCAL_CACHE` and no `config.py`.** DDFS reads four environment variables in total:
`AVIA_*` in `ddfs_oag_expand.py`, `AVIA_ENGINE_BUNDLE` in `ddfs_pack_emit.py`, `PORT` in
`ddfs_service.py`, `DDFS_ORACLE_OUT` in `ddfs_zagreb_oracle.py`. There is no single resolver. Meridian
proved the value of one variable and one config module; DDFS has neither.

**No `requirements.txt`, no `check_env.py`, no `.gitignore`, no README.** All four are absent from
Model_refs. The Meridian note is explicit that provisioning is five steps and the fifth is
`check_env.py`, and that installing a tool's dependencies into a shared interpreter changes every
other tool on the host. DDFS will be the second or third tool on that workstation.

**Two interpreters in play.** `__pycache__` holds both `cpython-310` and `cpython-312` builds of the
DDFS modules. `ddfs_service` was last compiled under 3.10; `ddfs_ladder`, `ddfs_towerlog` and
`ddfs_hindcast` under 3.12. Pin one, and make `check_env.py` fail on the other.

**Nothing must be committed from the data side.** `C:\Avia\oag.duckdb`, `C:\Avia\sabre.duckdb`,
`C:\Avia\2025 Towerlog.xlsx`, `avia_forecast_build\webapp\data\cockpit.json` (5.5MB) and the two 40MB
`.xlsm` engines in Model_refs all stay out. So does `access_password.txt`, which `ddfs_service.py`
reads from beside itself. That last one is the secrets item: if it exists it must be gitignored before
the first `git add`, not after.

---

## 5. Proposed repo shape

```
ddfs/
  config.py                    resolves every store from AVIA_LOCAL_CACHE
  check_env.py                 exits non-zero when a store, package or interpreter is wrong
  requirements.txt             what the workstation runs, nothing else
  .gitignore                   written before the first git add
  README.md
  ddfs_service.py              the service
  ddfs_live.html               the unified tool, served at / and /cockpit
  ddfs_oag_expand.py  ddfs_method_module.py  ddfs_pack_emit.py
  ddfs_hindcast.py    ddfs_towerlog.py       ddfs_bridge.py
  ddfs_zagreb_oracle.py  ddfs_ladder.py
  ddfs_report_gen_v02.js       wired, or attic with the reason
  ddfs_packs/                  ZAG_secondary_2025.json, BLQ_Baseline_2025
  ddfs_bridge_fixtures/        43 fixtures + abha_design_days
  studio/ddfs_front_v1.html    the internal review environment, /demo
  attic/                       ddfs_cockpit.html, ddfs_front_v0.html,
                               ddfs_report_gen_v01.js, one line of reason each
  docs/                        notes 23, 28, 31, 32, 36, 37 v2, 38, 39, 41
```

Greenwich stays in Model_refs until it gets its own repo, and Model_refs stops being a code location
the moment both are out.

**Commit order**, per the Meridian note:

1. `.gitignore` first, then `git add -A -n` and read the list before trusting it.
2. Baseline commit and tag: the DDFS files exactly as they stand on 24 July, nothing renamed. This is
   the revert point.
3. `git mv` the superseded surfaces to `attic/`, one reason per file, committed there rather than
   deleted.
4. Structural moves one per commit: `studio/`, `docs/`.
5. Then, and only then, the fixes in section 4 as separate commits, so each is revertible on its own.

---

## 6. The Atlas link, and why it does not justify waiting

DDFS reads Atlas at exactly one place: `ddfs_pack_emit.py` line 33 resolves
`avia_forecast_build/webapp/data/cockpit.json`, the engine bundle, read-only, 5,554,450 bytes as at
20 July 2026. Everything downstream of that runs on the emitted pack. The two tools meet at a file,
not in code.

That means the recommendation is to pin the bundle as a versioned contract rather than to wait:

- put a schema version in the pack and in the emitter, and refuse rather than default when it does
  not match;
- commit a small `cockpit.json` fixture, enough to exercise the emitter without carrying the 5.5MB
  bundle into the repo;
- add a check that fails loudly when Atlas changes the bundle shape.

Meridian's recurring bug shape is a missing input substituting a neutral default in silence. The
Atlas handover is the next place that will happen, and a committed fixture plus a failing check is
what stops it. Waiting for Atlas to finish does not stop it, and it costs another fortnight of
divergence on a tool that is nearly at final testing.

---

## 7. Decisions needed before anything moves

1. **The report generator.** Wire `ddfs_report_gen_v02.js` into the tool as a Stage 5 output, or send
   it to the attic with the reason recorded. It is a client deliverable path, so my view is wire it,
   but it is a build slot rather than a migration step.
2. **`ddfs_bridge.py`.** Keep the whole module and its 43 fixtures, or reduce it to the two constants
   the service actually uses and attic the rest. My view is keep it and its fixtures for now, and
   record it in the switch register as a capability not currently reachable, with the test that would
   let it be turned back on. It is the same fault Meridian had: disciplined work missing its last move.
3. **The frozen Zagreb answer.** Say on the page that the forecast years come from a pinned oracle
   run, or make the endpoint call the oracle at store day. The first is one line and honest; the
   second is a build slot.
4. **Egnyte and the Jess Pack copies.** Both hold 19 July front ends that are now four days behind and
   two design generations behind. Replace them with a share link into the repo, or refresh and date
   them, so nobody reviews a superseded page.
5. **Python version.** Pin 3.12 to match the Meridian workstation provisioning, or state why DDFS
   differs.

---

Avia Solutions Limited. All rights reserved.
