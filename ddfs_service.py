"""Avia Cortex - DDFS live service. Author: Avia Solutions.

The DDFS equivalent of qsi_service.py: run on the machine that holds the OAG
and Sabre stores, expose through the existing Cloudflare tunnel, and Jess
creates a DDFS off real data from her laptop. Pattern copied from
avia_forecast_build/webapp/qsi_service.py (stdlib only, shared-password
Basic Auth, /api compute endpoints).

Run:   cd C:\\Users\\Carte\\OneDrive\\Avia\\Model_refs
       python ddfs_service.py                (port 8030; PORT env overrides)
Tunnel ingress (config.yml, before the catch-all):
       - hostname: ddfs.aviacortex.com
         service: http://localhost:8030
Access: HTTP Basic Auth, any username + the shared password
        (DDFS_PASSWORD or FORECAST_PASSWORD env, else access_password.txt
        beside this file, else the forecast webapp's access_password.txt).
        With no password found the server runs OPEN with a warning - local
        development only; licensed data must not be exposed unprotected.

Endpoints:
  GET /                     the live page (ddfs_live.html)
  GET /demo                 the v1.7 demonstration front end
  GET /cockpit              THE DDFS COCKPIT (note 37 v2): the full chain,
        engine forecast -> levers -> emit pack -> DDFS, on one page
  GET /api/years?airport=ZAG          years held + coverage (full/sample)
  GET /api/methods?airport=&year=&basis=atm|pax   live method comparison TSV
  GET /api/ddfs?airport=&year=&basis=&date=auto|YYYY-MM-DD
        builds the design day (auto = SBR30 day): hourly A/D, KPIs,
        stand ledger by ICAO class, event schedule TSV
  GET /api/airports         engine bundle airport list (picker)
  GET /api/engine?airport=  engine forecast slice for the cockpit chart
  GET /api/packs            packs held in ddfs_packs/
  POST /api/emit_pack       {airport, scenario, base_year, spot_years,
        overrides} -> the DDFS pack (flag rather than fill; overrides are
        request-scoped and never written back; &save=1 files it to ddfs_packs)
  POST /api/forecast        {pack} or {airport,...} -> DDFS from the pack
        (sample weeks now, SBR30 full mode automatically at store day)
  GET /api/hindcast         the ADAC 2024 acceptance run, scoreboard verbatim
Only whitelisted files are served; Model_refs holds client models that must
never go over the tunnel."""
import http.server, socketserver, os, sys, json, urllib.parse, base64, hmac, threading
import datetime as dt
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
PORT = int(os.environ.get("PORT", "8030"))
REALM = "Avia Cortex DDFS"
WHITELIST = {"ddfs_live.html", "ddfs_front_v1.html", "ddfs_cockpit.html"}

import ddfs_oag_expand as ox
import ddfs_method_module as mm
import ddfs_pack_emit as pe
import ddfs_hindcast as hc
import ddfs_towerlog as tl

from ddfs_aircraft import ICAO  # one owner: ddfs_aircraft.py


def _load_password():
    for env in ("DDFS_PASSWORD", "FORECAST_PASSWORD"):
        pw = (os.environ.get(env) or "").strip()
        if pw:
            return pw
    for p in (os.path.join(ROOT, "access_password.txt"),
              r"C:\Avia\avia_forecast_build\webapp\access_password.txt"):
        try:
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
        except OSError:
            pass
    return ""


PASSWORD = _load_password()
_cache = {}


def store():
    import duckdb
    return duckdb.connect(ox.OAG_DEFAULT, read_only=True)


def api_years(q):
    ap = (q.get("airport") or "").upper()
    con = store()
    rows = con.execute("""select year,
        sum(case when source_file like '%wc %' then 1 else 0 end),
        sum(case when source_file not like '%wc %' then 1 else 0 end)
      from oag where (dep_airport=? or arr_airport=?) and service_type='J'
      group by 1 order by 1""", [ap, ap]).fetchall()
    con.close()
    return {"airport": ap, "years": [
        {"year": y, "coverage": "full" if m else "sample-weeks", "rows": (w or 0) + (m or 0)}
        for (y, w, m) in rows]}


def events_for(ap, year):
    k = (ap, year)
    if k not in _cache:
        _cache[k] = ox.load_oag(ap, year)
        if len(_cache) > 6:
            _cache.pop(next(iter(_cache)))
    return _cache[k]


