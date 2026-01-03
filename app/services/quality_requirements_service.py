"""Quality requirements loader for QA automation."""
import json
import os
from typing import List, Dict

from django.conf import settings


DEFAULT_QUALITY_REQUIREMENTS_PATH = os.getenv(
    "QUALITY_REQUIREMENTS_PATH",
    os.path.join(settings.BASE_DIR, "config", "qa_requirements.json"),
)


def load_quality_requirements(path: str = None) -> List[Dict]:
    """Load quality requirements from JSON file.

    Returns a list of requirement dicts. If file is missing or invalid, returns empty list.
    """
    path = path or DEFAULT_QUALITY_REQUIREMENTS_PATH
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []
