# Moving an Avia tool into git: what the Meridian migration taught, and the order to do it in

Version 1.0 - 8 August 2026 - Avia Solutions - standing document

Paste this at the start of any session that moves an Avia tool into git: Atlas, Greenwich, DDFS,
ask-avia, the websites. It exists so no session repeats a day that has already been paid for.

Everything below was established by doing it to Meridian on 8 August 2026, and every claim carries
the evidence that produced it. Where a lesson cost hours, that is said, because a reader deciding
whether to skip a step should know what skipping it costs.

---

## 1. The naming and structure decisions. Settled. Do not reopen them.

Agreed by John on 8 August 2026 and recorded in `NAMING_AND_STRUCTURE_REGISTER_08Aug2026.md` v2.0.

**One name per tool**, covering the product, the engine and the repo. A tool with two names grows a
second version of itself under the other one.

**Products keep their names, bare. Everything else takes the `avia-` prefix.** The prefix is
carrying information rather than noise: it separates the things that are sold from the things that
support them.

| Repo | What it is | Was called |
|---|---|---|
| `meridian` | route forecasting, sold as Meridian | QSI tool, Avia Cortex QSI, the app, AviaDev |
| `atlas` | the Global Forecast, the OGF | Global Forecast, avia_forecast_build, the Cockpit |
| `greenwich` | airport financial model and business plans | financial model, Forecast Studio, 09e Studio |
| `ddfs` | design day schedules, a module other tools use | DDFS, the DDFS Cockpit |
| `ask-avia` | internal, interrogates the data library | AIP. **Not `aip`**: that is the Aeronautical Information Publication, and Meridian's own airfield advisory already uses it in that sense |
| `avia-extract` | the 25-year harvest | data extraction |
| `avia-website` | aviasolutions.com | `acct1.website` |
| `avia-tao-website` | the Observatory product site | |

**Lowercase with hyphens.** The workstation and any future container are Linux and case-sensitive,
the Dev PC is not, and git on Windows sets `ignorecase = true`. A repo created as `Meridian` and
referenced as `meridian` works on the Dev PC and fails on the workstation, and only on deployment.
This already happened once: `meridian` was created as `Meridian` and the first push went through a
redirect.

**Not repos, so nobody creates them later.** The Aviation Observatory is a platform and a brand. The
Cockpit is two run modes inside Atlas. Forecast Studio is Greenwich's front end. Engagement codenames
(Silvaria, Aquila, Iguana, Forth, Liguria) name deliverables, never repos, because a tool outlives an
engagement.

**Account.** `Aviaacct1` today, moving to a business organisation once everything is in and working.
GitHub transfers carry history, tags and redirects, so the move is a settings page. Superseded repos
are **archived**, not renamed: renaming `avia-forecast-poc` to `atlas` would make a proof of concept
look like the product's history.

**Layout.**

```
Dev PC          C:\src\<tool>\        one clone each, nothing else
                C:\Avia\              stores, until they move
                C:\assets\            imagery and fonts, in no repo
Workstation     E:\Avia\              THE single data root: stores, duckdb_tmp, assets
                C:\src\<tool>\        the deployed clones
OneDrive        documents only. No .py, no .duckdb, no .json a tool reads.
Egnyte          knowledge, client work, documents. No tool code, no stores.
```

`AVIA_LOCAL_CACHE` is the hinge. `config.py` resolves every store from it, so provisioning a host
changes one variable and no code. Protect that: one hardcoded path breaks it silently on the next
host.

---

## 2. Before you touch anything: count the copies

Meridian had **five**, and two handovers written the week before mentioned two of them.

1. `C:\AviaDev` the run tree, which was **already a git repo with thirty commits and four tags**
2. the OneDrive project tree, which held fifteen modules the run tree did not have
3. the git history itself
4. a 24 June snapshot on Egnyte at `18 Products/QSI/Application`, which the estate index still named
   as the code location
5. `C:\Avia\qsi-tool`, left by a `robocopy` in a transfer note, holding the API key in plain text on
   a path nobody was tracking

Find them before you decide which is canonical. Look in: the run path, the OneDrive project folder,
Egnyte under `18 Products`, anywhere a previous handover's commands wrote to, and `E:` and `C:` roots.

**Then check whether it is already a repo.** `Atlas` is: `C:\Avia\avia_forecast_build` has a `.git`
with no remote. Both Meridian handovers asserted there was no history to lose and prescribed
`git init` in a fresh folder, which would have abandoned thirty commits and the `pre-connection-fix`
rollback tag.

