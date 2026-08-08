"""
OAG store expansion and Sabre pax weighting for the DDFS method module (WS7).

Turns the C:/Avia/oag.duckdb schedule-period rows into daily flight events for
one airport and year, and optionally weights each event with passengers so the
method module can rank hours on a pax basis as well as ATM.

CONVENTIONS, stated not buried (state file update SEVENTY-TWO):
- Monthly snapshot files are authoritative for their own month; the old
  weekly test files (name contains 'wc ') are excluded; half-year and annual
  files are admitted only for flight-dates the monthly family does not cover.
- Duplicates collapse at event grain (carrier, flight number, date,
  direction, time); the store's dup_marker is not a codeshare flag and is
  not used.
- J services only (scheduled passenger); C and G excluded, a stated scope.
- Arrival dates carry the local_arr_day offset; times are local throughout.
- days_of_op positions 1-7 are Monday-Sunday, blank meaning no operation.

PAX WEIGHTING (working assumption, stated in every output): route-direction
load factors from Sabre MIDT annual O&D (sabre.duckdb): departing legs from
itineraries originating at the airport (first stop = the other airport),
arriving legs from itineraries terminating at the airport (last stop = the
other airport); connections OVER the airport are excluded (small at non-hub
airports; revisit for hubs). LF = MIDT pax / scheduled seats per route,
direction and year; routes with LF outside [0.2, 1.05] or missing fall back
to the airport-wide LF, and the count of such routes is reported. Event pax
= event seats x route LF. MIDT undercounts direct-channel sales; the basis
is therefore indicative weighting for hour ranking, not a traffic estimate.

Author: Avia Solutions.
Usage: python3 ddfs_oag_expand.py --airport ZAG --year 2015 \
         [--pax] [--oag PATH] [--sabre PATH] [--out events.tsv]
Then: python3 ddfs_method_module.py --tsv events.tsv [--basis pax]
Or import: events = expand(...); res = ddfs_method_module.method_table(...)
"""
import csv, re, sys, datetime as dt

import config
from collections import defaultdict

def _store_path(name):
    """Resolve a store through the one resolver. Kept as a name because other
    modules import it; the resolution itself lives in config.py, so
    provisioning a host sets AVIA_LOCAL_CACHE and changes no code."""
    return config.store_path(name)


def _require_store(name, what=None):
    """Resolve or stop, listing every path tried. Use at the point of opening
    a store so a missing store cannot become a neutral default downstream."""
    return config.require(name, what)


OAG_DEFAULT = _store_path("oag.duckdb")
SABRE_DEFAULT = _store_path("sabre.duckdb")
MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _file_month(source_file):
    m = re.search(r"([A-Z][a-z]{2}) (\d{4})", source_file)
    return MONTHS.get(m.group(1)) if m else None


