"""microjq -- A minimal jq clone in Python for querying JSON from the command line."""

__version__ = "1.0.0"
__all__ = ["jq", "JQError", "extract", "parse_expr"]

from .core import jq, JQError, extract, parse_expr
