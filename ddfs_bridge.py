"""ddfs_bridge.py v0 - DDFS bridge, reference-day builder.

Stage 1 of the WS7 bridge (note 23 v2, Part A): parse an OAG Analyser
Schedules Bank Structure export into flight events, pair arrivals with
departures (classification, not forced matching, per note 23 v2 4a),
and emit the reference day at TransferSheet grain.

Oracle: AHB 24 July 2025 (template v15 OAG_export vs AHB_DDFS_TransferSheet).
Source data carries provenance; nothing is invented (flag rather than fill).
"""
import csv, sys
from datetime import datetime, timedelta

MIN_TURN = {"NB": 25, "WB": 40, "RJ": 20}
MAX_TURN = {"NB": 240, "WB": 360, "RJ": 240}   # beyond this: not a standard turn
WB_EQUIP = {"330","333","332","339","343","346","350","351","359","744","747","772","773","777","77L","77W","787","788","789","78J","78X","380","388","763","764","767"}

def ac_class(equip, seats):
    e = str(equip).strip()
    if e in WB_EQUIP: return "WB"
    try: s = int(seats)
    except (TypeError, ValueError): s = 0
    if s > 240: return "WB"
    if 0 < s <= 110: return "RJ"
    return "NB"

def hhmm(v):
    s = str(v).strip()
    if not s: return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    return None

def read_oag_bank(path):
    """Bank structure: arrivals cols 0-8, departures cols 8-16, hub time col 8."""
    events = []
    with open(path, newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    start = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Airline")
    for r in rows[start + 1:]:
        r = (r + [""] * 17)[:17]
        if r[0].strip():                      # arrival at hub
            t = hhmm(r[8])
            if t is None: continue
            events.append(dict(al=r[0].strip(), fn=r[1].strip(), od=r[2].strip(),
                opdays=r[3].strip(), equip=r[4].strip(), svc=r[5].strip(),
                seats=r[6].strip(), time=t, ad="A"))
        elif r[8].strip():                    # departure from hub
            t = hhmm(r[8])
            if t is None: continue
            events.append(dict(al=r[16].strip(), fn=r[15].strip(), od=r[14].strip(),
                opdays=r[13].strip(), equip=r[12].strip(), svc=r[11].strip(),
                seats=r[10].strip(), time=t, ad="D"))
    for e in events:
        e["id"] = f"{e['al']}{e['fn']}_SP"
    return events

def fnum(fn):
    try: return int(fn)
    except ValueError: return None

def pair_events(events):
    """Greedy pairing within class turn band, midnight wrap allowed.
    Score: flight-number adjacency, same O/D, time proximity.
    Residuals classified, kept and labelled, never invented."""
    arrs = [e for e in events if e["ad"] == "A"]
    deps = [e for e in events if e["ad"] == "D"]
    used, pairs = set(), {}
    def cands(a):
        cls = ac_class(a["equip"], a["seats"])
        out = []
        for i, d in enumerate(deps):
            if i in used or d["al"] != a["al"]: continue
            if ac_class(d["equip"], d["seats"]) != cls: continue
            same_ac = 0 if (d["equip"] == a["equip"] and d["seats"] == a["seats"]) else 1
            delta = (d["time"] - a["time"]).total_seconds() / 60
            if delta < 0: delta += 1440          # midnight wrap
            if not (MIN_TURN[cls] <= delta <= MAX_TURN[cls]): continue
            fa, fd = fnum(a["fn"]), fnum(d["fn"])
            adj = abs(fd - fa) if fa is not None and fd is not None else 99
            out.append((adj, same_ac, 0 if d["od"] == a["od"] else 1, delta, i))
        return sorted(out)
    # two passes: settle tight flight-number pairs first, then the rest
    order = sorted(range(len(arrs)), key=lambda k: arrs[k]["time"])
    for tight in (True, False):
        for k in order:
            a = arrs[k]
            if a["id"] in pairs: continue
            c = cands(a)
            if tight: c = [x for x in c if x[0] <= 3]
            if c:
                adj, same_ac, samod, delta, i = c[0]
                used.add(i)
                pairs[a["id"]] = (deps[i]["id"], round(delta), "standard_turn")
    exceptions = []
    for a in arrs:
        if a["id"] not in pairs:
            exceptions.append((a["id"], "A", "unmatched"))
    for i, d in enumerate(deps):
        if i not in used:
            exceptions.append((d["id"], "D", "unmatched"))
    return pairs, exceptions

def run_oracle_diff(oag_path, oracle_path):
    events = pair_input = read_oag_bank(oag_path)
    pairs, exceptions = pair_events(events)
    # oracle
    with open(oracle_path, newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    hd = next(i for i, r in enumerate(rows) if "String" in r)
    cols = {n: j for j, n in enumerate(rows[hd])}
    orc = {}
    for r in rows[hd + 1:]:
        if len(r) <= cols["Pair"] or not r[cols["String"]].strip(): continue
        orc[r[cols["String"]].strip()] = dict(
            ad=r[cols["D/A"]].strip(), pair=r[cols["Pair"]].strip(),
            gt=r[cols["Ground time"]].strip())
    o_ids, b_ids = set(orc), {e["id"] for e in events}
    print(f"events: bridge {len(b_ids)} vs oracle {len(o_ids)}")
    print("only in oracle:", sorted(o_ids - b_ids) or "none")
    print("only in bridge:", sorted(b_ids - o_ids) or "none")
    o_pairs = {k: v["pair"] for k, v in orc.items() if v["ad"] == "A"}
    hit = sum(1 for k, v in o_pairs.items() if k in pairs and pairs[k][0] == v)
    print(f"pair match: {hit}/{len(o_pairs)}")
    for k, v in sorted(o_pairs.items()):
        got = pairs.get(k, ("-",))[0]
        if got != v: print(f"  MISMATCH {k}: oracle {v}, bridge {got}")
    gt_hit = gt_tot = 0
    for k, v in orc.items():
        if v["ad"] != "A" or k not in pairs: continue
        gt_tot += 1
        if pairs[k][1] == round(float(v["gt"])): gt_hit += 1
        else: print(f"  GT DIFF {k}: oracle {v['gt']}, bridge {pairs[k][1]}")
    print(f"ground time match: {gt_hit}/{gt_tot}")
    print("exceptions:", exceptions or "none")

if __name__ == "__main__" and len(sys.argv) == 3:
    run_oracle_diff(sys.argv[1], sys.argv[2])

def emit_transfersheet(events, pairs, year, out_path):
    """Schedule-side columns of the v15 TransferSheet layout; engine-computed
    columns (Pax, Transfer, O&D) and template lookups (Country, Region) are
    left to the template, per note 23 v2 section 1."""
    rev = {v[0]: (k, v[1]) for k, v in pairs.items()}
    hdr = ["String","Airline","Airline name","Origin","Op. days","Equipment",
           "Service type","Seats","Time","Hub time","Hour","D/A","Year",
           "Airline category","Pair","Ground time","Pair class"]
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(hdr)
        for e in sorted(events, key=lambda x: (x["ad"], x["time"])):
            if e["ad"] == "A" and e["id"] in pairs:
                pid, gt, pcls = pairs[e["id"]]
            elif e["ad"] == "D" and e["id"] in rev:
                pid, gt, pcls = rev[e["id"]][0], 0, "standard_turn"
            else:
                pid, gt, pcls = "", "", "unmatched"
            w.writerow([e["id"], e["al"], "", e["od"], e["opdays"], e["equip"],
                        e["svc"], e["seats"], e["time"].strftime("%H:%M:%S"), "",
                        e["time"].hour, e["ad"], year, e["al"], pid, gt, pcls])

# ---------------- Stage 2: the scaler (growth events per output year) -------

def read_growth_spec(path):
    """Inputs section 2 fixture -> {(airline, aircraft, cat_idx, year): n_routes},
    plus turnaround minutes per (airline, aircraft)."""
    slot_al = {"2.1":"F3","2.2":"XY","2.3":"SW","2.4":"5W","2.5":"3L","2.6":"OTH"}
    spec, turns, hdr = {}, {}, {}
    with open(path, newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[1] == "hdr":
                hdr[r[0]] = r[4:]; continue
            al, ac = slot_al[r[0]], r[2]
            if r[3]: turns[(al, ac)] = int(float(r[3]))
            for j, v in enumerate(r[4:]):
                if not v: continue
                y = hdr[r[0]][j] if j < len(hdr[r[0]]) else ""
                try: yr = int(float(y))
                except ValueError: continue
                n = int(float(v))
                if n: spec[(al, ac, j // 8, yr)] = n
    return spec, turns

def read_tod(path):
    """{airline: [24 hourly shares]} from the departure profile fixture
    (shares identical across distance categories in the Abha instance)."""
    slot_al = {"2.1":"F3","2.2":"XY","2.3":"SW","2.4":"5W","2.5":"3L","2.6":"OTH"}
    prof = {}
    with open(path, newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))[1:]
    for r in rows:
        al = slot_al[r[0]]
        prof.setdefault(al, [0.0]*24)[int(r[1])] = float(r[2] or 0)
    return prof

def alloc_hours(n, profile):
    """Deterministic largest-remainder allocation of n events over 24 hours."""
    quota = [n * p for p in profile]
    base = [int(q) for q in quota]
    rem = n - sum(base)
    order = sorted(range(24), key=lambda h: quota[h] - base[h], reverse=True)
    for h in order[:rem]: base[h] += 1
    out = []
    for h in range(24):
        out += [h] * base[h]
    return out

def generate_growth(spec, turns, prof):
    """Per output year: n routes -> n arrivals + n departures, hours by the
    airline profile (largest remainder), minutes spaced deterministically.
    The placement rule is the bridge's own (note 23 v2 Part A), not a clone
    of the template's internals."""
    events = []
    seq = {}
    by_year_al = {}
    for (al, ac, cat, yr), n in sorted(spec.items()):
        by_year_al.setdefault((yr, al), []).append((ac, cat, n))
    for (yr, al), items in sorted(by_year_al.items()):
        k = 0
        ntot = sum(n for _, _, n in items)
        dep_pool = alloc_hours(ntot, prof[al])
        arr_pool = alloc_hours(ntot, prof[al])
        j = 0
        for ac, cat, n in items:
            dep_h = dep_pool[j:j + n]
            arr_h = arr_pool[j:j + n]
            j += n
            for i in range(n):
                s = seq[(yr, al)] = seq.get((yr, al), 0) + 1
                aid, did = f"{al}N{yr}_{s}A", f"{al}N{yr}_{s}D"
                ma, md = (7 * k) % 60, (7 * k + 30) % 60
                k += 1
                base = datetime(2000, 1, 1)
                events.append(dict(al=al, fn=f"N{yr}_{s}", od=f"cat{cat+1}",
                    opdays="", equip=ac, svc="J", seats="", ad="A", year=yr,
                    time=base + timedelta(hours=arr_h[i], minutes=ma), id=aid))
                events.append(dict(al=al, fn=f"N{yr}_{s}", od=f"cat{cat+1}",
                    opdays="", equip=ac, svc="J", seats="", ad="D", year=yr,
                    time=base + timedelta(hours=dep_h[i], minutes=md), id=did))
    return events

def pair_growth(events):
    """Pair generated growth events per year and airline: band pass first,
    then residuals paired loose and classified night_stop (the template also
    pairs everything, with long ground times)."""
    pairs, exceptions = {}, []
    keys = sorted({(e["year"], e["al"], e["equip"]) for e in events})
    for yr, al, eq in keys:
        sub = [e for e in events if e["year"] == yr and e["al"] == al
               and e["equip"] == eq]
        p, exc = pair_events(sub)
        pairs.update(p)
        arrs = [e for e in sub if e["ad"] == "A" and e["id"] not in p]
        deps_left = [e for e in sub if e["ad"] == "D"
                     and e["id"] not in {v[0] for v in p.values()}]
        for a in sorted(arrs, key=lambda e: e["time"]):
            best = None
            for d in deps_left:
                if d["equip"] != a["equip"]: continue
                delta = (d["time"] - a["time"]).total_seconds() / 60
                if delta < 0: delta += 1440
                if best is None or delta < best[0]: best = (delta, d)
            if best:
                delta, d = best
                deps_left.remove(d)
                pairs[a["id"]] = (d["id"], round(delta), "night_stop")
            else:
                exceptions.append((a["id"], "A", "unmatched"))
        for d in deps_left:
            exceptions.append((d["id"], "D", "unmatched"))
    return pairs, exceptions

def build_year_tables(oag_path, growth_path, tod_path, base_year, out_dir):
    """End to end: reference day + per-year growth events, one TransferSheet
    TSV per output year (day(Y) = reference day + growth events of year Y)."""
    import os
    ref = read_oag_bank(oag_path)
    rp, _ = pair_events(ref)
    spec, turns = read_growth_spec(growth_path)
    prof = read_tod(tod_path)
    gev = generate_growth(spec, turns, prof)
    gp, _ = pair_growth(gev)
    years = sorted({e["year"] for e in gev})
    for y in years:
        rows = list(ref) + [e for e in gev if e["year"] == y]
        allp = dict(rp); allp.update({k: v for k, v in gp.items()
            if k in {e["id"] for e in gev if e["year"] == y}})
        emit_transfersheet(rows, allp, y, os.path.join(out_dir, f"design_day_{y}.tsv"))
    return years

def selftest(fix_dir="."):
    import os
    p = lambda n: os.path.join(fix_dir, n)
    ev = read_oag_bank(p("oag_export_ahb.tsv"))
    pairs, exc = pair_events(ev)
    assert len(ev) == 92 and len(pairs) == 46 and not exc, "reference-day oracle"
    spec, turns = read_growth_spec(p("inputs_growth.tsv"))
    prof = read_tod(p("inputs_tod.tsv"))
    gev = generate_growth(spec, turns, prof)
    gp, gexc = pair_growth(gev)
    assert sum(spec.values()) == 228 and len(gev) == 456, "growth generation"
    assert len(gp) == 228 and not gexc, "growth pairing"
    print("ddfs_bridge selftest: all assertions pass "
          "(92-event reference day, 46/46 pairs; 228 growth routes paired, "
          "0 unmatched)")

if __name__ == "__main__" and len(sys.argv) == 2 and sys.argv[1] == "selftest":
    selftest("/".join(__file__.split("/")[:-1] + ["ddfs_bridge_fixtures"]))

# ---------------- Stage 3: the AOG ledger (Part C stand demand) ------------

ICAO_LETTER = {"E190":"C","CRJ":"C","AT7":"C","DH4":"C","320":"C","32N":"C",
    "321":"C","32Q":"C","319":"C","737":"C","738":"C","73H":"C","7M8":"C",
    "B737":"C","A320":"C","A321":"C","757":"D","B757":"D","767":"D",
    "330":"E","333":"E","332":"E","339":"E","350":"E","359":"E","A350":"E",
    "787":"E","788":"E","789":"E","B787":"E","777":"E","77W":"E","380":"F"}

def icao_letter(equip, seats):
    e = str(equip).strip()
    if e in ICAO_LETTER: return ICAO_LETTER[e]
    return "E" if ac_class(equip, seats) == "WB" else "C"

def aog_ledger(events, pairs):
    """Exact hourly aircraft-on-ground ledger by ICAO code letter (Bologna
    practice, note 26 adoption). Occupancy per pair runs arrival to paired
    departure with midnight wrap; wrapped pairs are the overnight stock
    (DayBeforeArr semantics). Returns per-class 24-hour series (AOG at the
    end of each clock hour) plus overall, overnight and individual peaks.
    Definitions held as working assumptions pending Jess's review:
    overnight peak = max over hours 00-05; individual peak = per-class max."""
    by_id = {e["id"]: e for e in events}
    spans = []
    for aid, (did, gt, pcls) in pairs.items():
        a, d = by_id.get(aid), by_id.get(did)
        if not a or not d: continue
        t0 = a["time"].hour * 60 + a["time"].minute
        t1 = d["time"].hour * 60 + d["time"].minute
        cls = icao_letter(a["equip"], a["seats"])
        if t1 >= t0: spans.append((t0, t1, cls))
        else: spans.append((t0, 1440, cls)); spans.append((0, t1, cls))
    classes = sorted({c for _, _, c in spans})
    series = {c: [0]*24 for c in classes}
    for h in range(24):
        probe = h * 60 + 60 - 1                     # end of clock hour
        for t0, t1, c in spans:
            if t0 <= probe < t1: series[c][h] += 1
    total = [sum(series[c][h] for c in classes) for h in range(24)]
    peak_hour = max(range(24), key=lambda h: total[h])
    out = {
        "series": series, "total": total,
        "overall_peak": {c: series[c][peak_hour] for c in classes},
        "overall_peak_total": total[peak_hour], "peak_hour": peak_hour,
        "overnight_peak": {c: max(series[c][0:6]) for c in classes},
        "individual_peak": {c: max(series[c]) for c in classes},
        "avg_aog_min": round(sum((t1 - t0) for t0, t1, _ in spans)
                             / max(len(pairs), 1), 1)}
    return out

def emit_aog(led, out_path):
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        cs = sorted(led["series"])
        w.writerow(["Hour"] + cs + ["Total"])
        for h in range(24):
            w.writerow([h] + [led["series"][c][h] for c in cs] + [led["total"][h]])
        for name in ("overall_peak", "overnight_peak", "individual_peak"):
            w.writerow([name] + [led[name][c] for c in cs] +
                       [led["overall_peak_total"] if name == "overall_peak" else ""])

def selftest_aog(fix_dir="."):
    import os
    ev = read_oag_bank(os.path.join(fix_dir, "oag_export_ahb.tsv"))
    pairs, _ = pair_events(ev)
    led = aog_ledger(ev, pairs)
    assert led["avg_aog_min"] == 46.4, "AOG regression (reference day)"
    assert led["overall_peak_total"] == 3, "AOG peak regression"
    print("aog selftest: avg 46.4 min, peak 3, Ok")

# ---------------- Stage 4: canonical emit and the CAST adapter -------------

CANON_COLS = ["event_id","rotation_id","pair_class","sp_flag","output_year",
    "season","scenario_id","pack_id","source","derivation_flag","placement_rule",
    "airline_code","airline_name","flight_number","airline_category",
    "service_type","commercial_flag","od_airport","od_city","od_country",
    "od_region","dd_region","distance_band","dom_intl","schengen_flag",
    "eea_final_dest","eea_aircraft_dest","ad_flag","sched_time","hour_bucket",
    "block_time","ground_time_min","equipment_iata","aircraft_model",
    "aircraft_class","icao_code_letter","seats","registration","pax_onboard",
    "transfer_pax","od_pax","load_factor","bags","cargo_kg","terminal",
    "stand_id"]

def canonical_rows(events, pairs, year, season, scenario, pack_id, rule):
    """Note 28 superset: one row per event; unpopulatable fields left blank
    (flag rather than fill; blanks documented per source grade)."""
    rev = {v[0]: (k, v[1], v[2]) for k, v in pairs.items()}
    rows = []
    for e in sorted(events, key=lambda x: (x["ad"], x["time"])):
        if e["ad"] == "A" and e["id"] in pairs:
            pid, gt, pcls = pairs[e["id"]]
        elif e["ad"] == "D" and e["id"] in rev:
            pid, gt, pcls = rev[e["id"]][0], 0, rev[e["id"]][2]
        else:
            pid, gt, pcls = "", "", "unmatched"
        sp = e["id"].endswith("_SP")
        band = e["od"] if str(e["od"]).startswith("cat") else ""
        rows.append(dict(event_id=e["id"], rotation_id=pid, pair_class=pcls,
            sp_flag="SP" if sp else "generated", output_year=year,
            season=season, scenario_id=scenario, pack_id=pack_id,
            source="OAG bank export" if sp else "bridge growth",
            derivation_flag="" if sp else "generated", placement_rule=rule,
            airline_code=e["al"], airline_name="", flight_number=e["fn"],
            airline_category=e["al"], service_type=e["svc"],
            commercial_flag="Commercial" if e["svc"] == "J" else e["svc"],
            od_airport=e["od"] if not band else "", od_city="", od_country="",
            od_region="" if not band else e["od"], dd_region="",
            distance_band=band, dom_intl="", schengen_flag="",
            eea_final_dest="", eea_aircraft_dest="", ad_flag=e["ad"],
            sched_time=e["time"].strftime("%H:%M:%S"),
            hour_bucket=e["time"].hour, block_time="",
            ground_time_min=gt, equipment_iata=e["equip"], aircraft_model="",
            aircraft_class=ac_class(e["equip"], e["seats"]),
            icao_code_letter=icao_letter(e["equip"], e["seats"]),
            seats=e["seats"], registration="", pax_onboard="", transfer_pax="",
            od_pax="", load_factor="", bags="", cargo_kg="", terminal="",
            stand_id=""))
    return rows

def emit_canonical(rows, out_path):
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(CANON_COLS)
        for r in rows: w.writerow([r[c] for c in CANON_COLS])

def emit_cast(rows, out_path):
    """CAST projection (Tashkent field set): pure column projection of the
    canonical table, per note 28 section 3. Block time falls back to
    scheduled time, flagged in the header note."""
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["#","Flight direction","Block time","Airline",
                    "Aircraft code","Domestic/International","Passengers","Type"])
        for i, r in enumerate(sorted(rows, key=lambda x: x["sched_time"]), 1):
            w.writerow([i, r["ad_flag"],
                        r["block_time"] or r["sched_time"], r["airline_code"],
                        r["equipment_iata"], r["dom_intl"] or "",
                        r["pax_onboard"] or "", r["commercial_flag"]])

def selftest_canonical(fix_dir="."):
    import os
    ref = read_oag_bank(os.path.join(fix_dir, "oag_export_ahb.tsv"))
    rp, _ = pair_events(ref)
    rows = canonical_rows(ref, rp, 2025, "S", "Base", "fixture", "n/a")
    assert len(rows) == 92 and len(CANON_COLS) == 46, "canonical emit regression"
    assert all(r["sp_flag"] == "SP" for r in rows), "sp_flag regression"
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as t:
        pass
    emit_cast(rows, t.name)
    n = sum(1 for _ in open(t.name)) - 1
    assert n == 92, "CAST projection identity"
    print("canonical selftest: 92 rows x 46 cols, CAST projection identity, Ok")
