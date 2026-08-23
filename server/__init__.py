# Lane D. Modules use flat imports (Makefile runs `cd server && uvicorn app:app`);
# this shim keeps `import server.<mod>` from the repo root (smoke, Lane D4 callers)
# resolving the same flat names.
import pathlib
import sys

_here = str(pathlib.Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)
