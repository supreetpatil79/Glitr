import sys
from pathlib import Path

# Add parent root directory to sys.path so Python can find main.py, db.py, models.py, services/
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app
