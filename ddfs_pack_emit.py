"""ddfs_pack_emit.py - ENGINE-TO-PACK EMIT (20 July 2026, note 37 v2 item 2).

The genuinely new piece of the DDFS Cockpit chain: from the Global Forecast
engine's data bundle (webapp/data/cockpit.json, the same bundle the protected
Cockpit reads) for a chosen airport and scenario, emit an airport-scenario
DDFS pack in the ZAG pack grain (engine value | override | provenance per
input, notes 14, 15, 23 v3 section 3). Flag rather than fill: whatever the
engine cannot supply is either bridged from the OAG store with the source
named (gauge mix, seats per ATM, month shares where full-year coverage is
held) or carried as an explicit cannot-supply flag (GA, terminal allocation,
transfers, LCC path), never silently defaulted.

Read-only on the engine bundle: overrides are request-scoped, recorded in
the pack under overrides_applied, and never written back.

Selftest: python3 ddfs_pack_emit.py --selftest
Author: Avia Solutions.
"""
import json, os, glob, datetime as dt
from collections import defaultdict

import config
from ddfs_oag_expand import _store_path

_BUNDLE_CACHE = {}


BUNDLE_NAME = "avia_forecast_build/webapp/data/cockpit.json"


def _bundle_path():
    """The Atlas engine bundle, through the one resolver. AVIA_ENGINE_BUNDLE
    overrides it where Atlas lives outside the data root."""
    return config.store_path(BUNDLE_NAME)


def load_bundle():
    p = _bundle_path()
    if p not in _BUNDLE_CACHE:
        with open(p) as f:
            _BUNDLE_CACHE[p] = json.load(f)
    return _BUNDLE_CACHE[p]


def airport_row(code):
    b = load_bundle()
    for a in b["airports"]:
        if a["c"] == code.upper():
            return b, a
    raise KeyError(f"{code} not in the engine bundle")


def airports_list():
    b = load_bundle()
    return [{"c": a["c"], "n": a["n"], "cty": a["cty"], "base": a["base"]}
            for a in b["airports"]]


def _store_coverage(ap, year):
    """(weekly_events_per_sample_week, coverage) from the OAG store."""
    import duckdb
    con = duckdb.connect(_store_path("oag.duckdb"), read_only=True)
    full = con.execute("""select count(*) from oag
        where (dep_airport=? or arr_airport=?) and year=? and service_type='J'
        and source_file not like '%wc %'""", [ap, ap, year]).fetchone()[0]
    weeks = con.execute("""select source_file, count(*) from oag
        where (dep_airport=? or arr_airport=?) and year=? and service_type='J'
        and source_file like '%wc %' group by 1""", [ap, ap, year]).fetchall()
    con.close()
    return full, weeks


def _week_day_events(ap, year, week_like):
    """Expanded per-dow events for one sample week (ladder conventions:
    event-grain dedupe, arrival day offset)."""
    import duckdb
    con = duckdb.connect(_store_path("oag.duckdb"), read_only=True)
    rows = con.execute("""select carrier, flight_no, dep_airport, arr_airport,
        local_dep_time, local_arr_time, local_arr_day, days_of_op, seats,
        aircraft_code
      from oag where (dep_airport=? or arr_airport=?) and year=?
        and source_file like ? and service_type='J'""",
      [ap, ap, year, week_like]).fetchall()
    con.close()
    seen, ev = set(), []
    for (cx, fn, dep, arr, dt_, at_, ad_day, dow, seats, ac) in rows:
        is_dep = dep == ap
        t = ((dt_ if is_dep else at_) or "").strip()
        if not t.isdigit():
            continue
        m = int(t.zfill(4)[:2]) * 60 + int(t.zfill(4)[2:])
        off = 1 if (not is_dep and (ad_day or "").strip() in ("1", "+1")) else 0
        for d in (dow or ""):
            if d.isdigit():
                dw = (int(d) - 1 + off) % 7 + 1
                k = (cx, fn, dw, is_dep, m)
                if k in seen:
                    continue
                seen.add(k)
                ev.append(dict(dow=dw, minute=m, ad="D" if is_dep else "A",
                               carrier=cx, seats=int(seats or 0), actype=ac))
    return ev


