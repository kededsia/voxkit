"""Measure the film, rather than judge it.

Every gate in `voxkit.gates` answers a yes/no question and stops. That is the
right shape for a gate — it has to be able to fail the build — but it is the
wrong shape for the question "did it actually get better?". The client asked for
a camera that moves; the gate said the shot moved *somewhere* and passed while
43 % of the frames sat perfectly still. The number that would have caught it was
not a verdict, it was a distribution.

So: this module computes the numbers, and prints them. It changes nothing and
fails nothing. It reads the *same* program the renderer reads (`program_of`), so
a figure here cannot drift from what is on screen.

    vox camera m03            per shot, and the module total
    vox camera --all          every module that can be built

The two numbers worth knowing:

    dead       the longest run of frames whose camera does not change by 1 %.
               A hold has to creep; this is how long it forgot to.

    reach      the range of the pan, and the spread of the zoom. A shot can move
               and still look like a photograph if the move is the same 2 %
               everywhere — so this is reported per axis, not as a total.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .emit import camera as cam
from .gates.program import DEAD_AIR, DEAD_STILL, _busy, program_of

#: A window this long with no change is what a viewer calls "frozen".
WINDOW = 30


@dataclass(frozen=True)
class Shot:
    """What one shot's camera actually does, frame by frame."""

    id: str
    frames: int
    keys: int
    zoom_min: float
    zoom_med: float
    zoom_max: float
    pan_x: float
    pan_y: float
    dead: int          # longest still run, in frames
    dead_at: int       # where it starts
    dead_busy: bool    # was the page moving while the camera held?
    frozen: int        # keys that sit exactly at zoom 1.000

    @property
    def allowed(self) -> int:
        """How long a still run this shot may have, by the gate's own rule."""
        return DEAD_AIR * (2 if self.dead_busy else 1)

    @property
    def moving(self) -> bool:
        """Did this shot change the frame at all, by the gate's own definition?"""
        return self.zoom_max - self.zoom_min >= 0.05 or max(self.pan_x, self.pan_y) >= 0.08

    @property
    def alive(self) -> bool:
        """Is it moving *and* never frozen long enough to notice?"""
        return self.moving and self.dead < self.allowed

    def line(self) -> str:
        mark = "ok  " if self.alive else "DEAD"
        why = " busy" if self.dead_busy and self.dead >= DEAD_AIR else ""
        return (f"  {mark} {self.id}  {self.frames:>4}f  keys {self.keys:>3}  "
                f"zoom {self.zoom_min:.2f}/{self.zoom_med:.2f}/{self.zoom_max:.2f}  "
                f"pan {self.pan_x:.2f},{self.pan_y:.2f}  "
                f"still {self.dead:>3}f@{self.dead_at:<4} "
                f"({self.dead / 30:.1f}s){why}")


def measure(program) -> list[Shot]:
    """Every shot in the program, measured. Pure: no files, no clock."""
    out: list[Shot] = []
    for shot in program.shots:
        if shot.span <= 0:
            continue
        frames = [cam.resolve(shot.camera, f) for f in range(shot.span)]
        zs = [c[2] for c in frames]
        xs = [c[0] for c in frames]
        ys = [c[1] for c in frames]

        dead, dead_at = 0, 0
        for f in range(0, max(1, len(frames) - WINDOW)):
            base = frames[f]
            # The excursion, not the difference between the ends — the same
            # measure the gate uses, so the report and the verdict agree.
            far = max(max(abs(c[0] - base[0]), abs(c[1] - base[1]),
                          abs(c[2] - base[2])) for c in frames[f:f + WINDOW + 1])
            if far >= DEAD_STILL:
                continue
            run = WINDOW
            while f + run < len(frames):
                c = frames[f + run]
                if max(abs(c[0] - base[0]), abs(c[1] - base[1]),
                       abs(c[2] - base[2])) >= DEAD_STILL:
                    break
                run += 1
            if run > dead:
                dead, dead_at = run, f

        out.append(Shot(
            id=shot.id, frames=shot.span, keys=len(shot.camera),
            zoom_min=round(min(zs), 3), zoom_med=round(statistics.median(zs), 3),
            zoom_max=round(max(zs), 3),
            pan_x=round(max(xs) - min(xs), 3), pan_y=round(max(ys) - min(ys), 3),
            dead=dead, dead_at=dead_at,
            dead_busy=_busy(shot, dead_at, dead_at + dead),
            frozen=sum(1 for k in shot.camera if abs(k.zoom - 1.0) < 1e-6),
        ))
    return out


def report(shots: list[Shot]) -> str:
    """The table, plus the one line that says whether the film moves."""
    if not shots:
        return "  (no shots)"
    frames = sum(s.frames for s in shots)
    # The worst *single* run, not the sum of per-shot worsts — a total adds runs
    # that never happen at the same time and reads as a bigger fault than the
    # film has.
    worst = max(s.dead for s in shots)
    alive = sum(1 for s in shots if s.alive)
    lines = [s.line() for s in shots]
    lines.append("")
    lines.append(
        f"  {alive}/{len(shots)} shots alive  ·  {frames} frames  ·  "
        f"worst still {worst}f ({worst / 30:.1f}s)  ·  "
        f"zoom medians {sorted({round(s.zoom_med, 2) for s in shots})}")
    return "\n".join(lines)


def camera(ctx) -> tuple[int, str]:
    """The CLI body: build the program, measure it, print it."""
    program = program_of(ctx)
    shots = measure(program)
    return (0 if all(s.alive for s in shots) else 1), report(shots)
