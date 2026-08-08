"""Avia DDFS - the pack contract, and the Atlas bundle contract.

Author: Avia Solutions.

The pack is the interface between the two halves of DDFS. Every growth source
(the Avia Global Forecast engine, an engagement pack such as the Zagreb oracle,
a client-supplied forecast) emits a pack, and everything downstream reads the
pack rather than the source. That is what lets Atlas finish on its own schedule
without DDFS waiting for it.

An interface only holds if something checks it. Two contracts live here:

  PACK_SCHEMA    what a pack must carry for forecast_from_pack to read it
  BUNDLE_SCHEMA  what the Atlas cockpit.json bundle must carry for the emitter

Both refuse rather than default. The recurring fault in this estate is a
missing input substituting a neutral value in silence, so a pack that does not
meet the contract raises with a statement of exactly what is missing, and never
returns a partial answer.

Established 8 August 2026, when checking the two packs held in ddfs_packs/
showed they do not in fact share a grain: the emitted pack carries
series.pax_total and the Zagreb engagement pack does not, so
forecast_from_pack raised KeyError('pax_total') on the engagement pack. See
docs/SWITCH_REGISTER.md.
"""

PACK_SCHEMA = "avia-ddfs-pack/1"
BUNDLE_SCHEMA = "atlas-cockpit/1"


class ContractError(ValueError):
    """A pack or bundle that does not meet its contract. Never caught and
    turned into a default: the caller stops."""


# ---------------------------------------------------------------- the pack --

# Fields every pack carries, whatever produced it.
PACK_CORE = ("pack_id", "airport", "base_year", "spot_years", "series", "dd_block")

# Series that forecast_from_pack reads. A pack missing either cannot be
# forecast from, whatever else it holds.
PACK_SERIES = ("pax_total", "scheduled_movements")

# Read by the forecast but tolerated when absent, with the default stated.
PACK_OPTIONAL = {"flags": [], "vintage": "not stated", "note": ""}


def validate_pack(pack):
    """Every problem with `pack`, as a list of sentences. Empty list means it
    meets the contract. Returns rather than raises so a caller can report all
    of them at once instead of the first."""
    problems = []
    if not isinstance(pack, dict):
        return [f"pack is {type(pack).__name__}, expected a dict"]

    schema = pack.get("schema")
    if schema and schema != PACK_SCHEMA:
        problems.append(
            f"pack schema is {schema!r}, this build reads {PACK_SCHEMA!r}")

    for f in PACK_CORE:
        if f not in pack:
            problems.append(f"missing core field {f!r}")

    series = pack.get("series")
    if not isinstance(series, dict):
        problems.append("series missing or not a dict")
    else:
        for s in PACK_SERIES:
            if s not in series:
                problems.append(
                    f"series.{s} missing. Held instead: "
                    f"{', '.join(sorted(series)) or 'nothing'}")
            elif not isinstance(series[s], dict) or "values" not in series[s]:
                problems.append(f"series.{s} has no values block")

    sy = pack.get("spot_years")
    if sy is not None and not isinstance(sy, (list, tuple)):
        problems.append(f"spot_years is {type(sy).__name__}, expected a list")

    by = pack.get("base_year")
    if by is not None and not isinstance(by, int):
        problems.append(f"base_year is {type(by).__name__}, expected int")

    return problems


def require_pack(pack, what="pack"):
    """Return the pack, or raise ContractError naming everything wrong with it.

    Call this at the top of anything that reads a pack. The alternative is what
    the code did until 8 August 2026: KeyError('pax_total') from inside the
    forecast, which says nothing about which pack, from which source, or what
    else was missing."""
    problems = validate_pack(pack)
    if problems:
        pid = pack.get("pack_id", "unidentified") if isinstance(pack, dict) else "unreadable"
        raise ContractError(
            f"{what} {pid!r} does not meet {PACK_SCHEMA}:\n  - "
            + "\n  - ".join(problems)
            + "\n\nEvery growth source must emit the same pack grain. A pack "
              "that does not is not forecast from with defaults substituted."
        )
    return pack


def stamp(pack):
    """Put the schema on a pack at emit. Packs written before 8 August 2026
    carry no schema; validate_pack accepts an absent schema and rejects a
    wrong one, so old packs keep working and a future change is caught."""
    pack["schema"] = PACK_SCHEMA
    pack["bundle_contract"] = BUNDLE_SCHEMA
    return pack


# ------------------------------------------------------------- the bundle --

# Atlas writes webapp/data/cockpit.json. DDFS reads it and never writes it.
BUNDLE_TOP = ("years", "base", "horizon", "airports")

