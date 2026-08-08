"""ddfs_zagreb_oracle.py - THE ZAGREB ORACLE, first pass (19 July 2026).
Regenerates the sent ZAG Secondary Forecast (18 June 2026) from Jess's pack
inputs plus the 2025 OAG sample weeks, and diffs all 995 pinned target rows
in Model_refs/ddfs_bridge_fixtures/zagreb_oracle_targets.tsv.
Conventions register: see the Conventions sheet of the diff workbook and
note 35; candidates marked HER DEFINITION TO CONFIRM are open with Jess.
Selftest: python3 ddfs_zagreb_oracle.py --selftest   (5 pins from the
first-pass run; any change to conventions moves a pin deliberately).
Full run + diff: python3 ddfs_zagreb_oracle.py --run
Author: Avia Solutions.
"""
"""Zagreb oracle stage 1: extract the two 2025 wc sample weeks from the OAG store,
expand days_of_op to per-dow events at ZAG. Conventions recorded in comments.
Author: Avia Solutions."""
import duckdb, json, re

from ddfs_oag_expand import _store_path
OAG = _store_path("oag.duckdb")
# Schengen membership as at the sent deliverable (18 June 2026): EU Schengen + EFTA
# + BG/RO (air borders from 31 Mar 2024). HR domestic counts in the Schengen split
# (Jess's model rows group "Schengen and domestic"). IE, GB, CY non-Schengen.
SCHENGEN = set("AT BE BG CH CZ DE DK EE ES FI FR GR HR HU IS IT LI LT LU LV MT NL NO PL PT RO SE SI SK".split())
from ddfs_aircraft import ICAO  # one owner: ddfs_aircraft.py

