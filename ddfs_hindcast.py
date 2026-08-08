"""ddfs_hindcast.py - FORECAST FROM PACK + THE ADAC 2024 HINDCAST
(20 July 2026, note 37 v2 items 4 and 5, John's own acceptance test).

forecast_from_pack(pack): the DDFS side of the chain. Takes an emitted
airport-scenario pack (ddfs_pack_emit), builds the schedule base from the
OAG store at the pack's base year (sample mode: busiest day of the summer
sample week, the ladder rung 2 convention, proxy stated; full mode: the
method module's own SBR30 pick, upgrading automatically when full-year
coverage lands because coverage is read live), and scales the design day
to each spot year by the pack's scheduled-movements path.

adac_hindcast(): recreate a 2024 ADAC forecast from the engine through the
pack and diff the emerging DDFS against the sent deliverable's 692 pinned
rows (adac2024_oracle_targets.tsv) in the ladder's scoreboard format.
Resemblance is a scoreboard, not a judgement: the sent case carries
client-plan carrier growth (EY, 3L, 5W ramps) the engine profile does not.

Run: python3 ddfs_hindcast.py            (the acceptance run)
     python3 ddfs_hindcast.py --selftest (pins)
Author: Avia Solutions.
"""
import os, csv, sys, datetime as dt
from collections import defaultdict

import ddfs_pack_emit as pe

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddfs_bridge_fixtures")


def _score(pairs, label):
    """The ladder's scoreboard line (ddfs_ladder.score conventions)."""
    es = [(abs(g - t) / abs(t) if t else abs(g - t), abs(g - t)) for t, g in pairs]
    mape = sum(e[0] for e in es) / len(es) * 100
    mab = sum(e[1] for e in es) / len(es)
    w25 = sum(1 for e in es if e[0] <= 0.25) * 100 // len(es)
    print(f"  {label:52s} n {len(es):4d}  MAPE {mape:6.1f}%  meanAbs {mab:8.2f}  within25% {w25}%")
    return mape, mab


