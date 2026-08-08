"""ddfs_ladder.py - the store-day test ladder (note 23 v3 section 6).
Three rungs, each diffing a regeneration against a pinned sent-deliverable
fixture in ddfs_bridge_fixtures:
  1. ZAGREB  - ddfs_zagreb_oracle vs zagreb_oracle_targets.tsv (995 rows)
  2. ADAC    - AUH design-day hourly ATMs vs adac2024_oracle_targets.tsv
  3. BOLOGNA - BLQ stand ledger and busy hour vs bologna_s25_oracle_targets.tsv
MODES: sample (wc weeks, today) and full (monthly files, when the full-year
store lands). The harness states its mode and every proxy it uses; divergence
from a different reference week is expected and reported, not hidden.
Usage: python3 ddfs_ladder.py [--rung 1|2|3]
Author: Avia Solutions.
"""
import csv, re, sys, datetime as dt
from collections import defaultdict
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "ddfs_bridge_fixtures")
sys.path.insert(0, HERE)

ICAO = {"SF3":"B","AT4":"B","CRJ":"B","CR9":"C","DH4":"C","AT7":"C",
 "319":"C","320":"C","321":"C","32A":"C","32B":"C","32N":"C","32Q":"C","221":"C","223":"C",
 "73H":"C","738":"C","739":"C","7M8":"C","7M9":"C","E70":"C","E75":"C","E90":"C","E95":"C","295":"C","290":"C",
 "332":"E","333":"E","339":"E","343":"E","359":"E","35K":"E","351":"E",
 "787":"E","788":"E","789":"E","781":"E","77W":"E","77L":"E","772":"E","773":"E","763":"D","752":"D","764":"D",
 "388":"F","744":"E","748":"F"}

def store_path():
    from ddfs_oag_expand import _store_path
    return _store_path("oag.duckdb")

def week_events(airport, year, week_like):
    """Generic wc-week extraction, ZAG-oracle conventions: event-grain dedupe
    (carrier, flight number, dow, direction, minute), dup_marker unused."""
    import duckdb
    con = duckdb.connect(store_path(), read_only=True)
    rows = con.execute("""select carrier, carrier_category, flight_no,
        dep_airport, arr_airport, local_dep_time, local_arr_time, local_arr_day,
        days_of_op, seats, aircraft_code
      from oag where (dep_airport=? or arr_airport=?) and year=?
        and source_file like ? and service_type='J'""",
      [airport, airport, year, week_like]).fetchall()
    con.close()
    seen, ev = set(), []
    for (cx, cat, fn, dep, arr, dt_, at_, ad_day, dow, seats, ac) in rows:
        is_dep = dep == airport
        t = (dt_ if is_dep else at_) or ""
        t = t.strip()
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
                               carrier=cx, cat=cat, seats=int(seats or 0),
                               icao=ICAO.get(ac, "C")))
    return ev

def load_fixture(name):
    tgt = {}
    with open(os.path.join(FIX, name)) as f:
        rdr = csv.DictReader((l for l in f if not l.startswith("#")), delimiter="\t")
        for r in rdr:
            v = r["value"].replace(",", "").replace("%", "")
            try:
                x = float(v)
            except ValueError:
                continue  # non-numeric rows (flagged text) skipped, not invented
            tgt[(r["sheet"], r["section"], r["measure"], r["row"], r["split"], r["year"])] = x
    return tgt

def score(pairs, label):
    """pairs: list of (target, got). Prints and returns (mape, meanabs)."""
    es = [(abs(g - t) / abs(t) if t else abs(g - t), abs(g - t)) for t, g in pairs]
    mape = sum(e[0] for e in es) / len(es) * 100
    mab = sum(e[1] for e in es) / len(es)
    w25 = sum(1 for e in es if e[0] <= 0.25) * 100 // len(es)
    print(f"  {label:44s} n {len(es):4d}  MAPE {mape:6.1f}%  meanAbs {mab:8.2f}  within25% {w25}%")
    return mape, mab

