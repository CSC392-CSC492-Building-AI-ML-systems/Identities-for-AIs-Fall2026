"""Root test package. Support the established fingerprinting imports."""
import os
import sys
# Do not write caches into immutable upstream artifact bundles.
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
from pathlib import Path
SYSTEM = Path(__file__).resolve().parents[1] / "system"
if str(SYSTEM) not in sys.path:
    sys.path.insert(0, str(SYSTEM))
