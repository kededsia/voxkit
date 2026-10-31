"""Gates, in the order a film is built.

A gate that reads no generated file is *free*: it runs the moment a plan and a
transcript exist, and `vox plan` runs all of them. The rest need artifacts and
say so (`N/A`) rather than passing silently — a render refuses an incomplete
run, because a gate that declined to look has verified nothing.

One process, findings as data, cached on the exact files each gate declared.
"""
from .base import (
    Cache, Context, Gate, GateResult, RunResult, Skipped, digest, gate_set,
    plan_key, run,
)

__all__ = ["Cache", "Context", "Gate", "GateResult", "RunResult", "Skipped",
           "digest", "gate_set", "plan_key", "run"]