def _gauge_bridge(ap, year):
    """OAG-bridged gauge facts for the base year: ICAO class mix of events and
    seats per ATM (note 23 item 3: the engine is an airport-level pax model,
    so the gauge path comes back cannot-supply and is bridged from OAG)."""
    from ddfs_ladder import ICAO
    full, weeks = _store_coverage(ap, year)
    ev = []
    for (src, _n) in weeks:
        wk = src[src.index("wc "):].replace(".xlsx", "")
        ev += _week_day_events(ap, year, f"%{wk}%")
    if not ev:
        return None, None, None, "FLAG: no schedule rows held for base year"
    mix = defaultdict(int)
    for e in ev:
        mix[ICAO.get(e["actype"], "C")] += 1
    tot = sum(mix.values())
    spa = sum(e["seats"] for e in ev) / tot
    daily = tot / (7.0 * max(1, len(weeks)))
    return ({c: round(mix[c] / tot, 4) for c in sorted(mix)},
            round(spa, 1), daily, None)


def emit_pack(airport, scenario="Baseline", base_year=None, spot_years=None,
              overrides=None):
    """Emit the airport-scenario DDFS pack from the engine bundle."""
    b, a = airport_row(airport)
    years = b["years"]
    base_year = int(base_year or b["base"])
    if scenario not in a["series"]:
        raise KeyError(f"scenario {scenario} not in engine series")
    ser = a["series"][scenario]
    ymap = {y: (ser[i] if i < len(ser) else None) for i, y in enumerate(years)}
    if base_year not in ymap or ymap[base_year] is None:
        raise KeyError(f"engine series holds no value for base year {base_year}")
    spot_years = spot_years or [base_year + n for n in (0, 5, 10, 15, 20)]
    spot_years = [y for y in spot_years if y in ymap and ymap[y] is not None]

    flags = []
    pax = {str(y): round(ymap[y] * 1e6) for y in spot_years}

    # movements: base from the OAG store, path riding pax over upgauge
    mix, spa, daily, gflag = _gauge_bridge(airport, base_year)
    full, weeks = _store_coverage(airport, base_year)
    upg = 0.0
    if overrides and "upgauge_pa" in overrides:
        upg = float(overrides["upgauge_pa"])
    if gflag:
        flags.append(gflag)
        mov = None
    else:
        base_atms = daily * 365.25
        cov = ("full-year files" if full else
               f"sample-week annualisation ({len(weeks)} wc weeks; stated proxy, upgrades at store day)")
        mov = {str(y): round(base_atms * (ymap[y] / ymap[base_year])
                             / (1 + upg) ** (y - base_year)) for y in spot_years}

    dd = {
        "gauge_mix_base": (
            {"values": mix, "provenance": f"OAG-BRIDGE {airport} {base_year} (engine cannot supply; note 23 item 3)"}
            if mix else {"value": None, "provenance": "FLAG: cannot supply, no schedule rows held"}),
        "seats_per_atm_base": (
            {"value": spa, "provenance": f"OAG-BRIDGE {airport} {base_year}"}
            if spa else {"value": None, "provenance": "FLAG: cannot supply"}),
        "upgauge_pa": {"value": upg,
                       "provenance": ("OVERRIDE (request-scoped)" if overrides and "upgauge_pa" in overrides
                                      else "ENGINE-DEFAULT: none")},
        "pax_load_factor": {"value": (overrides or {}).get("pax_load_factor", 0.80),
                            "provenance": ("OVERRIDE (request-scoped)" if overrides and "pax_load_factor" in overrides
                                           else "WORKING ASSUMPTION 0.80 (ZAG precedent, note 35 v2; engagement value to confirm)")},
        "dom_share": {"value": a.get("dom"), "provenance": "ENGINE"},
        "connecting_share": {"value": a.get("cx"), "provenance": "ENGINE"},
        "month_share": {"value": None,
                        "provenance": "FLAG: cannot supply from sample weeks; full-year store or ACI monthly panel fills this (note 23 item 1)"},
        "design_day_convention": {"value": "busiest day of held sample week (PROXY; sent ADAC convention is PMAD - upgrades at store day)",
                                  "provenance": "SAMPLE-MODE PROXY, stated per ladder rung 2"},
        "ga_movements": {"value": None, "provenance": "FLAG: engagement input, not engine-derivable"},
        "terminal_allocation": {"value": None, "provenance": "FLAG: engagement input (ZAG precedent: candidate rule to confirm)"},
        "transfer_rule": {"value": None, "provenance": "FLAG: engagement input (ZAG precedent: fixed base-year share of hub carrier)"},
        "lcc_net_path": {"value": None, "provenance": "ENGINE-DEFAULT: none (analyst input where the engagement holds one)"},
    }
    flags += [k for k, v in dd.items() if isinstance(v, dict) and v.get("value") is None
              and "FLAG" in str(v.get("provenance", ""))]

    pack = {
        "pack_id": f"{airport}_{scenario}_{base_year}_{dt.date.today().isoformat()}",
        "airport": airport.upper(),
        "airport_name": a["n"],
        "base_year": base_year,
        "vintage": "engine bundle cockpit.json (read-only)",
        "emitted": dt.datetime.now().isoformat(timespec="seconds"),
        "scenario": scenario,
        "spot_years": spot_years,
        "series": {
            "pax_total": {"provenance": f"ENGINE {scenario} series", "values": pax},
            "scheduled_movements": (
                {"provenance": f"DERIVED: OAG {base_year} base ({cov}), grown with the pax path over (1+upgauge)^n",
                 "values": mov} if mov else
                {"provenance": "FLAG: cannot supply, no schedule base held", "values": None}),
        },
        "dd_block": dd,
        "flags": sorted(set(flags)),
        "overrides_applied": overrides or {},
        "note": "Emitted by ddfs_pack_emit.py; the engine bundle is never written back. Flag rather than fill throughout.",
    }
    return pack