_wcache = {}


def weighted_for(ap, year):
    """Sabre-weighted module events, cached: the weighting query is the slow
    leg and the duality card needs it on every build."""
    k = (ap, year)
    if k not in _wcache:
        _wcache[k] = ox.weight_events(events_for(ap, year), ap, year)[0]
        if len(_wcache) > 6:
            _wcache.pop(next(iter(_wcache)))
    return _wcache[k]


def api_methods(q):
    ap = (q.get("airport") or "").upper()
    year = int(q.get("year"))
    basis = q.get("basis", "atm")
    ev = events_for(ap, year)
    # weight_events already returns module-shaped events plus meta; converting
    # again through to_module_events was the latent pax-basis fault (20 July)
    mev = weighted_for(ap, year) if basis == "pax" else ox.to_module_events(ev)
    res = mm.method_table(mev, basis=basis, source=f"oag.duckdb live, {ap} {year}")
    import tempfile
    with tempfile.NamedTemporaryFile("r", suffix=".tsv", delete=False) as tf:
        pass
    mm.emit_table(res, tf.name)
    tsv = open(tf.name).read().rstrip("\n")
    os.unlink(tf.name)
    return {"tsv": tsv, "airport": ap, "year": year, "basis": basis,
            "sbr30": res["sbr30"], "annual_total": res["annual_total"]}


def day_events(ap, date):
    """Full event list for one calendar date with aircraft class (store query
    at date grain, monthly-file authority, event-grain dedupe)."""
    con = store()
    rows = con.execute("""select carrier, flight_no, dep_airport, arr_airport,
        local_dep_time, local_arr_time, local_arr_day, days_of_op, seats,
        aircraft_code, cast(eff_from as date), cast(eff_to as date), source_file
      from oag where (dep_airport=? or arr_airport=?) and year=?
        and service_type='J' and source_file not like '%wc %'""",
      [ap, ap, date.year]).fetchall()
    con.close()
    monthly_first = sorted(rows, key=lambda r: 0 if ox._file_month(r[12]) else 1)
    seen, out = set(), []
    for (cx, fn, dep, arr, dtm, atm_, ad_day, dow, seats, ac, f, t, src) in monthly_first:
        is_dep = dep == ap
        tt = (dtm if is_dep else atm_) or ""
        tt = tt.strip()
        if not tt.isdigit():
            continue
        ev_date = date
        base_date = date - dt.timedelta(days=1) if (not is_dep and (ad_day or "").strip() in ("1", "+1")) else date
        if not (f and t and f <= base_date <= t):
            continue
        if not (dow or "")[base_date.isoweekday() - 1: base_date.isoweekday()].strip():
            continue
        fm = ox._file_month(src)
        if fm and fm != base_date.month:
            continue
        m = int(tt.zfill(4)[:2]) * 60 + int(tt.zfill(4)[2:])
        key = (cx, fn, "D" if is_dep else "A", m)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(carrier=cx, fno=fn, ad="D" if is_dep else "A", minute=m,
                        od=(arr if is_dep else dep), seats=int(seats or 0),
                        icao=ICAO.get(ac, "C"), actype=ac))
    return sorted(out, key=lambda e: e["minute"])