```powershell
Get-ChildItem -Recurse -Depth 3 -Directory -Filter .git | ForEach-Object {
  $r = $_.Parent.FullName
  "{0}  commits={1}  remote={2}" -f $r,
    (git -C $r rev-list --count HEAD 2>$null),
    ((git -C $r remote -v) -ne $null)
}
```

If it is a repo: keep it, add a remote, push. Renaming is a remote change and moving a folder is a
copy. Nothing that rewrites history belongs anywhere near this: no `rebase`, no `push --force`, no
`filter-branch`, no `reset --hard`.

---

## 3. Compare the copies file by file, not by the list you were handed

The single most expensive finding. A reconciler that moves the files a step names will report a tree
reconciled while whole modules exist on one side only, because a file present in one place looks
like working scratch.

On Meridian: 156 top-level Python files were common to both trees and 155 were byte-identical, which
is what "reconciled" was based on. **28 files existed on one side only and none was in git.** Fifteen
were substantive, 15,331 lines, including the previous pipeline, a 3,017-line calibration library
with 27 cases, the module written the previous day, and every script that ingests and validates the
OAG store. Eight of them existed nowhere else at all.

```powershell
# every top-level file on each side, then the two set differences
Get-ChildItem A\*.* -File | Select-Object -Expand Name | Sort-Object > a.txt
Get-ChildItem B\*.* -File | Select-Object -Expand Name | Sort-Object > b.txt
Compare-Object (Get-Content a.txt) (Get-Content b.txt)
# then hash everything that appears in both
```

Compare `.json` and `.csv` model inputs too, not just `.py`. A missing table substitutes a neutral
default in silence, which is the recurring bug shape in this estate.

Three tools do this properly and all three are now committed in `meridian`, none of them
QSI-specific, so point them at any tree:

- `audit_split.py` compares two trees file by file
- `missing_modules.py --from X --to Y` walks the import graph and reports what one tree needs and the
  other lacks
- `capability_audit.py --tree X --out CAPABILITY_AUDIT.md` reports orphaned modules, config keys read
  and never written, data files named in code and absent, swallowed exception handlers and shadowed
  duplicate filenames

Run the audit **after** the trees are reconciled, not before. The version run on an incomplete tree
has a wrong orphan list.

---

## 4. Commit order that keeps the history legible

1. **Bring the single-copy files in first**, before any folder is renamed or moved. Until that is
   done every later step risks working on the incomplete tree.
2. **Commit and tag the baseline.** One pure snapshot of what exists, so everything after it is
   revertible to a known point.
3. **Then the attic.** Working scratch goes to `attic/` with a one-line reason per file and gets
   **committed there**. A committed attic is a record; a deletion is a loss; a gitignored file is a
   file that exists on one machine only, which is the fault the repo exists to end. `git mv` keeps
   the history, so `git log --follow` still reads back.
4. **Then structural moves**, one per commit, so the diff reads as a move rather than a rewrite.

`.gitignore` before `git add`, never after, and simulate the staging list before trusting it:

```powershell
git add -A -n            # what WOULD stage
git add -A
git status --short | Select-String -Pattern "key|password|secret|duckdb|venv|_dt_cache"
```

That last line must return nothing.

**Results and data are not committable.** A 3 July result CSV was swept into Meridian's first commit
by `git add -A`, travelled to the workstation in the clone, and then a watcher waiting for that
night's run to produce the file found the stale one already there and released early. Exclude:
`*.duckdb`, `*.joblib`, `venv/`, `_dt_cache/`, generated `*.pptx` and `*.pdf`, machine config such as
`avia_config.json`, back-test master tables, and any `pretest_*` or result output.

---

## 5. The completeness proof is a clone that runs

Do not hand-assemble a clean folder. A clone contains exactly what is tracked, so a clone that runs
proves the repository is whole by construction. A hand-built folder proves only that you built it
correctly.

```powershell
git clone <remote> C:\src\<tool>
cd C:\src\<tool>
# then the tool's own checks, from the clone
```

**But a clone plus a data root is not a runnable host.** That mistake cost an hour on the workstation.
Provisioning is five steps and the last is not optional:

1. `git clone`
2. copy the data root
3. set `AVIA_LOCAL_CACHE` (and any store that lives elsewhere)
4. `py -3.12 -m pip install -r requirements.txt`
5. `py -3.12 check_env.py`

`check_env.py` exits non-zero when something required is missing or broken, and it earns its keep: on
the workstation it confirmed a numpy downgrade from 2.5.1 to 2.3.5, reported no failed uninstalls,
and ran five smoke tests. Its own docstring records why it exists, that pip reported a broken install
as a warning and exited zero.

