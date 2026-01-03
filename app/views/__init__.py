"""Views package exports submodules for URLs to import.

Instead of importing many symbols from `api.py` (which required every symbol to exist
at import time and caused ImportError if some were missing), we expose the submodules
`api` and `ui` directly so callers can do `from app.views import api, ui` and then
use `api.some_view` safely.
"""

from . import api, ui
