from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).parent.parent


def setup_paths():
    paths = [
        str(PROJECT_ROOT / "08_parser"),
        str(PROJECT_ROOT / "09_pipeline"),
        str(PROJECT_ROOT / "07_simulator"),
    ]
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)

