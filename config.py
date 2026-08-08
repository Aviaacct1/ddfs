"""Avia DDFS - one resolver for every path the tool reads. Author: Avia Solutions.

Provisioning a host changes one environment variable and no code:

    AVIA_LOCAL_CACHE = the data root holding oag.duckdb, sabre.duckdb and the
                       client workbooks. E:\\Avia on the workstation.

Nothing in this repo may open a store by a literal path. A hardcoded path breaks
the tool silently on the next host, and DDFS carried three of them until
8 August 2026: two branches globbing a Claude session mount and falling back to
C:\\Avia, neither of which is right on the workstation.

Resolution order for any named file, first hit wins:

  1. its own environment variable, where one exists
     (AVIA_OAG_DB, AVIA_SABRE_DB, AVIA_ENGINE_BUNDLE, AVIA_TOWERLOG)
  2. AVIA_LOCAL_CACHE
  3. landmark search: walk up from this file and from the working directory
     looking for a directory that actually contains the file
  4. documented host candidates, development only, reported when used
  5. no hit: attempts() returns every path tried, and require() raises with
     the list in the message

Rule from the Meridian migration: find paths by landmark, never by counting
folders, and report the paths tried when nothing is found. A resolver that
returns a default in silence is how a missing input becomes a wrong number.
"""
import os
import glob

# The files DDFS reads from the data root, and the environment variable that
# overrides each. Adding a store means adding a line here and nowhere else.
STORES = {
    "oag.duckdb":         "AVIA_OAG_DB",
    "sabre.duckdb":       "AVIA_SABRE_DB",
    "2025 Towerlog.xlsx": "AVIA_TOWERLOG",
    "avia_forecast_build/webapp/data/cockpit.json": "AVIA_ENGINE_BUNDLE",
}

# Where a host has historically kept the data root. Used only after the
# environment variable and the landmark search have both missed, and the
# choice is always reported so it never passes unnoticed.
_HOST_CANDIDATES = (
    r"E:\Avia",          # workstation data root
    r"C:\Avia",          # Dev PC
)

_MAX_WALK_UP = 5


def data_root():
    """The configured data root, or None. Never guesses."""
    r = os.environ.get("AVIA_LOCAL_CACHE")
    return r.rstrip("\\/") if r else None


def _norm(root, name):
    return os.path.join(root, *name.split("/"))


def _walk_up_candidates(name):
    """Directories to try, walking up from this file and from the working
    directory. Landmark search: a directory qualifies because it holds the
    file, not because it is N levels above something."""
    seen, out = set(), []
    for start in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        d = start
        for _ in range(_MAX_WALK_UP):
            for cand in (d, os.path.join(d, "Avia"), os.path.join(d, "data")):
                p = _norm(cand, name)
                if p not in seen:
                    seen.add(p)
                    out.append(p)
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return out


def _session_mounts(name):
    """Cowork session mounts, development only. Generic: any mounted folder
    that actually holds the file qualifies, rather than assuming the folder
    is called C:--Avia as the pre-8-August code did."""
    out = []
    for mount in sorted(glob.glob("/sessions/*/mnt/*")):
        out.append(_norm(mount, name))
    return out


def attempts(name):
    """Every path that would be tried for `name`, in order. The message a
    failure prints, and what check_env.py reports."""
    tried = []
    env = STORES.get(name)
    if env and os.environ.get(env):
        tried.append(os.environ[env])
    root = data_root()
    if root:
        tried.append(_norm(root, name))
    tried += _walk_up_candidates(name)
    tried += [_norm(h, name) for h in _HOST_CANDIDATES]
    tried += _session_mounts(name)
    # de-duplicate, keep order
    seen, out = set(), []
    for p in tried:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def find(name):
    """First readable hit, or None. Does not raise, so a module can be
    imported on a host where the stores are not present."""
    for p in attempts(name):
        try:
            if os.path.isfile(p) and os.access(p, os.R_OK):
                return p
        except OSError:
            continue
    return None


def store_path(name):
    """The path to use for `name`. Returns the resolved file when one exists;
    otherwise the configured location, so an error message names the place the
    file was expected rather than the last thing tried."""
    hit = find(name)
    if hit:
        return hit
    root = data_root()
    if root:
        return _norm(root, name)
    return _norm(_HOST_CANDIDATES[0], name)


def require(name, what=None):
    """Resolve or fail loudly, listing every path tried. Use this at the point
    of opening a store, so a missing input stops the run instead of becoming a
    neutral default in the output."""
    hit = find(name)
    if hit:
        return hit
    lines = "\n  ".join(attempts(name))
    raise FileNotFoundError(
        f"{what or name} not found.\n"
        f"AVIA_LOCAL_CACHE is {data_root() or 'not set'}.\n"
        f"Paths tried, in order:\n  {lines}"
    )


def describe():
    """One block for check_env.py and for the run header, so any number the
    tool produces can be traced to the data it was produced from."""
    out = [f"AVIA_LOCAL_CACHE = {data_root() or '(not set)'}"]
    for name, env in STORES.items():
        hit = find(name)
        src = "not found"
        if hit:
            if os.environ.get(env) and os.path.abspath(os.environ[env]) == os.path.abspath(hit):
                src = f"{env}"
            elif data_root() and hit.startswith(data_root()):
                src = "AVIA_LOCAL_CACHE"
            else:
                src = "landmark or host candidate"
        out.append(f"  {name:48s} {src:26s} {hit or ''}")
    return "\n".join(out)


if __name__ == "__main__":
    print(describe())
