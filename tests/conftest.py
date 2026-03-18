"""Root conftest — adds all skill script directories to sys.path."""

import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent

for skill_scripts in _repo.glob("knowledge/*/skill/scripts"):
    path = str(skill_scripts)
    if path not in sys.path:
        sys.path.insert(0, path)
