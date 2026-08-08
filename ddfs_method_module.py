"""
DDFS method module (WS7): computes, per candidate design-day method, the day
and hour the method selects from a full-year schedule, and emits the method
comparison table of note 31 (ADAC comparator style) so the engagement chooses
its method on evidence rather than habit.

Definitions follow note 31 v2, verified against Avia's IATA ADRM copy
(10th edition, effective March 2014): SBR family (20th/30th/40th busiest
hour); the 5% Busy Hour Rate (cumulative top-hour volumes to five percent of
annual volume, threshold adjustable); the IATA Busy Day (peak month, the
Monday-Sunday week closest to the month's average week, its second busiest
day, then the peak clock hour and the peak rolling-60 window, which may
straddle clock hours); FAA PMAD and PMAWD; the 90th-percentile day; peak day
and peak hour for reference only (the ADRM warns against planning to the
absolute peak); and per-OAG-season variants (summer starts the last Sunday
of March, winter the last Sunday of October).

Inputs: either a TSV of flight events (columns: date YYYY-MM-DD, time HH:MM,
ad A|D, optional pax) or a DuckDB store with a SQL returning the same columns
(--duckdb PATH --sql "..."). Basis is movements (ATM) natively; if a pax
column is supplied the ranking basis can be switched with --basis pax.
Conventions stated in the output rather than buried: hour ties break on
earlier date then hour; the 90th-percentile day is the ceil(0.10 x n)-th
busiest day; weeks are Monday-Sunday windows lying fully inside the month.

Selftest: an engineered synthetic year in which July carries a fat cluster
of high evening hours while 15 August is the single busiest day, so the 30th
busy hour falls in JULY while the peak day falls in AUGUST (John's example
made testable); every method's pick is pinned.

Author: Avia Solutions. python3 ddfs_method_module.py --selftest
"""
import csv, sys, datetime as dt
from collections import defaultdict


# ---------------- input adapters -------------------------------------------
def read_events_tsv(path):
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            d = dt.date.fromisoformat(r["date"])
            hh, mm = r["time"].split(":")[:2]
            out.append((d, int(hh), int(mm), r.get("ad", ""),
                        float(r["pax"]) if r.get("pax") else 0.0))
    return out


def read_events_duckdb(db_path, sql):
    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    out = []
    for row in con.execute(sql).fetchall():
        d, t = row[0], row[1]
        if isinstance(d, str):
            d = dt.date.fromisoformat(d)
        if isinstance(t, str):
            hh, mm = int(t[0:2]), int(t[3:5])
        else:
            hh, mm = t.hour, t.minute
        ad = row[2] if len(row) > 2 else ""
        pax = float(row[3]) if len(row) > 3 and row[3] is not None else 0.0
        out.append((d, hh, mm, ad, pax))
    con.close()
    return out


# ---------------- aggregation ----------------------------------------------
def hourly_series(events, basis="atm"):
    """{(date, hour): value} over every event; value = movements or pax."""
    h = defaultdict(float)
    for d, hh, mm, ad, pax in events:
        h[(d, hh)] += pax if basis == "pax" else 1.0
    return dict(h)


def daily_series(hourly):
    d = defaultdict(float)
    for (day, hh), v in hourly.items():
        d[day] += v
    return dict(d)