def _hm(t):
    try:
        v = int(t)
    except (TypeError, ValueError):
        return None
    return (v // 100) % 24, v % 100


def expand_rows(rows, airport, year):
    """rows: (dep, arr, carrier, fn, t_dep, t_arr, arr_day, days_of_op,
    eff_from, eff_to, seats, source_file). Returns event dict keyed at event
    grain -> (hh, mm, seats, other_airport). Monthly files authoritative."""
    monthly, other, monthly_keys = {}, {}, set()
    y0, y1 = dt.date(year, 1, 1), dt.date(year, 12, 31)
    for dep, arr, cx, fn, tdep, tarr, aday, dow, f0, f1, seats, sf in rows:
        fm = _file_month(sf)
        try:
            seats_n = int(seats)
        except (TypeError, ValueError):
            seats_n = 0
        d = max(f0, y0)
        end = min(f1, y1)
        while d <= end:
            i = d.isoweekday()
            if len(dow) >= i and dow[i - 1] not in (" ", ""):
                if fm is None or d.month == fm:
                    tgt = monthly if fm else other
                    if dep == airport:
                        hm = _hm(tdep)
                        if hm:
                            tgt[(cx, fn, d, "D")] = (hm[0], hm[1], seats_n, arr)
                            if fm:
                                monthly_keys.add((cx, fn, d, "D"))
                    if arr == airport:
                        try:
                            off = int(aday)
                        except (TypeError, ValueError):
                            off = 0
                        d2 = d + dt.timedelta(days=off)
                        hm = _hm(tarr)
                        if hm and d2.year == year:
                            tgt[(cx, fn, d2, "A")] = (hm[0], hm[1], seats_n, dep)
                            if fm:
                                monthly_keys.add((cx, fn, d2, "A"))
            d += dt.timedelta(days=1)
    for k, v in other.items():
        if k not in monthly_keys:
            monthly[k] = v
    return monthly


def load_oag(airport, year, oag_path=OAG_DEFAULT):
    import duckdb
    con = duckdb.connect(oag_path, read_only=True)
    rows = con.execute(
        """select dep_airport, arr_airport, carrier, flight_no, local_dep_time,
                  local_arr_time, local_arr_day, days_of_op,
                  cast(eff_from as date), cast(eff_to as date), seats, source_file
           from oag where (dep_airport=? or arr_airport=?) and year=?
             and service_type='J' and source_file not like '%wc %'""",
        [airport, airport, year]).fetchall()
    con.close()
    return expand_rows(rows, airport, year)


def sabre_route_pax(airport, year, sabre_path=SABRE_DEFAULT):
    """{('D', other): pax, ('A', other): pax} per the stated leg approximation."""
    import duckdb
    con = duckdb.connect(sabre_path, read_only=True)
    out_rows = con.execute(
        """select coalesce(connecting_airport1, destination_airport) as other,
                  sum(passengers) from sabre
           where year=? and origin_airport=? group by 1""", [year, airport]).fetchall()
    in_rows = con.execute(
        """select coalesce(connecting_airport3, connecting_airport2,
                           connecting_airport1, origin_airport) as other,
                  sum(passengers) from sabre
           where year=? and destination_airport=? group by 1""", [year, airport]).fetchall()
    con.close()
    return ({r[0]: r[1] for r in out_rows}, {r[0]: r[1] for r in in_rows})


def weight_events(events, airport, year, sabre_path=SABRE_DEFAULT,
                  lf_lo=0.2, lf_hi=1.05):
    """attach pax = seats x route LF; fallback airport LF outside bounds."""
    pax_out, pax_in = sabre_route_pax(airport, year, sabre_path)
    seats_route = defaultdict(float)
    for (cx, fn, d, ad), (hh, mm, seats, other) in events.items():
        seats_route[(ad, other)] += seats
    tot_seats = sum(seats_route.values())
    tot_pax = sum(pax_out.values()) + sum(pax_in.values())
    lf_airport = (tot_pax / tot_seats) if tot_seats else 0.7
    lf, fallbacks = {}, 0
    for (ad, other), s in seats_route.items():
        p = (pax_out if ad == "D" else pax_in).get(other)
        r = (p / s) if (p and s) else None
        if r is None or not (lf_lo <= r <= lf_hi):
            lf[(ad, other)] = lf_airport
            fallbacks += 1
        else:
            lf[(ad, other)] = r
    weighted = []
    for (cx, fn, d, ad), (hh, mm, seats, other) in events.items():
        weighted.append((d, hh, mm, ad, seats * lf[(ad, other)]))
    return weighted, {"airport_lf": round(lf_airport, 3),
                      "routes": len(seats_route), "fallback_routes": fallbacks}


def to_module_events(events):
    return [(d, hh, mm, ad, 0.0)
            for (cx, fn, d, ad), (hh, mm, seats, other) in events.items()]


def write_tsv(evts, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["date", "time", "ad", "pax"])
        for d, hh, mm, ad, pax in sorted(evts):
            w.writerow([d.isoformat(), "%02d:%02d" % (hh, mm), ad, round(pax, 2)])


# ---------------- selftests --------------------------------------------------
def selftest():
    """Offline: the expansion conventions on fabricated rows."""
    f = dt.date
    rows = [
        # monthly file, Tue/Thu, spans two months: only July dates from Jul file
        ("ZAG", "FRA", "LH", "1", "0900", "1100", "0", " 2 4   ",
         f(2015, 6, 20), f(2015, 8, 10), "180", "Europe Jul 2015.xlsx"),
        # same flight in the Aug file: its August dates
        ("ZAG", "FRA", "LH", "1", "0900", "1100", "0", " 2 4   ",
         f(2015, 6, 20), f(2015, 8, 10), "180", "Europe Aug 2015.xlsx"),
        # half-year file duplicate of the July flight: must NOT add events
        ("ZAG", "FRA", "LH", "1", "0905", "1105", "0", " 2 4   ",
         f(2015, 7, 1), f(2015, 7, 31), "180", "Middle East H2 2015.xlsx"),
        # half-year-only flight (no monthly coverage): kept
        ("DOH", "ZAG", "QR", "9", "0100", "0600", "1", "1      ",
         f(2015, 7, 6), f(2015, 7, 6), "300", "Middle East H2 2015.xlsx"),
        # wc files are excluded upstream in load_oag, not tested here
    ]
    ev = expand_rows(rows, "ZAG", 2015)
    checks, fails = 0, []

    def ex(c, m):
        nonlocal checks
        checks += 1
        if not c:
            fails.append(m)
    deps = [k for k in ev if k[3] == "D"]
    julys = [k for k in deps if k[2].month == 7]
    augs = [k for k in deps if k[2].month == 8]
    ex(len(julys) == 9, "July Tue/Thu departures from the Jul file: 9, got %d" % len(julys))
    ex(len(augs) == 2, "August departures from the Aug file (4 and 6 Aug, the only Tue/Thu in 1-10 Aug 2015): 2, got %d" % len(augs))
    ex(all(ev[k][0] == 9 and ev[k][1] == 0 for k in julys),
       "monthly file's 09:00 wins over the half-year 09:05 variant")
    arrs = [k for k in ev if k[3] == "A"]
    ex(len(arrs) == 1 and arrs[0][2] == f(2015, 7, 7),
       "overnight arrival lands 7 Jul (Mon dep + 1 day offset)")
    ex(ev[arrs[0]][3] == "DOH", "arrival carries the other airport")
    print("oag expansion selftest: %d checks, %s"
          % (checks, "all pass" if not fails else "%d FAILURES %s" % (len(fails), fails)))
    return not fails


def selftest_live():
    """Against the live store: the validated ZAG anchors (store-dependent
    pins; re-pin if the 2015/2016 loads are ever rebuilt)."""
    ev = load_oag("ZAG", 2015)
    n = len(ev)
    jul14 = sum(1 for (cx, fn, d, ad) in ev
                if ad == "D" and d == dt.date(2015, 7, 14))
    ok = (n == 27014 and jul14 == 41)
    print("oag live selftest: events %d (pin 27014), 14 Jul departures %d (pin 41): %s"
          % (n, jul14, "Ok" if ok else "MISMATCH"))
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(0 if selftest() else 1)
    if "--selftest-live" in a:
        sys.exit(0 if (selftest() and selftest_live()) else 1)
    airport = a[a.index("--airport") + 1]
    year = int(a[a.index("--year") + 1])
    oag = a[a.index("--oag") + 1] if "--oag" in a else OAG_DEFAULT
    out = a[a.index("--out") + 1] if "--out" in a else "events_%s_%d.tsv" % (airport, year)
    events = load_oag(airport, year, oag)
    if "--pax" in a:
        sabre = a[a.index("--sabre") + 1] if "--sabre" in a else SABRE_DEFAULT
        evts, meta = weight_events(events, airport, year, sabre)
        print("pax weighting: airport LF %(airport_lf)s over %(routes)d "
              "route-directions, %(fallback_routes)d on fallback" % meta)
    else:
        evts = to_module_events(events)
    write_tsv(evts, out)
    print("wrote %s: %d events" % (out, len(evts)))