def rung1():
    print("RUNG 1 - ZAGREB (mode: sample weeks; full-year rerun replaces C1 when the store lands)")
    import ddfs_zagreb_oracle as zo
    ok = zo.selftest()
    tgt = load_fixture("zagreb_oracle_targets.tsv")
    run = {}
    with open(os.path.join(FIX, "zagreb_oracle_run_v02.tsv")) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if not r["value"].startswith("FLAG"):
                run[(r["sheet"], r["section"], r["measure"], r["row"], r["split"], r["year"])] = float(r["value"])
    pairs = [(tgt[k], run[k]) for k in run if k in tgt]
    score(pairs, "all valued rows vs sent deliverable")
    # GROWTH DECOMPOSITION (ACI review item 1, 23 July 2026): the reconciliation
    # evidence on every run. Overall growth matches; the residuals are (a) the
    # base-year concentration of the two-week annualisation (proven +6.6% on
    # ZAG 2015 real data, resolves mechanically at store day) and (b) the
    # Non-Schengen composition (hers spreads, x1.55 vs the x2.02 annual path;
    # split basis is a Jess question). Do not tune to sample-week artefacts.
    def g(d, row, split):
        a = d.get(("Base", "30th BHRs - Overall", "", row, split, "2025"))
        b = d.get(("Base", "30th BHRs - Overall", "", row, split, "2045"))
        return (b / a) if a and b else None
    print("  growth decomposition, 30th BHRs 2045/2025 (sent | oracle | annual path x2.02):")
    for row, split in (("2-way", "Total"), ("Arrivals", "Schengen"), ("Arrivals", "Non-Schengen"),
                       ("Departures", "Schengen"), ("Departures", "Non-Schengen")):
        gs, go = g(tgt, row, split), g(run, row, split)
        if gs and go:
            print(f"    {row:10s} {split:12s} sent x{gs:.3f} | oracle x{go:.3f}")
    k25 = ("Base", "30th BHRs - Overall", "", "2-way", "Total", "2025")
    if k25 in tgt and k25 in run:
        print(f"  base-year 2-way total 30th hour: sent {tgt[k25]:.0f} vs oracle {run[k25]:.0f} "
              f"({run[k25]/tgt[k25]-1:+.1%}; two-week annualisation concentration, "
              f"proven +6.6% on ZAG 2015 real data; store day resolves)")
    return ok

