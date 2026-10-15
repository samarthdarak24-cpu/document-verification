"""Core cross-cutting utilities: configuration and security helpers."""

from app.core.config import get_settings
from app.core.security import (
    MAGIC_SIGNATURES,
    SecurityError,
    is_safe_relative_path,
    resolve_safe_path,
    safe_filename,
    validate_magic_bytes,
)

__all__ = [
    "get_settings",
    "safe_filename",
    "validate_magic_bytes",
    "MAGIC_SIGNATURES",
    "is_safe_relative_path",
    "resolve_safe_path",
    "SecurityError",
]