def base_day(pack):
    """The schedule-base design day for the pack's base year.
    Coverage read live: full-year files -> SBR30 pick; else sample mode."""
    ap, year = pack["airport"], pack["base_year"]
    full, weeks = pe._store_coverage(ap, year)
    if full:
        import ddfs_oag_expand as ox, ddfs_method_module as mm, ddfs_service as svc
        ev = ox.load_oag(ap, year)
        s30 = mm.sbr(mm.hourly_series(ox.to_module_events(ev), basis="atm"), 30)
        date = s30["date"]
        date = dt.date.fromisoformat(date) if isinstance(date, str) else date
        de = svc.day_events(ap, date)
        hourly = defaultdict(lambda: [0, 0])
        for e in de:
            hourly[e["minute"] // 60][0 if e["ad"] == "A" else 1] += 1
        return {"mode": "full (SBR30 day)", "date": str(date), "hourly": dict(hourly)}
    # sample mode: the summer wc week, busiest day by events (rung 2 convention)
    summer = [s for (s, _n) in weeks if "May" in s] or [s for (s, _n) in weeks]
    if not summer:
        return {"mode": "FLAG: no schedule base held", "hourly": None}
    wk = summer[0][summer[0].index("wc "):].replace(".xlsx", "")
    ev = pe._week_day_events(ap, year, f"%{wk}%")
    by_day = defaultdict(list)
    for e in ev:
        by_day[e["dow"]].append(e)
    dd = max(by_day, key=lambda d: len(by_day[d]))
    hourly = defaultdict(lambda: [0, 0])
    for e in by_day[dd]:
        hourly[e["minute"] // 60][0 if e["ad"] == "A" else 1] += 1
    return {"mode": f"sample ({wk}, busiest day dow={dd}; PMAD proxy stated)",
            "week": wk, "dow": dd, "hourly": dict(hourly)}


def forecast_from_pack(pack):
    mov = pack["series"]["scheduled_movements"]["values"]
    pax = pack["series"]["pax_total"]["values"]
    if not mov:
        return {"error": "pack carries no movements path (flagged); DDFS needs it"}
    bd = base_day(pack)
    if not bd.get("hourly"):
        return {"error": bd["mode"]}
    base = str(pack["base_year"])
    day_total = sum(a + d for (a, d) in bd["hourly"].values())
    years = {}
    for y in pack["spot_years"]:
        ys = str(y)
        f = mov[ys] / mov[base]
        hourly = {h: [bd["hourly"].get(h, [0, 0])[0] * f,
                      bd["hourly"].get(h, [0, 0])[1] * f] for h in range(24)}
        years[ys] = {
            "growth_factor": round(f, 4),
            "hourly": {f"{h:02d}": [round(v[0], 1), round(v[1], 1)] for h, v in hourly.items()},
            "day_atms": round(day_total * f, 1),
            "kpis": {
                "pax_m": round(pax[ys] / 1e6, 1),
                "atm_k": round(mov[ys] / 1e3, 1),
                "avg_atm_day": round(mov[ys] / 365.25),
                "pax_per_atm": round(pax[ys] / mov[ys]),
                "design_day_atms": round(day_total * f),
            }}
    from ddfs_towerlog import OAG_STATEMENT
    return {"airport": pack["airport"], "base_year": pack["base_year"],
            "base_day": {k: v for k, v in bd.items() if k != "hourly"},
            "base_day_atms": day_total, "years": years,
            "base_statement": OAG_STATEMENT,
            "flags": pack["flags"],
            "note": "Design day scaled uniformly by the movements path; per-carrier "
                    "reshaping needs carrier paths the pack does not carry (flagged)."}


ADAC_SPOTS = [2019, 2024, 2028, 2032, 2038, 2040, 2044]


def adac_hindcast(verbose=True):
    pack = pe.emit_pack("AUH", "Baseline", base_year=2024, spot_years=ADAC_SPOTS)
    fc = forecast_from_pack(pack)
    tgt = {}
    n_rows = 0
    with open(os.path.join(FIX, "adac2024_oracle_targets.tsv")) as f:
        for r in csv.DictReader((l for l in f if not l.startswith("#")), delimiter="\t"):
            n_rows += 1
            v = r["value"].replace(",", "").replace("%", "")
            try:
                x = float(v)
            except ValueError:
                continue
            tgt[(r["sheet"], r["section"], r["measure"], r["row"], r["split"], r["year"])] = x
    if verbose:
        print(f"ADAC 2024 HINDCAST - engine -> pack -> DDFS vs the sent deliverable ({n_rows} pinned rows)")
        print(f"  base day: {fc['base_day']['mode']}, {fc['base_day_atms']} ATMs "
              f"(sent 2024 day: A 225 / D 219 = 444)")
    fams = {"hourly": [], "day_totals": [], "kpi": []}
    excluded = defaultdict(int)
    for k, t in tgt.items():
        (sheet, sect, meas, row, split, year) = k
        if sect == "Hourly ATMs":
            if split not in ("A", "D"):
                excluded["benchmark columns (Motts 2040, 2023 DDFS) - comparator inputs, not targets"] += 1
                continue
            if year == "2019":
                excluded["2019 columns - empty in the sent workbook"] += 1
                continue
            if year not in fc["years"]:
                continue
            if row == "Max":
                excluded["rolling-hour Max rows - need event-grain retiming, not clock-hour scaling"] += 1
                continue
            got = fc["years"][year]["hourly"].get(row.zfill(2), [0, 0])[0 if split == "A" else 1] if row != "Total" else None
            if row == "Total":
                got = sum(v[0 if split == "A" else 1] for v in fc["years"][year]["hourly"].values())
                fams["day_totals"].append((abs(t), got))
            else:
                fams["hourly"].append((abs(t), got))
        elif sheet == "Overview - Base" and row == "Total":
            if year not in fc["years"]:
                continue
            kp = fc["years"][year]["kpis"]
            m = {"Commercial Pax fcst (m)": "pax_m", "Commercial ATM fcst (k)": "atm_k",
                 "Average ATM per day": "avg_atm_day", "Pax / ATM": "pax_per_atm",
                 "Design day": "design_day_atms"}.get(sect)
            if m:
                fams["kpi"].append((t, kp[m]))
            else:
                excluded[f"KPI '{sect}' - not regenerated (derivative or needs actuals)"] += 1
        else:
            excluded["per-airline / region rows - pack carries no carrier paths (flagged, not filled)"] += 1
    if verbose:
        _score(fams["hourly"], "hourly ATMs A/D, forecast years vs sent columns")
        for y in [str(s) for s in ADAC_SPOTS if s != 2019]:
            yp = []
            for k, t in tgt.items():
                if (k[1] == "Hourly ATMs" and k[4] in ("A", "D") and k[5] == y
                        and k[3] not in ("Total", "Max") and y in fc["years"]):
                    yp.append((abs(t), fc["years"][y]["hourly"].get(k[3].zfill(2), [0, 0])[0 if k[4] == "A" else 1]))
            if yp:
                _score(yp, f"    of which {y} (growth factor {fc['years'][y]['growth_factor']})")
        _score(fams["day_totals"], "design-day A/D totals per year")
        _score(fams["kpi"], "KPI block Total rows (pax, ATMs, pax/ATM, day)")
        for reason, n in sorted(excluded.items()):
            print(f"  not valued ({n:3d} rows): {reason}")
        print(f"  the divergence is the growth profile: sent 2044 pax 69.7m (client-plan carrier ramps)")
        print(f"  vs engine Baseline 44.4m; the scoreboard states it, per the spec resemblance != judgement")
    return {"pack": pack["pack_id"], "families": {k: len(v) for k, v in fams.items()},
            "excluded": dict(excluded), "fc": fc}


def selftest():
    checks = []
    pack = pe.emit_pack("AUH", "Baseline", base_year=2024, spot_years=ADAC_SPOTS)
    fc = forecast_from_pack(pack)
    checks.append(("base day mode is sample (pre store day)", fc["base_day"]["mode"].startswith("sample"), True))
    checks.append(("base day ATMs (rung 2 pin)", fc["base_day_atms"], 441))
    checks.append(("2024 growth factor is unity", fc["years"]["2024"]["growth_factor"], 1.0))
    checks.append(("spot years carried", len(fc["years"]), 7))
    r = adac_hindcast(verbose=False)
    checks.append(("hourly family valued", r["families"]["hourly"] > 200, True))
    checks.append(("kpi family valued", r["families"]["kpi"], 25))
    fails = [c for c in checks if c[1] != c[2]]
    for c in checks:
        print(("ok  " if c[1] == c[2] else "FAIL"), c[0], c[1], "expected", c[2])
    print(f"hindcast selftest: {len(checks)} checks, "
          + ("all pass" if not fails else f"{len(fails)} FAILURES"))
    return not fails


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    adac_hindcast()