# Fields the emitter reads from an airport record.
BUNDLE_AIRPORT = ("c", "n", "cty", "base", "g", "dom", "series")


def validate_bundle(bundle):
    """Every problem with the Atlas engine bundle, as a list of sentences."""
    problems = []
    if not isinstance(bundle, dict):
        return [f"bundle is {type(bundle).__name__}, expected a dict"]

    for f in BUNDLE_TOP:
        if f not in bundle:
            problems.append(f"missing top-level {f!r}. Held: "
                            f"{', '.join(sorted(bundle)) or 'nothing'}")

    aps = bundle.get("airports")
    if not isinstance(aps, list) or not aps:
        problems.append("airports missing, not a list, or empty")
    else:
        missing = [f for f in BUNDLE_AIRPORT if f not in aps[0]]
        if missing:
            problems.append(
                f"airport record is missing {', '.join(missing)}. "
                f"First record holds: {', '.join(sorted(aps[0]))}")
        s = aps[0].get("series")
        if s is not None and not isinstance(s, dict):
            problems.append("airport series is not a dict of scenario to path")

    yrs = bundle.get("years")
    if yrs is not None and (not isinstance(yrs, list) or not yrs):
        problems.append("years missing or empty")

    return problems


def require_bundle(bundle, path=None):
    """Return the bundle, or raise ContractError naming what changed.

    This is the check that lets Atlas finish independently. When Atlas changes
    the shape of cockpit.json, DDFS stops here and says so, rather than
    emitting a pack built on a field that has quietly moved."""
    problems = validate_bundle(bundle)
    if problems:
        raise ContractError(
            f"Atlas engine bundle{' at ' + path if path else ''} does not meet "
            f"{BUNDLE_SCHEMA}:\n  - " + "\n  - ".join(problems)
            + "\n\nThe bundle is read-only to DDFS. If Atlas has changed shape "
              "deliberately, update ddfs_pack_contract.BUNDLE_* and the fixture "
              "in ddfs_bridge_fixtures/cockpit_fixture.json together, in one "
              "commit, so the contract and the test move as a pair."
        )
    return bundle


def selftest():
    checks = []

    good = {"pack_id": "X_Baseline_2025", "airport": "ZAG", "base_year": 2025,
            "spot_years": [2030], "dd_block": {},
            "series": {"pax_total": {"values": {"2025": 1}},
                       "scheduled_movements": {"values": {"2025": 1}}}}
    checks.append(("valid pack passes", validate_pack(good), []))
    checks.append(("stamped pack carries the schema",
                   stamp(dict(good))["schema"], PACK_SCHEMA))

    no_pax = {k: v for k, v in good.items()}
    no_pax["series"] = {"scheduled_movements": {"values": {}},
                        "dep_pax_schengen": {"values": {}}}
    probs = validate_pack(no_pax)
    checks.append(("pack without pax_total is rejected", len(probs), 1))
    checks.append(("rejection names what was held instead",
                   "dep_pax_schengen" in probs[0], True))

    wrong_schema = dict(good, schema="avia-ddfs-pack/2")
    checks.append(("unknown schema is rejected", len(validate_pack(wrong_schema)), 1))

    raised = False
    try:
        require_pack(no_pax, "engagement pack")
    except ContractError as ex:
        raised = "pax_total" in str(ex) and "engagement pack" in str(ex)
    checks.append(("require_pack raises with the detail", raised, True))

    bundle = {"years": [2025], "base": 2025, "horizon": 2060,
              "airports": [{"c": "ZAG", "n": "Zagreb", "cty": "Croatia",
                            "base": 4.3, "g": 0.03, "dom": 0.0,
                            "series": {"Baseline": [0.03]}}]}
    checks.append(("valid bundle passes", validate_bundle(bundle), []))
    short = {"years": [2025], "base": 2025, "horizon": 2060,
             "airports": [{"c": "ZAG", "n": "Zagreb"}]}
    probs = validate_bundle(short)
    checks.append(("bundle with a changed airport record is rejected",
                   len(probs), 1))
    checks.append(("bundle rejection names the missing fields",
                   "cty" in probs[0], True))
    checks.append(("bundle without airports is rejected",
                   len(validate_bundle({"years": [1], "base": 1, "horizon": 2})), 2))

    fails = [c for c in checks if c[1] != c[2]]
    for c in checks:
        print(("ok  " if c[1] == c[2] else "FAIL"), c[0], c[1], "expected", c[2])
    print(f"pack contract selftest: {len(checks)} checks, "
          + ("all pass" if not fails else f"{len(fails)} FAILURES"))
    return not fails


if __name__ == "__main__":
    import sys
    sys.exit(0 if selftest() else 1)
