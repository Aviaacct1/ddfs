"""Avia DDFS - host check. Author: Avia Solutions.

Step 5 of provisioning, and it is not optional:

    1. git clone <remote> C:\\src\\ddfs
    2. copy the data root
    3. set AVIA_LOCAL_CACHE
    4. py -3.12 -m venv .venv
       .venv\\Scripts\\python -m pip install -r requirements.txt
    5. .venv\\Scripts\\python check_env.py

Exits non-zero when something required is missing or broken. It exists because
pip reports a broken install as a warning and exits zero, so "the install
worked" is not evidence that the tool runs. On Meridian this check caught a
numpy downgrade nobody had read in the resolver output.

It also reports what it cannot fail on: the interpreter version, whether this
is a shared Python, and the coverage of each store. A run that does not declare
which data produced it is a run whose numbers cannot be traced back.

Usage:
    python check_env.py            checks and smoke tests
    python check_env.py --quick    checks only, no store queries
"""
import sys
import os
import importlib

FAIL, WARN = [], []
PY_REQUIRED = (3, 12)


def ok(msg):
    print(f"  ok    {msg}")


def fail(msg):
    FAIL.append(msg)
    print(f"  FAIL  {msg}")


def warn(msg):
    WARN.append(msg)
    print(f"  warn  {msg}")


def check_interpreter():
    print("Interpreter")
    v = sys.version_info
    print(f"        {sys.version.split()[0]} at {sys.executable}")
    if (v.major, v.minor) == PY_REQUIRED:
        ok(f"Python {v.major}.{v.minor}, the pinned version")
    else:
        fail(f"Python {v.major}.{v.minor}: DDFS is pinned to "
             f"{PY_REQUIRED[0]}.{PY_REQUIRED[1]}. Both 3.10 and 3.12 have "
             f"compiled this tool in the past, which is how two hosts disagree.")

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        ok(f"virtual environment: {sys.prefix}")
    else:
        warn("virtualenv NO, this is a shared Python. Installing one tool's "
             "dependencies here changes every other tool that uses this "
             "interpreter. The workstation runs several tools; give DDFS its own.")


def check_packages():
    print("Packages")
    required = {"duckdb": "1.0", "openpyxl": "3.1"}
    for name, floor in required.items():
        try:
            m = importlib.import_module(name)
        except Exception as ex:
            fail(f"{name} does not import: {type(ex).__name__}: {ex}")
            continue
        got = getattr(m, "__version__", "unknown")
        if got == "unknown":
            warn(f"{name} imports but reports no version")
        elif _older(got, floor):
            fail(f"{name} {got} is below the floor of {floor}")
        else:
            ok(f"{name} {got}")


def _older(got, floor):
    def parts(s):
        out = []
        for p in s.split("."):
            digits = "".join(c for c in p if c.isdigit())
            out.append(int(digits) if digits else 0)
        return out
    g, f = parts(got), parts(floor)
    g += [0] * (len(f) - len(g))
    f += [0] * (len(g) - len(f))
    return g < f


def check_paths():
    print("Paths and stores")
    import config
    root = config.data_root()
    if root:
        ok(f"AVIA_LOCAL_CACHE = {root}")
    else:
        warn("AVIA_LOCAL_CACHE is not set. Stores are being found by landmark "
             "search or host candidate, which works here and will not work the "
             "same way on another host. Set it.")
    for name in config.STORES:
        hit = config.find(name)
        if hit:
            size = os.path.getsize(hit)
            ok(f"{name}  ({size:,} bytes)  {hit}")
        elif name == "2025 Towerlog.xlsx":
            warn(f"{name} not found. Towerlog reconciliation will be skipped, "
                 f"and the tool must say it skipped it.")
        else:
            fail(f"{name} not found. Paths tried:\n          "
                 + "\n          ".join(config.attempts(name)))


def check_repo_shape():
    print("Repository")
    here = os.path.dirname(os.path.abspath(__file__))
    for f in ("ddfs_service.py", "ddfs_live.html", "config.py",
              "requirements.txt", "ddfs_bridge_fixtures", "ddfs_packs"):
        p = os.path.join(here, f)
        (ok if os.path.exists(p) else fail)(f"{f} present" if os.path.exists(p)
                                            else f"{f} missing from the clone")
    strays = [f for f in ("oag.duckdb", "sabre.duckdb", "access_password.txt")
              if os.path.exists(os.path.join(here, f))]
    for s in strays:
        warn(f"{s} is inside the repo directory. Data and secrets live on the "
             f"data root, not beside the code. Check .gitignore held.")


def smoke():
    print("Smoke tests")
    import config
    import ddfs_aircraft as ac
    if len(ac.ICAO) >= 47 and ac.code_letter("320") == "C" and ac.code_letter("77W") == "E":
        ok(f"aircraft classification: {len(ac.ICAO)} types, one owner")
    else:
        fail("aircraft classification map is wrong")

    try:
        import ddfs_method_module  # noqa: F401
        import ddfs_oag_expand     # noqa: F401
        import ddfs_pack_emit      # noqa: F401
        import ddfs_bridge         # noqa: F401
        import ddfs_towerlog       # noqa: F401
        import ddfs_hindcast       # noqa: F401
        ok("all DDFS modules import")
    except Exception as ex:
        fail(f"module import: {type(ex).__name__}: {ex}")
        return

    bundle = config.find("avia_forecast_build/webapp/data/cockpit.json")
    if bundle:
        try:
            import ddfs_pack_emit as pe
            b = pe.load_bundle()
            ok(f"Atlas engine bundle loads, {len(b)} top-level keys")
        except Exception as ex:
            fail(f"Atlas engine bundle will not load: {type(ex).__name__}: {ex}")
    else:
        warn("Atlas engine bundle not found: the Forecast stage engine source "
             "will be unavailable. Packs and the oracle path still work.")

    store = config.find("oag.duckdb")
    if store:
        try:
            import duckdb
            con = duckdb.connect(store, read_only=True)
            n = con.execute("select count(*) from oag").fetchone()[0]
            yrs = con.execute("select min(year), max(year) from oag").fetchone()
            con.close()
            ok(f"OAG store opens: {n:,} rows, years {yrs[0]} to {yrs[1]}")
        except Exception as ex:
            fail(f"OAG store will not open: {type(ex).__name__}: {ex}")


def main():
    print("Avia DDFS host check\n")
    check_interpreter(); print()
    check_packages(); print()
    check_paths(); print()
    check_repo_shape(); print()
    if "--quick" not in sys.argv:
        smoke(); print()
    if FAIL:
        print(f"RESULT: {len(FAIL)} failure(s), {len(WARN)} warning(s). "
              f"This host will not run DDFS correctly.")
        for f in FAIL:
            print(f"  - {f.splitlines()[0]}")
        return 1
    print(f"RESULT: pass, {len(WARN)} warning(s).")
    for w in WARN:
        print(f"  - {w.splitlines()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