def rung2():
    print("RUNG 2 - ADAC / AUH 2024 (mode: sample week wc 27May24; PROXY: design day = busiest")
    print("  day of the sample week; the sent convention is PMAD - divergence expected and stated)")
    ev = week_events("AUH", 2024, "%wc 27May24%")
    by_day = defaultdict(list)
    for e in ev:
        by_day[e["dow"]].append(e)
    dd = max(by_day, key=lambda d: len(by_day[d]))
    hourly = defaultdict(lambda: [0, 0])
    for e in by_day[dd]:
        hourly[e["minute"] // 60][0 if e["ad"] == "A" else 1] += 1
    tgt = load_fixture("adac2024_oracle_targets.tsv")
    pairs = []
    for hh in range(24):
        for i, ad in ((0, "A"), (1, "D")):
            k = ("Summary - ATMs", "Hourly ATMs", "ATMs", f"{hh:02d}", ad, "2024")
            if k in tgt:
                pairs.append((abs(tgt[k]), hourly[hh][i]))
    score(pairs, f"hourly ATMs vs sent 2024 columns (day dow={dd})")
    tot_t = sum(abs(tgt[k]) for k in tgt if k[1] == "Hourly ATMs" and k[3] == "Total" and k[5] == "2024")
    tot_g = sum(hourly[h][0] + hourly[h][1] for h in range(24))
    print(f"  day totals: sent {tot_t:.0f} ATMs vs sample-week proxy {tot_g} ATMs")
    return True

def rung3():
    print("RUNG 3 - BOLOGNA / BLQ S25 (mode: sample week wc 26May25; the sent ledger is the")
    print("  20/21 Jul 2025 linked schedule - a different week, divergence expected and stated)")
    ev = week_events("BLQ", 2025, "%wc 26May25%")
    # cyclic weekly ledger, ZAG-oracle machinery (weekly closure per class)
    codes = "ABCDEF"
    delta = defaultdict(lambda: dict((c, 0.0) for c in codes))
    arrsum = dict((c, 0.0) for c in codes); depsum = dict((c, 0.0) for c in codes)
    for e in ev:
        (arrsum if e["ad"] == "A" else depsum)[e["icao"]] += 1
    bal = {c: (depsum[c] / arrsum[c] if arrsum[c] else 1.0) for c in codes}
    for e in ev:
        t = (e["dow"] - 1) * 1440 + e["minute"]
        if e["ad"] == "D":
            delta[t][e["icao"]] -= 1
        else:
            delta[t][e["icao"]] += bal[e["icao"]]
    times = sorted(delta)
    level = {c: 0.0 for c in codes}; run_min = {c: 0.0 for c in codes}
    for t in times:
        for c in codes:
            level[c] += delta[t][c]; run_min[c] = min(run_min[c], level[c])
    level = {c: -run_min[c] for c in codes}
    maxaog = {c: 0.0 for c in codes}; ovn0 = dict(level)
    for t in times:
        for c in codes:
            level[c] += delta[t][c]
            maxaog[c] = max(maxaog[c], level[c])
    tgt = load_fixture("bologna_s25_oracle_targets.tsv")
    pairs = []
    for c in codes:
        k = ("StandDemand", "pax", "Max AOG", "Max", c, "2025")
        if k in tgt:
            pairs.append((tgt[k], round(maxaog[c])))
    if pairs:
        score(pairs, "Max AOG per ICAO class vs sent pax block")
    else:
        print("  fixture Max AOG keys not matched under expected naming - inspect fixture rows; got",
              [k for k in list(tgt)[:3]])
    # busy hour ATMs
    hourly = defaultdict(float)
    for e in ev:
        hourly[(e["dow"], e["minute"] // 60)] += 1
    got_max = max(hourly.values())
    for bound in ("Arr", "Dep", "Dep+Arr"):
        k = ("Clock_Total_ATMs", bound, "ATMs", "Max", "-", "2025")
        if k in tgt:
            gm = max((v for kk, v in hourly.items()), default=0) if bound == "Dep+Arr" else                  max((sum(1 for e in ev if e["dow"] == d and e["minute"] // 60 == h and e["ad"] == bound[0]) 
                      for d in range(1, 8) for h in range(24)), default=0)
            print(f"  busy hour ATMs {bound}: sent {tgt[k]:.0f} vs sample-week max {gm:.0f}")
    print(f"  carried-in proxy (overnight stock at week min): {sum(ovn0.values()):.0f} vs sent carried-in 10")
    return True

def rung4():
    """The ADAC 2024 hindcast: engine -> pack -> DDFS vs the sent deliverable
    (note 37 v2 item 5, John's acceptance test; ddfs_hindcast carries it)."""
    import ddfs_hindcast as hc
    print("RUNG 4 - ", end="")
    hc.adac_hindcast()
    return True

if __name__ == "__main__":
    rungs = {"1": rung1, "2": rung2, "3": rung3, "4": rung4}
    pick = None
    for a in sys.argv[1:]:
        if a == "--rung":
            pick = sys.argv[sys.argv.index(a) + 1]
    print("DDFS TEST LADDER -", dt.date.today().isoformat())
    for n, fn in rungs.items():
        if pick and n != pick:
            continue
        try:
            fn()
        except Exception as ex:
            print(f"  RUNG {n} FAILED: {type(ex).__name__}: {ex}")
        print()
