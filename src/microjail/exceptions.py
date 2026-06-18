"""Project-wide exception base.

All custom exceptions raised by microjail inherit from :class:`MicrojailError`
so callers can catch every microjail-raised error with a single
``except MicrojailError``. Individual exceptions chain their underlying
causes (typically stdlib or third-party exceptions) via ``raise … from …``
rather than inheriting from those types directly, so domain errors do
not accidentally widen the catch surface of stdlib handlers.
"""


class MicrojailError(Exception):
    """Base class for all microjail-raised exceptions."""