def week_events(week_tag):
    con = duckdb.connect(OAG, read_only=True)
    rows = con.execute("""
      select carrier, carrier_category, flight_no, dep_airport, arr_airport,
             dep_country, arr_country, local_dep_time, local_arr_time,
             days_of_op, seats, aircraft_code, local_arr_day
      from oag where (dep_airport='ZAG' or arr_airport='ZAG') and year=2025
        and source_file like ?
        and service_type='J'""", [f"%{week_tag}%"]).fetchall()
    con.close()
    ev = []
    for (cx, cat, fn, dep, arr, dc, ac, dt_, at_, dow, seats, actype, arrday) in rows:
        is_dep = dep == "ZAG"
        t = dt_ if is_dep else at_
        if not t or not re.match(r"^\d{3,4}$", t.strip()):
            continue
        t = t.strip().zfill(4)
        minute = int(t[:2]) * 60 + int(t[2:])
        other = arr if is_dep else dep
        octry = ac if is_dep else dc
        offset = 0
        if not is_dep and arrday and arrday.strip() in ("1", "+1"):
            offset = 1
        for d in (dow or ""):
            if d.isdigit():
                dow_at_zag = (int(d) - 1 + offset) % 7 + 1
                ev.append(dict(dow=dow_at_zag, minute=minute, ad="D" if is_dep else "A",
                               carrier=cx, cat=cat, fno=fn, od=other, ctry=octry,
                               seats=int(seats or 0), icao=ICAO.get(actype, "C"),
                               actype=actype,
                               schengen=(octry in SCHENGEN)))
    # event-grain dedupe at (ad, od, dow, minute): belt and braces after the
    # operating-row filter; collapses residual same-time duplicates.
    seen, out = set(), []
    for e in ev:
        k = (e["ad"], e["od"], e["dow"], e["minute"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out



"""Zagreb oracle v3: solved allocation + C6v3 + stand ledgers.
 C6v3  lcc_net_path applies to FR (+Wizz from 2026, riding FR profile);
       FZ/PC/EW grow at the mainline residual rate.
 T-solved  Old Terminal = {FR, EW, JU, TK, BA} (fitted 2025, reads as LCC +
       non-aligned point-to-point; OU hub + alliance partners + Gulf at New).
 S1  Stand ledger: fluid (weighted) on-ground level per ICAO code, whole year
     sequential, floor 0; overall peak = max level snapshot composition;
     overnight = max within 22:00-06:00; individual = per-code own max.
 S2  Non-commercial: GA movements from the model, flat profile, class A/B.
Author: Avia Solutions."""
import json, datetime as dt, csv, os
from collections import defaultdict

# v4 refactor (20 July 2026, note 37 v2 item 3): pinned constants moved to
# pack-file inputs. The pack is ddfs_packs/ZAG_secondary_2025.json (values
# extracted from this module's own first-pass constants, provenance per field);
# the regression pin is zagreb_oracle_run_v02.tsv reproduced exactly.
_PACK_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "ddfs_packs", "ZAG_secondary_2025.json")

def load_pack(path=None):
    with open(path or _PACK_DEFAULT) as f:
        return json.load(f)

def apply_pack(p):
    """Bind the module conventions from a pack. Every value the first pass
    pinned as a constant now arrives from the pack file."""
    global SPOTS, DEP_SCHENGEN, DEP_NONSCH, DEP_TRANSFER, SCHED_MOV, GA_MOV
    global LCC_PAX_2WAY, UPGAUGE_PA, MONTH_SHARE, SUMMER, OLD_SET, RAMP, LF, OVN, GA25
    yv = lambda d: {int(k): v for k, v in d["values"].items()}
    s, b = p["series"], p["dd_block"]
    SPOTS = list(p["spot_years"])
    DEP_SCHENGEN = yv(s["dep_pax_schengen"])
    DEP_NONSCH = yv(s["dep_pax_nonschengen"])
    DEP_TRANSFER = yv(s["dep_pax_transfer"])
    SCHED_MOV = yv(s["scheduled_movements"])
    GA_MOV = yv(s["ga_movements"])
    LCC_PAX_2WAY = yv(s["lcc_pax_2way"])
    UPGAUGE_PA = b["upgauge_pa"]["value"]
    MONTH_SHARE = {int(k): v for k, v in b["month_share"]["values"].items()}
    SUMMER = set(b["summer_months"])
    OLD_SET = set(b["terminal_old_carriers"]["value"])
    RAMP = set(b["lcc_ramp_carriers"]["value"])
    LF = b["pax_load_factor"]["value"]
    OVN = tuple(b["overnight_window"]["value"])
    GA25 = b["ga_stands_base"]["values"]

apply_pack(load_pack())
BASE = os.environ.get("DDFS_ORACLE_OUT", ".")


def _outdir():
    """Where a run writes. Never the fixtures directory.

    Until 8 August 2026 a run defaulted to
    ddfs_bridge_fixtures/zagreb_oracle_run.tsv, sitting beside
    zagreb_oracle_run_v02.tsv, which is the pin the regression compares
    against. The two files were byte-identical, so a run wrote a result into
    the directory holding the check on that result. On Meridian the same shape
    released a watcher early on a stale file. Fixtures hold pins; runs go to
    runs/, which is gitignored, or to DDFS_ORACLE_OUT.
    """
    d = os.environ.get("DDFS_ORACLE_OUT")
    if not d:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
    os.makedirs(d, exist_ok=True)
    return d
DAYS = [31,28,31,30,31,30,31,31,30,31,30,31]

def load_weeks():
    """Extract the two 2025 wc sample weeks live from the OAG store."""
    return week_events("wc 26May25"), week_events("wc 27Oct25")

def month_factors(ws, ww):
    raw = {}
    for m in range(1, 13):
        wk = ws if m in SUMMER else ww
        raw[m] = sum(e["seats"] for e in wk) / 7.0 * DAYS[m-1]
    tot = sum(raw.values())
    return {m: MONTH_SHARE[m] / (raw[m] / tot) for m in raw}

def group_mults(ws, ww, year, fm):
    upg = (1 + UPGAUGE_PA) ** (year - 2025)
    ramp_mult = (LCC_PAX_2WAY[year] / LCC_PAX_2WAY[2025]) / upg
    r25 = o25 = 0.0
    for m in range(1, 13):
        wk = ws if m in SUMMER else ww
        r = sum(fm[m] for e in wk if e["carrier"] in RAMP)
        o = sum(fm[m] for e in wk if e["carrier"] not in RAMP)
        r25 += r / 7.0 * DAYS[m-1]; o25 += o / 7.0 * DAYS[m-1]
    tot_target = (r25 + o25) * SCHED_MOV[year] / SCHED_MOV[2025]
    other_mult = (tot_target - r25 * ramp_mult) / o25
    return ramp_mult, other_mult

def year_events(year, ws, ww, fm):
    upg = (1 + UPGAUGE_PA) ** (year - 2025)
    rm, om = group_mults(ws, ww, year, fm)
    ev = []
    d = dt.date(year, 1, 1)
    while d.year == year:
        wk = ws if d.month in SUMMER else ww
        dow = d.isoweekday()
        f = fm[d.month]
        for e in wk:
            if e["dow"] != dow: continue
            w = f * (rm if e["carrier"] in RAMP else om)
            ev.append((d, e["minute"], e["ad"], e["schengen"], e["carrier"] in OLD_SET,
                       e["carrier"], e["seats"] * upg, w, e["icao"]))
        d += dt.timedelta(days=1)
    return ev

def hourly(ev, pred, value="pax"):
    h = defaultdict(float)
    for e in ev:
        if not pred(e): continue
        (d, mi, ad, sch, old, cx, s, w, ic) = e
        h[(d, mi // 60)] += s * w * LF if value == "pax" else w
    return h

def nth(h, n=30):
    v = sorted(h.values(), reverse=True)
    return v[n-1] if len(v) >= n else (v[-1] if v else 0.0)

def stand_ledger_weeks(ws, ww, fm, year, pred_raw, dep_buffer_min=0, harmonise=False):
    """Cyclic weekly steady-state AOG per ICAO code (S1v2).
    Per month: the season week runs twice in a closed loop (second pass read),
    weights = fm[month] x group mult, so weekly A/D imbalances cannot drift.
    Departures may carry a buffer (Stand Scenario candidate).
    Returns (overall snapshot, overnight snapshot, individual per-code)."""
    codes = ["A", "B", "C", "D", "E"]
    upg_rm_om = group_mults(ws, ww, year, fm)
    rm, om = upg_rm_om
    best_tot = best_ovn = -1.0
    snap_tot = snap_ovn = {c: 0.0 for c in codes}
    indiv = {c: 0.0 for c in codes}
    for m in range(1, 13):
        wk = ws if m in SUMMER else ww
        f = fm[m]
        # minute-grain deltas over the 7x1440 cyclic week
        delta = defaultdict(lambda: dict((c, 0.0) for c in codes))
        # weekly closure (S1v3): per class, scale arrivals to equal departures;
        # sample-week A/D imbalance is an artefact, real rotations close.
        arrsum = dict((c, 0.0) for c in codes); depsum = dict((c, 0.0) for c in codes)
        sel = [e for e in wk if pred_raw(e)]
        for e in sel:
            w = f * (rm if e["carrier"] in RAMP else om)
            (arrsum if e["ad"] == "A" else depsum)[e["icao"]] += w
        bal = {c: (depsum[c] / arrsum[c] if arrsum[c] else 1.0) for c in codes}
        for e in sel:
            w = f * (rm if e["carrier"] in RAMP else om)
            t = (e["dow"] - 1) * 1440 + e["minute"]
            if e["ad"] == "D":
                t = (t + dep_buffer_min) % 10080
                delta[t][e["icao"]] -= w
            else:
                delta[t][e["icao"]] += w * bal[e["icao"]]
    # closed-loop start level: cumulative min trick per code
        times = sorted(delta)
        level = {c: 0.0 for c in codes}
        run_min = {c: 0.0 for c in codes}
        for t in times:
            for c in codes:
                level[c] += delta[t][c]
                run_min[c] = min(run_min[c], level[c])
        start = {c: -run_min[c] for c in codes}   # smallest start with no negative dip
        # second pass with proper start, read peaks
        level = dict(start)
        for t in times:
            for c in codes:
                level[c] += delta[t][c]
            if harmonise:
                # SS2 (confirmed vs the sent Stand Scenario, 19 July 2026):
                # code-C harmonisation - B on C stands 1:1, E across two C
                # stands (MARS); A and D keep their own codes. Individual
                # peaks stay per raw code except C (harmonised ledger max).
                snap = {"A": level["A"], "B": 0.0,
                        "C": level["C"] + level["B"] + 2 * level["E"],
                        "D": level["D"], "E": 0.0}
            else:
                snap = dict(level)
            tot = sum(snap.values())
            hour = (t % 1440) // 60
            if tot > best_tot:
                best_tot, snap_tot = tot, dict(snap)
            if (hour >= OVN[0] or hour < OVN[1]) and tot > best_ovn:
                best_ovn, snap_ovn = tot, dict(snap)
            for c in codes:
                v = snap["C"] if (harmonise and c == "C") else level[c]
                indiv[c] = max(indiv[c], v)
    return snap_tot, snap_ovn, indiv

def run():
    ws, ww = load_weeks()
    fm = month_factors(ws, ww)
    res = []
    xshare = None
    for year in SPOTS:
        ev = year_events(year, ws, ww, fm)
        for term, tsel in (("Old Terminal", lambda e: e[4]), ("New Terminal", lambda e: not e[4]), ("Overall", lambda e: True)):
            for dn, dp in (("2-way", lambda e: True), ("Arrivals", lambda e: e[2] == "A"), ("Departures", lambda e: e[2] == "D")):
                for sn, sp in (("Schengen", lambda e: e[3]), ("Non-Schengen", lambda e: not e[3]), ("Total", lambda e: True)):
                    h = hourly(ev, lambda e: tsel(e) and dp(e) and sp(e))
                    res.append(("Base", f"30th BHRs - {term}", "", dn, sn, year, nth(h)))
        ou2w = sum(s * w * LF for (d, mi, ad, sch, o, cx, s, w, ic) in ev if cx == "OU")
        if xshare is None: xshare = DEP_TRANSFER[2025] / ou2w
        res.append(("Base", "30th BHRs - Overall", "", "Transfers", "", year, nth(hourly(ev, lambda e: e[5] == "OU")) * xshare))
        res.append(("Base", "Peak Runway Movements", "", "Overall peak", "", year, nth(hourly(ev, lambda e: True, "mov"))))
        # stands: commercial blocks per terminal rule; GA flat as class A/B at model volume
        blocks = [("Stands - by Stand Code - Old Terminal - Commercial", lambda e: e["carrier"] in OLD_SET),
                  ("Stands - by Stand Code - New Terminal - Commercial", lambda e: e["carrier"] not in OLD_SET),
                  ("Stands - by Stand Code - Commercial", lambda e: True)]
        for sheet, harm in (("Base", False), ("Stand Scenario", True)):
            for name, pred in blocks:
                st, so, si = stand_ledger_weeks(ws, ww, fm, year, pred, harmonise=harm)
                for meas, snap in (("Overall peak", st), ("Overnight Peak", so)):
                    for c in "ABCDE":
                        res.append((sheet, name, meas, c, "", year, snap[c]))
                    res.append((sheet, name, meas, "Total", "", year, sum(snap.values())))
                for c in "ABCDE":
                    res.append((sheet, name, "Individual Peak", c, "", year, si[c]))
            # Non Commercial: flagged, value None (GA stand demand is an input
            # assumption in the sent deliverable, not derivable from schedules)
            for meas in ("Overall peak", "Overnight Peak", "Individual Peak"):
                rows_nc = "ABCDE" if meas == "Individual Peak" else "ABCDE"
                for c in rows_nc:
                    res.append((sheet, "Stands - by Stand Code - Non Commercial", meas, c, "", year, None))
                if meas != "Individual Peak":
                    res.append((sheet, "Stands - by Stand Code - Non Commercial", meas, "Total", "", year, None))
            # Overall = commercial + GA assumption (her 2025 NC block grown by
            # GA path, stated; the block itself now arrives from the pack)
            gag = GA_MOV[year] / GA_MOV[SPOTS[0]]
            stO, soO, siO = stand_ledger_weeks(ws, ww, fm, year, lambda e: True, harmonise=harm)
            for meas, snap in (("Overall peak", stO), ("Overnight Peak", soO)):
                tot = 0.0
                for c in "ABCDE":
                    v = snap[c] + GA25[meas][c] * gag
                    tot += v
                    res.append((sheet, "Stands - by Stand Code - Overall", meas, c, "", year, v))
                res.append((sheet, "Stands - by Stand Code - Overall", meas, "Total", "", year, tot))
            for c in "ABCDE":
                res.append((sheet, "Stands - by Stand Code - Overall", "Individual Peak", c, "", year, siO[c] + GA25["Individual Peak"][c] * gag))
        print("year", year, "done")
    return res


def run_lines(res):
    """Canonical TSV lines for a run result (FLAG wording pinned by the
    v02 fixture: GA stand demand is an input, not schedule-derivable)."""
    lines = ["sheet\tsection\tmeasure\trow\tsplit\tyear\tvalue"]
    for r in res:
        lines.append("\t".join(str(x) for x in r[:6])
                     + ("\tFLAG: GA input" if r[6] is None else f"\t{r[6]:.1f}"))
    return lines


def run_to(path):
    with open(path, "w") as f:
        f.write("\n".join(run_lines(run())) + "\n")
    print("written", path)


FIXTURES = None  # resolved at runtime relative to this file

def _fixdir():
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddfs_bridge_fixtures")

def selftest():
    ws, ww = load_weeks()
    checks = []
    checks.append(("summer events", len(ws), 888))
    checks.append(("summer deps", sum(1 for e in ws if e["ad"] == "D"), 450))
    checks.append(("summer dep seats", sum(e["seats"] for e in ws if e["ad"] == "D"), 64472))
    fm = month_factors(ws, ww)
    ev = year_events(2025, ws, ww, fm)
    v = nth(hourly(ev, lambda e: True))
    checks.append(("2025 overall 2-way 30th BHR (pin)", round(v), 2153))
    r = nth(hourly(ev, lambda e: True, "mov"))
    checks.append(("2025 runway 30th hour (pin)", round(r, 1), 19.3))
    fails = [c for c in checks if c[1] != c[2]]
    for c in checks:
        print(("ok  " if c[1] == c[2] else "FAIL"), c[0], c[1], "expected", c[2])
    print(f"zagreb oracle selftest: {len(checks)} checks, " + ("all pass" if not fails else f"{len(fails)} FAILURES"))
    return not fails


def regression():
    """The refactor's own oracle (note 37 v2 item 3): the full run from the
    extracted pack must reproduce zagreb_oracle_run_v02.tsv exactly."""
    import os
    pin = os.path.join(_fixdir(), "zagreb_oracle_run_v02.tsv")
    want = open(pin).read().rstrip("\n").split("\n")
    got = run_lines(run())
    if got == want:
        print(f"pack regression: {len(got)} lines reproduce zagreb_oracle_run_v02.tsv exactly, Ok")
        return True
    bad = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
    print(f"pack regression: FAIL, {bad} lines differ from zagreb_oracle_run_v02.tsv")
    for a, b in zip(got, want):
        if a != b:
            print("  got ", a[:120]); print("  want", b[:120]); break
    return False


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if "--regression" in sys.argv:
        sys.exit(0 if regression() else 1)
    if "--run" in sys.argv:
        i = sys.argv.index("--run")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else "zagreb_oracle_run.tsv"
        run_to(out)
    res = run()
    out = os.path.join(_outdir(), "zagreb_oracle_run.tsv")
    with open(out, "w") as f:
        f.write("sheet\tsection\tmeasure\trow\tsplit\tyear\tvalue\n")
        for r in res:
            f.write("\t".join(str(x) for x in r[:6]) + ("\tFLAG: GA input\n" if r[6] is None else f"\t{r[6]:.1f}\n"))
    print("written", out)
