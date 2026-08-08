# Attic

Working material kept because a deletion is a loss and a gitignored file is a file that exists on one
machine only. Committed here with a reason, so `git log --follow` still reads back to the original path.

| File | Reason |
|---|---|
| `ddfs_front_v0.html` | The 18 July v0 bridge front end, superseded by `ddfs_front_v1.html` and then by the unified `ddfs_live.html`. Served by no route and named in no whitelist. |
| `ddfs_cockpit.html` | The DDFS Cockpit of note 37 v2, folded into `ddfs_live.html` as its Forecast stage on 23 July (note 41). `/cockpit` now serves the unified page. Still named in the service `WHITELIST` constant, which enforces nothing; tidy that when the whitelist is either enforced or removed. |
| `ddfs_report_gen_v01.js` | Superseded by `ddfs_report_gen_v02.js` on 19 July. v02 stays in the root pending the decision on whether to wire it into the tool. |
| `zagreb_oracle_run_v01.tsv` | A superseded oracle run output held in the fixtures directory. The live pin is `zagreb_oracle_run_v02.tsv`. Moved out because fixtures should hold pins, not results. |

Nothing in this folder is imported, served or called by the running tool. Removed from the attic only
by a commit that says why.