**Install only what the host runs.** Meridian's `requirements.txt` listed streamlit for a legacy tool
the workstation does not run, and pip resolved starlette **down** from 1.6.0 to 1.3.1 to satisfy it.
Starlette is what the live portal server runs on. A tool nobody was using changed a dependency of the
tool in use, in a resolver step nobody reads. Legacy sets go in their own file.

**One virtual environment per tool on a shared host.** `check_env.py` prints the warning itself:
"virtualenv NO, this is a shared Python. Installing one tool's dependencies here changes every other
tool that uses this interpreter." The workstation will run four tools. That warning stopped being
theoretical on 8 August.

---

## 6. The traps, in the order they will cost you time

**Default-off switches are the main reason a tool is less capable than the work put into it.**
Meridian had five verified improvements switched off, each with sound reasoning in its own docstring,
none re-baselined: the whole Observatory deck path, the full-year capacity provider, DOT and DB1B for
US markets, the haul trim, the frequency discount. Plus ten connecting-feed parameters set only by
the back-test. The process was disciplined and missing its last move. Grep for environment variables
and command-line flags, and read section 2 of the capability audit for config keys read and never
written. **A default-off switch is a temporary state with an expiry, not a resting place**: record it
with the name of the test that would let it be turned on, and a switch with no test named against it
is unfinished work with a lid on.

**A green suite tells you nothing about what it was never asked.** Meridian's chart suite had 36
passing checks the whole time its palette used twenty colours, not one of which was in the brand
guide, including Office theme defaults and CSS seagreen. Those checks test what a chart says: title,
unit, period, source, gap handling. None tests what it looks like. Six of eight defects found on
8 August passed a green suite and were caught only by looking at the rendered output. **Look at the
artefact.**

**A fallback must report.** 234 swallowed exception handlers across 98 modules, and every capability
lost that week failed inside one. Fix the ones around a data load or a capability switch and leave
the rest.

**Find paths by landmark, never by counting folders.** Four modules resolved a sibling folder by
going up N levels and appending a name, each slightly differently, and one of them was the live entry
point. Moving the folder one level changed `app` to `C:\app`. A test failing loudly on import was the
only reason the live one came to light. Search upward for a file that must be there, and report the
paths tried when it is not found.

**One owner per constant.** The same load-factor target was defined in two modules, and a third
constant was kept equal to a fourth by a code comment asking whoever changed one to change the other.
Import it, do not restate it.

**Stores and runs must declare themselves.** A two-week schedule snapshot annualised as though it
were a full year, and a store double-loaded so it read twice the real figure, are the same fault:
something standing in for something else without saying so. Stamp scope in the store, print it on the
run, and record which data, which mode and which calibration produced any number.

**When a check surprises you, confirm it against the filesystem before acting.** This bit twice on
8 August, both times mine. A hash comparison "proved" the deck imagery had not come from the library,
when the renderer re-encodes on insert so the bytes can never match. A doubt about a headline
accuracy figure turned out to be wrong once the source line was read.

**Rotate secrets last, and verify with a real call.** A shape check passes on a placeholder. Confirm
with an authenticated request, keep the old credential alive until the new one has done real work,
and revoke rather than merely misplace.

**Never put a placeholder in a command.** `<new key>` and `<devpc>` were both pasted literally, and
one of them set an environment variable to the string `<new key>`. Give a real value, or a command
that derives it.

---

## 7. Two questions to ask of any tool, not just of its code

**Does the published accuracy describe the thing the client is shown?** Meridian displays a track
record produced by a separate capacity-anchored model with its own artifacts in another folder, while
forecasting with a different method. Both are real and both are documented; nothing in the
application imports the model that produced the claim. Ask it of Atlas before the OGF is sold, and
ask it early, because the answer may be a conversation rather than a change.

**What was every adjustment fitted against?** Meridian's adjustments were all calibrated with one
feed mechanism switched off. So the earlier finding that the better mechanism "did not beat" the
shipped one was measured against a calibration that assumed its absence. That is an untested
mechanism, not a failed one, and it changes what a back-test result means. Before spending hours on a
run, ask what would have to be recalibrated for the result to be readable.

**And run the cheap diagnostic before the expensive one.** The measurement rarely depends on the
implementation. Meridian had a purpose-built pre-test whose first line was "run BEFORE any wiring or
6-8h back-test", answering in minutes whether a mechanism discriminates at all.

---

## 8. What to leave behind

A session that moves a tool ends with: the repo pushed with its history and tags, a clone that runs,
a capability audit committed as the first document, an attic with a reason per file, the switch
register with an owner and a test against each entry, and the register updated with anything that
turned out to be different from what this note says.

Update this note when a tool teaches something new. A superseded document says so at the top or is
deleted, because the next reader finds whichever file the search returns first.

---

Avia Solutions Limited. All rights reserved.
