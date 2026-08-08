# DDFS switch register

Version 1.0 - 8 August 2026 - Avia Solutions

Every capability that is built and not currently reachable, every option that is deliberately
disabled, and every pin that is outstanding. Each entry carries an owner and the named test that
would allow it to be turned on.

A default-off switch is a temporary state with an expiry, not a resting place. An entry with no test
named against it is unfinished work with a lid on, and it is the reason Meridian shipped five
verified improvements switched off. Nothing is added here without a test.

---

## 1. Capability built and not reachable

### `ddfs_bridge.py`, the canonical, CAST, AOG and transfer sheet chain

**State.** The module holds 23 functions. `ddfs_service.py` imports `MIN_TURN` and `MAX_TURN` and
nothing else. `canonical_rows`, `emit_canonical`, `emit_cast`, `aog_ledger`, `emit_aog`,
`emit_transfersheet`, `build_year_tables`, `generate_growth`, `read_tod` and `run_oracle_diff` are
called by nothing in the running tool. Its 24 `canonical_ahb_*`, `cast_ahb_*` and `aog_ahb_*`
fixtures test a chain the live tool does not call.

**Decision, 8 August 2026 (JC).** Keep the module and its fixtures. It is disciplined work missing
its last move, and the outputs are ones clients ask for.

**Test that would allow it on.** `python ddfs_bridge.py --selftest`, which runs all three selftests
(reference day and pairing, AOG, canonical and CAST). Added 8 August 2026; before that the entry
point sat mid-file behind `len(sys.argv) == 3` and `--selftest` did nothing, which is how the module
drifted out of reach. Current state: three selftests, all pass.

**What turning it on means.** Wiring `canonical_rows` and `emit_canonical` into the Outputs stage of
the unified tool, so the canonical and CAST tables come out of the tool rather than out of a module
nobody calls. Own build session, after final testing.

**Owner.** JC.

### `ddfs_report_gen_v02.js`, the superset Design Day report generator

**State.** 18,741 bytes. Referenced by no Python module, no HTML surface and no batch file. The
service serves no JavaScript. The live page contains no report generation. The v0.2 Design Day report
in the 19 July Jess Pack was produced beside the tool, not from it.

**Decision, 8 August 2026 (JC).** Wire it in as a Stage 5 output.

**Test that would allow it on.** A headless check that the Outputs stage produces a report for the
Zagreb pack whose section count and figure count match the v0.2 deliverable, plus a rendered read of
the output. Not yet written: this is the build slot, not a switch to flip.

**Owner.** JC. Next build session.

---

## 2. Options deliberately disabled in the tool

Per note 41, these appear in the unified page as visible, disabled options carrying their ACI item
numbers, rather than vanishing. That is the right treatment and it stays.

| Option | Stage | Blocked on | Test that would allow it on |
|---|---|---|---|
| Per-season design days | 2 and 3 | ACI item 3 | Season-split method table for ZAG 2025 reproduces the annual figure when the seasons are recombined |
| Client-supplied forecast ingest | 4 | ACI item 4 | A client forecast emits a pack of the same grain as the engine, and the Design Day built from it matches the one built from an engine pack with the same growth |
| Annual and bi-annual emit | 2 | ACI item 5 | Annual emit for ZAG reproduces the five-yearly result at the five-yearly spot years |

The ACI items are licence closures, not code. Until they close, disabled and visible is correct.

---

## 3. Pins outstanding

### Hindcast base day in full mode

**State.** The base day upgrades from sample mode to the SBR30 full-year pick on its own as the store
loads. The pin of 441 ATMs was taken in sample mode on the two-week base. AUH 2024 now holds 267,789
full-year rows alongside 12 sample weeks, so the load is mid-flight and the current figure of 414 is
a mid-load figure.

**Deliberately not re-pinned.** Pinning 414 today would bake in a state that is about to change and
would then read as an accepted result. The selftest prints the coverage it saw and states that the
full-mode pin is outstanding.

**Test.** At store day, rerun `python ddfs_hindcast.py --selftest`, record the base day ATMs together
with the coverage figures they were taken against, and pin both. A pin that does not state its store
state is the fault that annualised a two-week snapshot.

**Owner.** JC, at store day.

### Zagreb forecast years served from a pinned file

**State.** `/api/zagreb_forecast` reads `ddfs_bridge_fixtures/zagreb_oracle_run_v02.tsv` and returns
rows from it. It does not call the oracle. This is deliberate and documented in the endpoint's own
docstring: the live answer always matches the pinned increment.

**What it means.** The tool ships a frozen Zagreb answer. A reader who assumes the forecast years are
computed on request will be wrong.

**Test.** `python ddfs_zagreb_oracle.py --regression` reproduces the pinned file byte-exactly, 996
lines, currently passing. That is what makes serving the file legitimate.

**Action.** State on the page that the forecast years come from a pinned oracle run of 19 July 2026,
or make the endpoint call the oracle at store day. One line, or a build slot.

**Owner.** JC.

---

## 4. Fixture questions open

Three fixture pairs are byte-identical across different forecast years: `cast_ahb_2040` equals
`cast_ahb_2045`, `aog_ahb_2040` equals `aog_ahb_2045`, `aog_ahb_2025` equals `aog_ahb_2030`. The
corresponding `canonical_ahb` files do differ between those years.

Either those measures are genuinely flat across the pair, or a fixture was copied and not
regenerated. Until it is established which, neither file should be trusted as a test target for the
year it names, because a test passing against a copied fixture proves nothing about that year.

**Test.** Regenerate each from its inputs and compare. **Owner.** JC.

---

## 5. Control not enforced

`ddfs_service.py` defines `WHITELIST` and the docstring says only whitelisted files are served.
`_file()` never consults it. Nothing is exposed today, because only three literal filenames reach
`_file()` and no user input does, but a stated control that reads as enforced and is not will mislead
whoever adds the next route.

**Test.** A check that requesting a path outside the whitelist returns 404 while the three served
pages return 200. **Owner.** JC. My view is enforce it: the service runs on licensed data behind a
Cloudflare tunnel.

---

Avia Solutions Limited. All rights reserved.
