"""Pytest config — adds project root to sys.path so `import bot.x` works."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
