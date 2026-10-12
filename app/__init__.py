"""Mørkyn's server package."""

from app.quiet_children import install as _quiet_children

# Before any module runs a subprocess: the tools Mørkyn runs must not open
# console windows on Windows (see app/quiet_children.py).
_quiet_children()