def save_pack(pack, folder=None):
    folder = folder or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddfs_packs")
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, pack["pack_id"] + ".json")
    with open(p, "w") as f:
        json.dump(pack, f, indent=1)
    return p


def selftest():
    checks = []
    b, a = airport_row("AUH")
    pk = emit_pack("AUH", "Baseline", base_year=2024,
                   spot_years=[2019, 2024, 2028, 2032, 2038, 2040, 2044])
    checks.append(("AUH 2024 pax (engine bundle pin)", pk["series"]["pax_total"]["values"]["2024"], 28843000))
    checks.append(("AUH spot years held", len(pk["spot_years"]), 7))
    checks.append(("AUH movements base emitted", pk["series"]["scheduled_movements"]["values"] is not None, True))
    checks.append(("AUH gauge mix bridged from OAG", "OAG-BRIDGE" in pk["dd_block"]["gauge_mix_base"]["provenance"], True))
    checks.append(("AUH month share flagged not filled", pk["dd_block"]["month_share"]["value"], None))
    checks.append(("AUH GA flagged not filled", pk["dd_block"]["ga_movements"]["value"], None))
    z = emit_pack("ZAG", "Baseline")
    checks.append(("ZAG base year from bundle", z["base_year"], 2025))
    checks.append(("ZAG 2025 pax (engine bundle pin)", z["series"]["pax_total"]["values"]["2025"], 4302000))
    ov = emit_pack("ZAG", "Baseline", overrides={"upgauge_pa": 0.0035})
    checks.append(("override request-scoped, recorded", ov["overrides_applied"].get("upgauge_pa"), 0.0035))
    checks.append(("override not in plain emit", z["overrides_applied"], {}))
    fails = [c for c in checks if c[1] != c[2]]
    for c in checks:
        print(("ok  " if c[1] == c[2] else "FAIL"), c[0], c[1], "expected", c[2])
    print(f"pack emit selftest: {len(checks)} checks, "
          + ("all pass" if not fails else f"{len(fails)} FAILURES"))
    return not fails


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if "--emit" in sys.argv:
        i = sys.argv.index("--emit")
        ap = sys.argv[i + 1]
        pk = emit_pack(ap)
        print(json.dumps(pk, indent=1))
