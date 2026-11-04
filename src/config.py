import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "emporio.db"
LIMITS_LOG_PATH = DATA_DIR / "provider_limits.log"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

DEFAULT_REFERENCE_DATE = "2026-03-25"


def reference_date() -> date:
    """Date used as "today" for deadlines. Orders go up to 2026-03-22 (docs/03-data.md, 5.3)."""
    text = os.getenv("REFERENCE_DATE", DEFAULT_REFERENCE_DATE)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"Invalid REFERENCE_DATE: use the YYYY-MM-DD format, not {text!r}.") from error
