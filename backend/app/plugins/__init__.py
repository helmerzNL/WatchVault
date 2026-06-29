"""Plugin runtime + metadata enrichment."""
from . import runtime
from .enrich import enrich_title

__all__ = ["runtime", "enrich_title"]
