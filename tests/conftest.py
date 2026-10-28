import sys
from pathlib import Path

# Windows-safe bootstrap for running the test-suite against the in-repo
# source tree without an editable install (the engine is consumed from
# source via `src/` on this box). No-op when the package is importable.
try:
    import ptcg  # noqa: F401
except ModuleNotFoundError:
    src = Path(__file__).resolve().parent.parent / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))