def day_occupancy(de):
    """STAND OCCUPANCY behind the Max AOG headline (JC, 20 July: the
    masterplan buyer wants turnarounds, overnight parking and towing, not
    just the maximum concurrent). Day-grain rotation pairing per the bridge's
    Part A conventions (ddfs_bridge.pair_events): greedy within the class
    turn band, flight-number adjacency first, same carrier and class; then a
    second pass beyond MAX_TURN classified long_park (towing candidates);
    residual arrivals are night stops, residual departures carried-in
    aircraft off overnight parking. Kept and labelled, never invented."""
    from ddfs_bridge import MIN_TURN, MAX_TURN
    BAND = {"A": "RJ", "B": "RJ", "C": "NB", "D": "NB", "E": "WB", "F": "WB"}
    arrs = [e for e in de if e["ad"] == "A"]
    deps = [e for e in de if e["ad"] == "D"]
    used = set()

    def _fn(e):
        try:
            return int("".join(ch for ch in str(e["fno"]) if ch.isdigit()))
        except ValueError:
            return None

    def cands(a, lo, hi):
        band = BAND.get(a["icao"], "NB")
        out = []
        for i, d in enumerate(deps):
            if i in used or d["carrier"] != a["carrier"] or d["icao"] != a["icao"]:
                continue
            delta = d["minute"] - a["minute"]
            if not (lo <= delta <= hi):
                continue
            fa, fd = _fn(a), _fn(d)
            adj = abs(fd - fa) if fa is not None and fd is not None else 99
            same_ac = 0 if d["actype"] == a["actype"] else 1
            out.append((adj, same_ac, delta, i))
        return sorted(out)

    pairs = []   # (arr, dep, dwell, kind)
    paired_arr = set()
    band_of = lambda a: BAND.get(a["icao"], "NB")
    for kind in ("standard_turn", "long_park"):
        for tight in (True, False):
            for k, a in enumerate(arrs):
                if k in paired_arr:
                    continue
                if kind == "standard_turn":
                    lo, hi = MIN_TURN[band_of(a)], MAX_TURN[band_of(a)]
                else:
                    lo, hi = MAX_TURN[band_of(a)] + 1, 1440
                c = cands(a, lo, hi)
                if tight:
                    c = [x for x in c if x[0] <= 3]
                if c:
                    adj, same_ac, delta, i = c[0]
                    used.add(i)
                    paired_arr.add(k)
                    pairs.append((a, deps[i], delta, kind))
    night_stops = [a for k, a in enumerate(arrs) if k not in paired_arr]
    carried_deps = [d for i, d in enumerate(deps) if i not in used]
    bins = [(0, 45), (46, 90), (91, 180), (181, 360), (361, 1440)]
    bin_labels = ["<=45", "46-90", "91-180", "181-360", ">360"]
    codes = sorted(set(e["icao"] for e in de)) or ["C"]
    per_code, dwell_bins = {}, {}
    for c in codes:
        pc = [p for p in pairs if p[0]["icao"] == c]
        dw = sorted(p[2] for p in pc)
        med = dw[len(dw) // 2] if dw else None
        per_code[c] = {
            "rotations": len(pc),
            "median_turn_min": med,
            "turnarounds": sum(1 for p in pc if p[3] == "standard_turn"),
            "long_park": sum(1 for p in pc if p[3] == "long_park"),
            "night_stops": sum(1 for a in night_stops if a["icao"] == c),
            "carried_in_deps": sum(1 for d in carried_deps if d["icao"] == c),
        }
        dwell_bins[c] = [sum(1 for p in pc if lo <= p[2] <= hi) for (lo, hi) in bins]
    rot = ["Arr time\tDep time\tAirline\tArr flight\tDep flight\tAircraft\tICAO code\tGround time (min)\tClassification"]
    for (a, d, delta, kind) in sorted(pairs, key=lambda p: p[0]["minute"]):
        rot.append(f"{a['minute']//60:02d}:{a['minute']%60:02d}\t{d['minute']//60:02d}:{d['minute']%60:02d}"
                   f"\t{a['carrier']}\t{a['fno']}\t{d['fno']}\t{a['actype']}\t{a['icao']}\t{delta}\t{kind}")
    for a in sorted(night_stops, key=lambda e: e["minute"]):
        rot.append(f"{a['minute']//60:02d}:{a['minute']%60:02d}\t-\t{a['carrier']}\t{a['fno']}\t-\t{a['actype']}\t{a['icao']}\t-\tnight_stop")
    for d in sorted(carried_deps, key=lambda e: e["minute"]):
        rot.append(f"-\t{d['minute']//60:02d}:{d['minute']%60:02d}\t{d['carrier']}\t-\t{d['fno']}\t{d['actype']}\t{d['icao']}\t-\tcarried_in")
    return {
        "convention": ("Rotation pairing per the bridge Part A rules: greedy within the class turn band "
                       "(RJ 20-240, NB 25-240, WB 40-360 min), flight-number adjacency settled first, same "
                       "carrier and ICAO class; beyond the band pairs classify long_park (towing candidates); "
                       "residual arrivals night stops, residual departures carried-in off overnight parking."),
        "per_code": per_code,
        "dwell_bin_labels": bin_labels,
        "dwell_bins": dwell_bins,
        "totals": {"rotations": len(pairs),
                   "turnarounds": sum(1 for p in pairs if p[3] == "standard_turn"),
                   "long_park_tow_candidates": sum(1 for p in pairs if p[3] == "long_park"),
                   "night_stops": len(night_stops),
                   "carried_in_deps": len(carried_deps)},
        "rotations_tsv": "\n".join(rot)}


def _day_summary(ap, date):
    """Light summary of one calendar date (for the basis-duality card)."""
    de = day_events(ap, date)
    hr_a = defaultdict(int); hr_s = defaultdict(int)
    for e in de:
        hr_a[e["minute"] // 60] += 1
        hr_s[e["minute"] // 60] += e["seats"]
    return {"design_day": str(date), "day_atms": len(de),
            "day_seats": sum(e["seats"] for e in de),
            "max_hour_atms": max(hr_a.values(), default=0),
            "max_hour_seats": max(hr_s.values(), default=0)}


def api_ddfs(q):
    ap = (q.get("airport") or "").upper()
    year = int(q.get("year"))
    basis = q.get("basis", "atm")
    date_s = q.get("date", "auto")
    method = (q.get("method") or "sbr30").lower()
    ev = events_for(ap, year)
    mev = weighted_for(ap, year) if basis == "pax" else ox.to_module_events(ev)
    hourly = mm.hourly_series(mev, basis=basis)
    s30 = mm.sbr(hourly, 30)  # the module's own deterministic pick (tie-break canonical)
    sbr_day, sbr_hour, sbr_val = s30["date"], s30["hour"], s30["value"]
    # DAY-PICK METHOD (JC, 20 July): any dated method from the module's own
    # canonical table, not SBR30 only. PMAD and PMAWD are month-average
    # constructs with no calendar date, so they cannot pick a buildable day.
    PICKS = {"sbr30", "sbr20", "sbr40", "bhr5", "peak_hour_absolute",
             "iata_busy_day", "peak_day", "p90_day"}
    picked_label = "SBR30 day (auto)"
    if method == "sbr30" or method not in PICKS:
        date = dt.date.fromisoformat(sbr_day) if isinstance(sbr_day, str) else sbr_day
    else:
        mt = mm.method_table(mev, basis=basis, source=f"oag.duckdb live, {ap} {year}")
        d = mt[method]["date"]
        date = dt.date.fromisoformat(d) if isinstance(d, str) else d
        picked_label = dict(mm.LABELS).get(method, method) + " (auto)"
    if date_s != "auto":
        date = dt.date.fromisoformat(date_s)
    # BASIS DUALITY (JC, 20 July): the airside day (ATM pick) and the landside
    # day (pax pick) are not always the same day; the pax peak can fall on a
    # heavier-gauge or higher-load day. Both picks run on every build; stands
    # and runway size on the ATM basis, terminal on the pax basis.
    def _pick(b):
        mv = weighted_for(ap, year) if b == "pax" else ox.to_module_events(ev)
        s = mm.sbr(mm.hourly_series(mv, basis=b), 30)
        d = s["date"]
        d = dt.date.fromisoformat(d) if isinstance(d, str) else d
        return d, s
    date_a, s_a = (date, s30) if basis == "atm" else _pick("atm")
    date_p, s_p = (date, s30) if basis == "pax" else _pick("pax")
    dual = {"atm": dict(_day_summary(ap, date_a),
                        sbr30_value=round(s_a["value"], 1),
                        sbr30_hour=f"{s_a['hour']:02d}:00" if isinstance(s_a["hour"], int) else str(s_a["hour"]),
                        basis="atm (movements)"),
            "pax": dict(_day_summary(ap, date_p),
                        sbr30_value=round(s_p["value"], 1),
                        sbr30_hour=f"{s_p['hour']:02d}:00" if isinstance(s_p["hour"], int) else str(s_p["hour"]),
                        basis="pax (Sabre-weighted, indicative)"),
            "diverge": date_a != date_p,
            "note": ("The airside and landside design days DIVERGE: stands and runway "
                     "belong to the ATM day, terminal sizing to the pax day; both stated."
                     if date_a != date_p else
                     "Both counting bases pick the same design day.")}
    de = day_events(ap, date)
    hr = defaultdict(lambda: [0, 0])
    for e in de:
        hr[e["minute"] // 60][0 if e["ad"] == "A" else 1] += 1
    codes = "ABCDEF"
    delta = defaultdict(lambda: dict((c, 0) for c in codes))
    for e in de:
        delta[e["minute"]][e["icao"]] += 1 if e["ad"] == "A" else -1
    level = {c: 0 for c in codes}; run_min = {c: 0 for c in codes}
    for t in sorted(delta):
        for c in codes:
            level[c] += delta[t][c]; run_min[c] = min(run_min[c], level[c])
    level = {c: -run_min[c] for c in codes}
    maxaog = dict(level); carried_in = sum(level.values())
    stand_start = dict(level)
    # hourly AOG ledger per class (max level within each clock hour), for the
    # ledger chart on the live page (v1 Studio chAog equivalent, live data)
    times = sorted(delta)
    stand_hourly = {c: [0] * 24 for c in codes}
    ti = 0
    for h in range(24):
        hmax = {c: level[c] for c in codes}
        while ti < len(times) and times[ti] < (h + 1) * 60:
            t = times[ti]
            for c in codes:
                level[c] += delta[t][c]
                if level[c] > hmax[c]:
                    hmax[c] = level[c]
                if level[c] > maxaog[c]:
                    maxaog[c] = level[c]
            ti += 1
        for c in codes:
            stand_hourly[c][h] = hmax[c]
    sched = ["# " + tl.OAG_STATEMENT,
             "#\tA/D\tTime\tAirline\tFlight\tO/D\tSeats\tAircraft\tICAO code"]
    for i, e in enumerate(de):
        sched.append(f"{i+1}\t{e['ad']}\t{e['minute']//60:02d}:{e['minute']%60:02d}\t{e['carrier']}\t{e['fno']}\t{e['od']}\t{e['seats']}\t{e['actype']}\t{e['icao']}")
    # LANDSIDE BUILD (JC, 20 July): the pax peak can fall on a different day
    # to the airfield peak, so the landside profile is built on the PAX-pick
    # day, not the airside day, whenever the two diverge.
    lde = de if date_p == date else day_events(ap, date_p)
    lhs = defaultdict(int)
    lhs_a = defaultdict(int)
    lhs_d = defaultdict(int)
    for e in lde:
        h = e["minute"] // 60
        lhs[h] += e["seats"]
        (lhs_a if e["ad"] == "A" else lhs_d)[h] += e["seats"]
    peak_h = max(lhs, key=lhs.get) if lhs else 0
    landside = {"design_day": str(date_p),
                "same_day_as_airside_build": date_p == date,
                "hourly_seats": [lhs.get(h, 0) for h in range(24)],
                "hourly_seats_arr": [lhs_a.get(h, 0) for h in range(24)],
                "hourly_seats_dep": [lhs_d.get(h, 0) for h in range(24)],
                "day_seats": sum(e["seats"] for e in lde),
                "peak_hour_seats": lhs.get(peak_h, 0),
                "peak_hour": f"{peak_h:02d}:00",
                "note": ("Landside profile built on the pax-pick day; seats are the "
                         "day-grain proxy, pax = seats x load factor is the "
                         "engagement's input (ZAG precedent 0.80, stated not defaulted).")}
    return {"airport": ap, "year": year, "basis": basis,
            "design_day": str(date), "picked_by": picked_label if date_s == "auto" else "user",
            "sbr30_hour": f"{sbr_hour:02d}:00" if isinstance(sbr_hour, int) else str(sbr_hour),
            "sbr30_value": round(sbr_val, 1),
            "day_atms": len(de), "day_seats": sum(e["seats"] for e in de),
            "hourly": {f"{h:02d}": hr[h] for h in range(24)},
            "max_hour_atms": max((v[0] + v[1] for v in hr.values()), default=0),
            "stand_max_aog": maxaog, "carried_in": carried_in,
            "stand_start": stand_start, "stand_hourly": stand_hourly,
            "dual": dual, "landside": landside, "occupancy": day_occupancy(de),
            "schedule_tsv": "\n".join(sched),
            "base_statement": tl.OAG_STATEMENT,
            "note": "Single-year DDFS from held schedules. Forecast-year growth needs the engagement pack (ZAG precedent); stated, not defaulted."}


def api_zagreb_forecast(q):
    """ZAG forecast-year DDFS measures from the canonical oracle run
    (ddfs_zagreb_oracle, pack-driven; conventions note 35 v2). Served from
    zagreb_oracle_run_v02.tsv so the live answer always matches the pinned
    increment; rerunning the oracle refreshes the file, not this code."""
    year = q.get("year", "2030")
    import csv as _csv
    path = os.path.join(ROOT, "ddfs_bridge_fixtures", "zagreb_oracle_run_v02.tsv")
    rows = []
    with open(path) as f:
        for r in _csv.DictReader(f, delimiter="\t"):
            if r["year"] == year and not r["value"].startswith("FLAG"):
                rows.append([r["sheet"], r["section"], r["measure"], r["row"], r["split"], str(round(float(r["value"])))])
    tsv = "sheet\tsection\tmeasure\trow\tsplit\tvalue\n" + "\n".join("\t".join(r) for r in rows)
    return {"airport": "ZAG", "year": year, "rows": len(rows), "tsv": tsv,
            "years_available": ["2025", "2030", "2035", "2040", "2045"],
            "note": "Pack-driven forecast regeneration in sample mode (Zagreb oracle, 19 July 2026); open conventions and the diff against the sent deliverable are in the Studio's oracle card (/demo). Fidelity reconciliation of 23 July 2026: overall BHR growth matches the sent case (x2.12 vs x2.12 to 2045); residuals are the two-week base-year concentration (+13.4% on the 2-way total 30th hour, resolves at the full-year store load) and the Non-Schengen composition (open with Jess). GA stand blocks are an input assumption and are excluded here."}


def api_airports(q):
    return {"airports": pe.airports_list()}


def api_engine(q):
    b, a = pe.airport_row((q.get("airport") or "ZAG").upper())
    return {"airport": a["c"], "name": a["n"], "country": a["cty"],
            "region": a["reg"], "years": b["years"], "base_year": b["base"],
            "base_mppa": a["base"], "growth": a["g"], "dom_share": a["dom"],
            "connecting_share": a["cx"], "series": a["series"],
            "dests": a["dests"][:10],
            "regress": {k: a["regress"].get(k) for k in ("bG_est", "r2", "n", "reliable")},
            "provenance": "engine bundle cockpit.json (read-only)"}


def api_packs(q):
    folder = os.path.join(ROOT, "ddfs_packs")
    out = []
    try:
        for f in sorted(os.listdir(folder)):
            if f.endswith(".json"):
                out.append(f)
    except OSError:
        pass
    return {"packs": out}


def api_emit_pack(body, q):
    pack = pe.emit_pack(body["airport"], body.get("scenario", "Baseline"),
                        base_year=body.get("base_year"),
                        spot_years=body.get("spot_years"),
                        overrides=body.get("overrides"))
    saved = None
    if q.get("save") == "1":
        saved = os.path.basename(pe.save_pack(pack))
    return {"pack": pack, "saved": saved}


def api_forecast(body, q):
    pack = body.get("pack")
    if not pack:
        pack = pe.emit_pack(body["airport"], body.get("scenario", "Baseline"),
                            base_year=body.get("base_year"),
                            spot_years=body.get("spot_years"),
                            overrides=body.get("overrides"))
    return hc.forecast_from_pack(pack)


def _oag_day_or_wcweek(ap, date):
    """OAG comparator day: monthly files where held; else the matching weekday
    of a held wc sample week covering (or nearest) the date, stated as such."""
    de = day_events(ap, date)
    if de:
        return de, "OAG monthly-file schedules, same calendar day"
    import duckdb, re as _re
    con = store()
    wks = [w[0] for w in con.execute("""select distinct source_file from oag
        where (dep_airport=? or arr_airport=?) and year=? and service_type='J'
        and source_file like '%wc %'""", [ap, ap, date.year]).fetchall()]
    con.close()
    best = None
    for w in wks:
        m = _re.search(r"wc (\d{1,2})([A-Z][a-z]{2})(\d{2})", w)
        if not m:
            continue
        start = dt.date(2000 + int(m.group(3)), ox.MONTHS[m.group(2)], int(m.group(1)))
        d = abs((date - start).days)
        if best is None or d < best[0]:
            best = (d, w, start)
    if not best:
        return [], "no OAG schedules held for the year"
    _dist, wfile, wstart = best
    tag = wfile[wfile.index("wc "):].replace(".xlsx", "")
    ev = pe._week_day_events(ap, date.year, f"%{tag}%")
    dow = date.isoweekday()
    de2 = sorted([e for e in ev if e["dow"] == dow], key=lambda e: e["minute"])
    within = wstart <= date <= wstart + dt.timedelta(days=6)
    lab = (f"OAG wc-week schedules ({tag}, matching weekday"
           + ("" if within else f"; date outside the held week, nearest used") + ")")
    return de2, lab


def api_reconcile(q):
    """Towerlog/AODB vs OAG for one day (ACI review item 2): the actual-
    movements day beside the schedule day, gap quantified by category.
    Reads a pinned fixture day (ddfs_bridge_fixtures/zag_towerlog_<date>.tsv)
    or the local workbook (C:\\Avia\\2025 Towerlog.xlsx) when placed."""
    ap = (q.get("airport") or "ZAG").upper()
    date = dt.date.fromisoformat(q["date"])
    fx = f"zag_towerlog_{date.isoformat()}.tsv"
    sample = f"zag_towerlog_sample_{date.isoformat()}.tsv"
    if os.path.exists(os.path.join(ROOT, "ddfs_bridge_fixtures", fx)):
        ev = tl.load_fixture_day(fx)
    elif q.get("sample") == "1" and os.path.exists(os.path.join(ROOT, "ddfs_bridge_fixtures", sample)):
        oe, lab = _oag_day_or_wcweek(ap, date)
        r = tl.reconcile(ap, date, tl.load_fixture_day(sample), oag_events=oe, oag_base_label=lab)
        r["SAMPLE"] = ("14 of circa 230 movements, hand-pinned; machinery demonstration only, "
                       "NOT a day reconciliation. The full day extracts from the workbook at C:\\Avia.")
        return r
    else:
        x = tl._local_xlsx()
        if not x:
            return {"error": "FLAG: no towerlog held for this date (fixture or C:\\Avia\\2025 Towerlog.xlsx); "
                             "the OAG base stands with its exclusions stated", "statement": tl.OAG_STATEMENT}
        ev = tl.load_xlsx_day(x, date)
        if not ev:
            return {"error": f"towerlog holds no rows for {date}", "statement": tl.OAG_STATEMENT}
    oe, lab = _oag_day_or_wcweek(ap, date)
    return tl.reconcile(ap, date, ev, oag_events=oe, oag_base_label=lab)


def api_hindcast(q):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = hc.adac_hindcast(verbose=True)
    return {"scoreboard": buf.getvalue(), "families": r["families"],
            "excluded": r["excluded"], "pack": r["pack"]}


class Handler(http.server.SimpleHTTPRequestHandler):
    def _authed(self):
        if not PASSWORD:
            return True
        h = self.headers.get("Authorization") or ""
        if h.startswith("Basic "):
            try:
                supplied = base64.b64decode(h[6:]).decode("utf-8", "ignore").split(":", 1)[-1]
                if hmac.compare_digest(supplied, PASSWORD):
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{REALM}"')
        self.end_headers()
        return False

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _file(self, name):
        p = os.path.join(ROOT, name)
        try:
            b = open(p, "rb").read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._authed():
            return
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._file("ddfs_live.html")
            if u.path == "/demo":
                return self._file("ddfs_front_v1.html")
            if u.path == "/api/years":
                return self._json(api_years(q))
            if u.path == "/api/methods":
                return self._json(api_methods(q))
            if u.path == "/api/ddfs":
                return self._json(api_ddfs(q))
            if u.path == "/api/zagreb_forecast":
                return self._json(api_zagreb_forecast(q))
            if u.path == "/cockpit":
                # the Cockpit folded into the unified tool as its Forecast
                # stage (23 July, JC); the old page stays on disk, superseded
                return self._file("ddfs_live.html")
            if u.path == "/api/airports":
                return self._json(api_airports(q))
            if u.path == "/api/engine":
                return self._json(api_engine(q))
            if u.path == "/api/packs":
                return self._json(api_packs(q))
            if u.path == "/api/hindcast":
                return self._json(api_hindcast(q))
            if u.path == "/api/reconcile":
                return self._json(api_reconcile(q))
        except Exception as ex:
            return self._json({"error": f"{type(ex).__name__}: {ex}"}, 500)
        self.send_error(404)  # nothing else in Model_refs is served

    def do_POST(self):
        if not self._authed():
            return
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/emit_pack":
                return self._json(api_emit_pack(body, q))
            if u.path == "/api/forecast":
                return self._json(api_forecast(body, q))
        except Exception as ex:
            return self._json({"error": f"{type(ex).__name__}: {ex}"}, 500)
        self.send_error(404)


class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    if not PASSWORD:
        print("WARNING: no access password set - server is OPEN. Local development only.")
    httpd = ThreadingServer(("", PORT), Handler)
    print(f"Avia Cortex DDFS live service on http://localhost:{PORT}/  (Ctrl+C to stop)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
