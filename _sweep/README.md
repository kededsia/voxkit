# Scratch: the 22 real plans this engine was extracted from

Not part of the package and not packaged (`setuptools` finds only `voxkit*`).

It is here because the gates were tuned against real plans, and a gate tuned
against a fixture proves only that the fixture matches the gate. Two numbers in
the top-level README come from this folder and nowhere else:

```
22 plans · free gates
fail by gate : compose 20 · readable 27 · schema 20 · marks 7 · data 3   (77)
warn by gate : arrival 106 · compose 71                                  (177)
clean        : m14, m15, m17
```

To reproduce:

```bash
python - <<'PY'
import collections, glob
from pathlib import Path
from voxkit.config import Project
from voxkit.contract import Plan
from voxkit.words import Narration
from voxkit.gates.base import Context, run, gate_set

root = Path("_sweep"); proj = Project(root=root)
free = [g.name for g in gate_set() if not g.needs_assets]
tally, warns, clean = collections.Counter(), collections.Counter(), []
for p in sorted(glob.glob("_sweep/plans/*.json")):
    mod = Path(p).stem
    tr = root / "audio" / f"{mod}.json"
    ctx = Context(project=proj, plan=Plan.load(Path(p)),
                  narration=Narration.from_file(tr) if tr.is_file() else None)
    res = run(ctx, gate_set(free), use_cache=False)
    if not res.findings("fail"): clean.append(mod)
    for f in res.findings("fail"): tally[f.gate] += 1
    for f in res.findings("warn"): warns[f.gate] += 1
print("fail:", dict(tally), sum(tally.values()))
print("warn:", dict(warns), sum(warns.values()))
print("clean:", clean)
PY
```
