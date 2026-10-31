"""voxkit — an agnostic documentary-collage engine.

The film is one mp4. Everything between the narration and that file is a chain
of contracts, and each contract has exactly one implementation:

    plan      a typed plan, validated before a single image is paid for
    words     the narration's own timings, so nothing is placed by eye
    assets    still -> pieces -> plate -> puppet, each measured not typed
    gates     findings as data, run in one process, cached on their inputs
    program   the shot's choreography computed as data, emitted as a thin template

Nothing here knows a module id, a film length or an account name. Those live in
`vox.toml` and in the plan.
"""

from .config import Project, discover, load
from .geometry import Rect, Placed, buried, covered_share, head_band, head_top, stack

__all__ = [
    "Project",
    "discover",
    "load",
    "Rect",
    "Placed",
    "stack",
    "buried",
    "head_band",
    "head_top",
    "covered_share",
]

__version__ = "1.0.0"