def rolling60(events, day, step=5, basis="atm"):
    """peak rolling 60-minute window of a given day, at `step`-minute steps."""
    mins = [(hh * 60 + mm, (pax if basis == "pax" else 1.0))
            for d, hh, mm, ad, pax in events if d == day]
    best = (0.0, 0)
    for s in range(0, 1441 - 60, step):
        v = sum(w for m, w in mins if s <= m < s + 60)
        if v > best[0]:
            best = (v, s)
    return {"value": best[0], "start": "%02d:%02d" % (best[1] // 60, best[1] % 60)}


def last_sunday(year, month):
    d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 \
        else dt.date(year, 12, 31)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def oag_season(day):
    s = last_sunday(day.year, 3)
    w = last_sunday(day.year, 10)
    return "S" if s <= day < w else "W"


# ---------------- methods ---------------------------------------------------
def sbr(hourly, rank):
    """rank-th busiest hour; ties break earlier date then hour (stated)."""
    ranked = sorted(hourly.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
    (day, hh), v = ranked[rank - 1]
    return {"date": day, "hour": hh, "value": v}


def bhr5(hourly, threshold=0.05):
    """ADRM 5% busy hour: descending cumulative to threshold of annual volume."""
    total = sum(hourly.values())
    ranked = sorted(hourly.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
    cum = 0.0
    for i, ((day, hh), v) in enumerate(ranked, 1):
        cum += v
        if cum >= threshold * total:
            return {"date": day, "hour": hh, "value": v, "hours_above": i,
                    "threshold": threshold}
    return {}


def peak_day(daily):
    day = max(sorted(daily), key=lambda d: daily[d])
    return {"date": day, "value": daily[day]}


def percentile_day(daily, pct=0.90):
    import math
    ranked = sorted(daily.items(), key=lambda kv: (-kv[1], kv[0]))
    k = math.ceil((1 - pct) * len(ranked))
    day, v = ranked[max(k - 1, 0)]
    return {"date": day, "value": v, "rank": k}


def peak_month(daily):
    m = defaultdict(float)
    for day, v in daily.items():
        m[(day.year, day.month)] += v
    return max(sorted(m), key=lambda k: m[k])


def iata_busy_day(hourly, daily, events, basis="atm"):
    """ADRM: peak month; Mon-Sun week fully inside the month closest to the
    month's average week; its SECOND busiest day; peak clock hour and peak
    rolling-60 window of that day."""
    y, mo = peak_month(daily)
    days = sorted(d for d in daily if d.year == y and d.month == mo)
    month_total = sum(daily[d] for d in days)
    avg_week = month_total / (len(days) / 7.0)
    weeks = []
    for d in days:
        if d.weekday() == 0 and d + dt.timedelta(days=6) <= days[-1]:
            wk = [d + dt.timedelta(days=i) for i in range(7)]
            weeks.append((wk, sum(daily.get(x, 0.0) for x in wk)))
    if not weeks:
        return {"note": "no complete Mon-Sun week inside the peak month"}
    wk, wtot = min(weeks, key=lambda w: abs(w[1] - avg_week))
    second = sorted(wk, key=lambda d: -daily.get(d, 0.0))[1]
    hours = {hh: v for (d, hh), v in hourly.items() if d == second}
    ph = max(sorted(hours), key=lambda h: hours[h])
    return {"peak_month": "%d-%02d" % (y, mo), "week_start": wk[0],
            "date": second, "hour": ph, "value": hours[ph],
            "rolling60": rolling60(events, second, basis=basis)}


def pmad(hourly, daily, weekdays_only=False):
    """FAA PMAD/PMAWD: peak month average-day profile; its peak hour."""
    y, mo = peak_month(daily)
    prof, ndays = defaultdict(float), set()
    for (d, hh), v in hourly.items():
        if d.year == y and d.month == mo and (not weekdays_only or d.weekday() < 5):
            prof[hh] += v
            ndays.add(d)
    n = max(len(ndays), 1)
    avg = {hh: v / n for hh, v in prof.items()}
    ph = max(sorted(avg), key=lambda h: avg[h])
    return {"peak_month": "%d-%02d" % (y, mo), "hour": ph,
            "value": round(avg[ph], 2), "days_averaged": n}


def season_slices(hourly, daily):
    out = {}
    for season in ("S", "W"):
        hs = {k: v for k, v in hourly.items() if oag_season(k[0]) == season}
        ds = {k: v for k, v in daily.items() if oag_season(k) == season}
        if not ds:
            continue
        out[season] = {"peak_day": peak_day(ds),
                       "sbr30": sbr(hs, 30) if len(hs) >= 30 else {}}
    return out


def method_table(events, basis="atm", source="unnamed source"):
    hourly = hourly_series(events, basis)
    daily = daily_series(hourly)
    res = {
        "peak_hour_absolute": sbr(hourly, 1),
        "sbr20": sbr(hourly, 20), "sbr30": sbr(hourly, 30),
        "sbr40": sbr(hourly, 40), "bhr5": bhr5(hourly),
        "iata_busy_day": iata_busy_day(hourly, daily, events, basis),
        "pmad": pmad(hourly, daily), "pmawd": pmad(hourly, daily, True),
        "peak_day": peak_day(daily), "p90_day": percentile_day(daily),
        "seasons": season_slices(hourly, daily),
        "basis": basis, "source": source,
        "annual_total": round(sum(daily.values()), 1),
        "days": len(daily),
    }
    return res


LABELS = [
    ("peak_hour_absolute", "Peak hour (reference only; ADRM: do not plan to it)"),
    ("sbr20", "20th busiest hour (Amsterdam convention)"),
    ("sbr30", "Standard Busy Rate, 30th busiest hour (BAA; ZAG convention)"),
    ("sbr40", "40th busiest hour (Paris convention)"),
    ("bhr5", "Busy Hour Rate, 5% busy hour (ADRM/Heathrow)"),
    ("iata_busy_day", "IATA Busy Day (2nd busiest day, average week, peak month)"),
    ("pmad", "FAA PMAD peak hour (peak month average day)"),
    ("pmawd", "FAA PMAWD peak hour (weekdays only)"),
    ("peak_day", "Peak day (reference only)"),
    ("p90_day", "90th-percentile day"),
]


def emit_table(res, out_path):
    def fmt(v):
        """house rule: float noise never reaches an output"""
        return round(v, 1) if isinstance(v, float) else v
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["Method", "Selected date", "Hour / window", "Value (%s)" % res["basis"], "Notes"])
        for key, label in LABELS:
            r = res.get(key, {})
            date = str(r.get("date", r.get("peak_month", "")))
            hour = ("%02d:00" % r["hour"]) if "hour" in r else ""
            if key == "iata_busy_day" and "rolling60" in r:
                hour += " (rolling60 %s = %s)" % (r["rolling60"]["start"], fmt(r["rolling60"]["value"]))
            notes = ""
            if key == "bhr5" and r:
                notes = "%d hours above; threshold %.0f%%" % (r["hours_above"], r["threshold"] * 100)
            if key == "p90_day" and r:
                notes = "rank %d of %d days" % (r["rank"], res["days"])
            if key in ("pmad", "pmawd") and r:
                notes = "average of %d days in %s" % (r["days_averaged"], r["peak_month"])
            w.writerow([label, date, hour, fmt(r.get("value", "")), notes])
        for season, s in res.get("seasons", {}).items():
            w.writerow(["Season %s peak day (OAG season)" % season,
                        s["peak_day"]["date"], "", fmt(s["peak_day"]["value"]), ""])
            if s.get("sbr30"):
                w.writerow(["Season %s 30th busy hour" % season, s["sbr30"]["date"],
                            "%02d:00" % s["sbr30"]["hour"], fmt(s["sbr30"]["value"]), ""])
        w.writerow(["Source", res["source"],
                    "", "", "basis %s; annual total %s over %d days"
                    % (res["basis"], res["annual_total"], res["days"])])


# ---------------- synthetic year and selftest -------------------------------
def synthetic_year(year=2015):
    """Deterministic full-year schedule, engineered so the hour ranking is
    provable by hand: base 4 movements in six daily banks (24/day, annual
    8,760 + boosts). July days 1-20 add 12 movements at 17:00, 18:00, 19:00
    (18:00 overlapping a base bank -> twenty hours at 16, forty at 12).
    15 August adds 6 movements across hours 07-21 plus a 20-movement spike
    at 12:00 (one hour at 30, the day totalling 134, the year's peak day).
    Hence: absolute peak hour 15 Aug (30); ranks 2-21 are July 18:00s (16);
    ranks 22-61 are July 17:00/19:00s (12), so the 30TH BUSY HOUR IS IN JULY
    while the PEAK DAY IS IN AUGUST; July is the peak month (1,464 vs 854)."""
    ev = []
    d = dt.date(year, 1, 1)
    while d.year == year:
        for hh in (6, 9, 12, 15, 18, 21):
            for i in range(4):
                ev.append((d, hh, (i * 7) % 60, "A" if i % 2 == 0 else "D", 0.0))
        if d.month == 7 and d.day <= 20:            # July evening cluster
            for hh in (17, 18, 19):
                for i in range(12):
                    ev.append((d, hh, (i * 5) % 60, "A" if i % 2 else "D", 0.0))
        if d.month == 8 and d.day == 15:            # the peak day with one spike
            for hh in range(7, 22):
                for i in range(6):
                    ev.append((d, hh, (i * 9) % 60, "A" if i % 2 else "D", 0.0))
            for i in range(20):
                ev.append((d, 12, (i * 3) % 60, "A" if i % 2 else "D", 0.0))
        d += dt.timedelta(days=1)
    return ev


def selftest():
    ev = synthetic_year()
    res = method_table(ev, source="synthetic_year(2015), engineered fixture")
    checks, fails = 0, []

    def ex(c, m):
        nonlocal checks
        checks += 1
        if not c:
            fails.append(m)

    ex(res["peak_day"]["date"] == dt.date(2015, 8, 15),
       "peak day should be 15 Aug, got %s" % res["peak_day"]["date"])
    ex(res["sbr30"]["date"].month == 7,
       "30th busy hour should fall in July, got %s" % res["sbr30"]["date"])
    ex(res["peak_hour_absolute"]["date"] == dt.date(2015, 8, 15),
       "absolute peak hour on 15 Aug")
    ex(res["sbr30"]["value"] == 12.0, "SBR30 value 12 (rank 30 in the July 17:00/19:00 band), got %s" % res["sbr30"]["value"])
    ex(res["sbr20"]["value"] == 16.0 and res["sbr20"]["date"].month == 7,
       "SBR20 value 16 in the July 18:00 band, got %s %s" % (res["sbr20"]["value"], res["sbr20"]["date"]))
    ex(res["peak_hour_absolute"]["value"] == 30.0 and res["peak_hour_absolute"]["hour"] == 12,
       "peak hour 30 at 12:00 (4 base + 6 spread + 20 spike), got %s" % res["peak_hour_absolute"]["value"])
    ex(res["peak_day"]["value"] == 134.0, "peak day total 134, got %s" % res["peak_day"]["value"])
    ex(res["pmad"]["hour"] == 18, "PMAD peak hour 18 (July average day), got %s" % res["pmad"]["hour"])
    ex(res["annual_total"] == 9590.0, "annual total 8760 + 720 + 110 = 9590, got %s" % res["annual_total"])
    ex(res["iata_busy_day"]["peak_month"] == "2015-07", "peak month July (boost of 20 days outweighs one big day)")
    ex(res["iata_busy_day"]["date"].month == 7, "IATA busy day in July")
    ex(res["iata_busy_day"]["hour"] in (17, 18, 19), "IATA busy day peak hour in the evening cluster")
    ex(res["pmad"]["peak_month"] == "2015-07" and res["pmad"]["hour"] in (17, 18, 19),
       "PMAD peak hour in the July evening cluster")
    ex(res["bhr5"]["value"] <= res["sbr30"]["value"],
       "5%% BHR rate at or below SBR30 (deeper into the ranking): %s vs %s"
       % (res["bhr5"]["value"], res["sbr30"]["value"]))
    ex(res["bhr5"]["hours_above"] > 30, "5% threshold reaches past rank 30")
    ex(res["p90_day"]["rank"] == 37, "90th percentile day = 37th busiest of 365")
    ex(res["seasons"]["S"]["peak_day"]["date"] == dt.date(2015, 8, 15), "summer season peak day 15 Aug")
    ex(res["seasons"]["W"]["peak_day"]["value"] < res["seasons"]["S"]["peak_day"]["value"],
       "winter peak below summer peak")
    ex(oag_season(dt.date(2015, 3, 29)) == "S" and oag_season(dt.date(2015, 3, 28)) == "W",
       "OAG summer starts last Sunday of March 2015 (29 Mar)")
    ex(oag_season(dt.date(2015, 10, 25)) == "W" and oag_season(dt.date(2015, 10, 24)) == "S",
       "OAG winter starts last Sunday of October 2015 (25 Oct)")
    # divergence, the point of the module: methods pick different dates
    dates = {str(res[k].get("date")) for k in ("sbr30", "peak_day", "iata_busy_day")}
    ex(len(dates) >= 2, "methods diverge across July/August as engineered")
    print("method module selftest: %d checks, %s"
          % (checks, "all pass" if not fails else "%d FAILURES %s" % (len(fails), fails)))
    return not fails


# ---------------- CLI -------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args or not args:
        sys.exit(0 if selftest() else 1)
    basis = args[args.index("--basis") + 1] if "--basis" in args else "atm"
    out = args[args.index("--out") + 1] if "--out" in args else "method_comparison.tsv"
    if "--tsv" in args:
        path = args[args.index("--tsv") + 1]
        ev, src = read_events_tsv(path), path
    elif "--duckdb" in args:
        db = args[args.index("--duckdb") + 1]
        sql = args[args.index("--sql") + 1]
        ev, src = read_events_duckdb(db, sql), "%s [%s]" % (db, sql[:80])
    else:
        print(__doc__)
        sys.exit(2)
    res = method_table(ev, basis=basis, source=src)
    emit_table(res, out)
    print("method comparison written to %s (%d events, %d days, basis %s)"
          % (out, len(ev), res["days"], basis))
