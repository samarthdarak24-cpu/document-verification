"""Security helpers shared by the upload and download paths.

Two independent concerns live here:

1. **Filename sanitising** — :func:`safe_filename` turns an arbitrary
   client-supplied name into a conservative, path-free token. It is applied to
   *every* upload before anything touches the filesystem, so a name such as
   ``..\\..\\..\\etc\\passwd`` can never escape the storage root.
2. **Content sniffing** — :func:`validate_magic_bytes` checks the leading bytes
   of an upload against the signature the *extension* claims. This blocks the
   trivial "rename ``evil.exe`` to ``invoice.pdf``" trick; it is a cheap guard,
   not a sandbox.

Both helpers are deliberately dependency-free (stdlib only) so they can be used
from the pipeline, the routers and the test-suite alike.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence, Tuple

#: Characters accepted in a sanitised filename.
_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]")

#: Maximum length of a sanitised filename (including the extension).
MAX_FILENAME_LENGTH = 128


class SecurityError(ValueError):
    """Raised when a path or filename is unsafe to use."""


# --------------------------------------------------------------------------- #
# Filenames
# --------------------------------------------------------------------------- #
def safe_filename(filename: str) -> str:
    """Return a safe, path-free version of ``filename``.

    The transformation is:

    1. Take the basename after splitting on both POSIX (``/``) and Windows
       (``\\``) separators — this is what removes directory components.
    2. Drop every character outside ``[A-Za-z0-9._-]`` (this also removes NUL,
       control characters and Unicode tricks such as the right-to-left override).
    3. Collapse leading dots so the result can never be ``.``, ``..`` or a
       hidden dotfile, and strip a trailing dot/space (illegal on Windows and a
       classic path-truncation trick).
    4. Truncate to :data:`MAX_FILENAME_LENGTH` characters while preserving the
       extension.

    Raises
    ------
    SecurityError
        If nothing usable remains after sanitising.
    """
    if not filename or not isinstance(filename, str):
        raise SecurityError("A non-empty filename is required.")

    # 1. basename (handles both separator conventions, repeatedly).
    name = filename.replace("\\", "/").split("/")[-1]
    name = name.split("\x00")[0]
    # 2. allow-list.
    name = _SAFE_CHARS_RE.sub("", name)
    # 3. no dotfiles, no trailing dots/spaces, no reserved single/double dots.
    name = name.lstrip(".")
    name = name.rstrip(" .-")

    if not name:
        raise SecurityError(f"Filename {filename!r} contains no usable characters.")

    # 4. length cap, extension preserved.
    if len(name) > MAX_FILENAME_LENGTH:
        suffix = Path(name).suffix[:32]
        stem_budget = MAX_FILENAME_LENGTH - len(suffix)
        if stem_budget <= 0:  # pathological: an extension longer than the cap
            name = name[:MAX_FILENAME_LENGTH]
        else:
            stem = name[: len(name) - len(suffix)] if suffix else name
            name = stem[:stem_budget] + suffix

    if name in {".", ".."}:
        raise SecurityError(f"Filename {filename!r} sanitises to a path token.")
    return name


# --------------------------------------------------------------------------- #
# Magic bytes
# --------------------------------------------------------------------------- #
#: Extension -> list of accepted leading-byte signatures.
#: Text formats (``.txt``, ``.md``, ``.csv``, ``.log``) intentionally have no
#: entry: they carry no signature, so nothing can be verified.
MAGIC_SIGNATURES: dict[str, Tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "pptx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    # ``.jif`` (JPEG interchange / rarely-used variant) shares the JPEG SOI
    # marker, so it is accepted alongside ``.jpg`` / ``.jpeg``.
    "jif": (b"\xff\xd8\xff",),
    "bmp": (b"BM",),
    "tif": (b"II*\x00", b"MM\x00*"),
    "tiff": (b"II*\x00", b"MM\x00*"),
    "webp": (b"RIFF",),
}

#: Extensions that never carry a magic signature (verified as "nothing to check").
_SIGNATURE_FREE_EXTENSIONS = {"txt", "md", "markdown", "csv", "tsv", "log", "json", "rtf"}

#: Longest signature we ever compare against.
_MAX_SIGNATURE_LEN = max(len(sig) for sigs in MAGIC_SIGNATURES.values() for sig in sigs)


def extension_of(filename: str) -> str:
    """Return the lowercase extension of ``filename`` without the leading dot."""
    name = filename.replace("\\", "/").split("/")[-1]
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def sniff(content: bytes) -> str | None:
    """Return the extension implied by ``content``'s magic bytes, else ``None``."""
    if not content:
        return None
    head = content[:_MAX_SIGNATURE_LEN]
    for extension, signatures in MAGIC_SIGNATURES.items():
        for signature in signatures:
            if head.startswith(signature):
                return extension
    return None


def validate_magic_bytes(filename: str, content: bytes) -> bool:
    """Check that ``content`` starts with the signature ``filename`` claims.

    * ``.pdf``          -> ``%PDF-``
    * ``.docx`` / OOXML -> ``PK\\x03\\x04`` (ZIP container)
    * ``.png``          -> ``\\x89PNG\\r\\n\\x1a\\n``
    * ``.jpg``/``.jpeg``/``.jif`` -> ``\\xff\\xd8\\xff`` (SOI)
    * ``.gif``          -> ``GIF87a`` / ``GIF89a``

    Text formats have no signature and are accepted. An *unknown* extension is
    also accepted (we simply have nothing to verify) but the caller is expected
    to reject unsupported types at the validation stage; this helper only
    guarantees "the bytes are not lying about the ones we know".

    Returns ``True`` when the content is consistent with the extension (or when
    no signature is known for it), ``False`` otherwise. Never raises.
    """
    extension = extension_of(filename)
    if extension in _SIGNATURE_FREE_EXTENSIONS:
        return True
    signatures = MAGIC_SIGNATURES.get(extension)
    if not signatures:
        # Unknown extension: nothing to verify. The upload size/type policy is
        # enforced by the validation stage, not here.
        return True
    if not content:
        return False
    return content.startswith(signatures)


def required_signature_error(filename: str) -> str | None:
    """Return a human-readable reason when ``filename`` fails magic validation."""
    extension = extension_of(filename)
    if extension in _SIGNATURE_FREE_EXTENSIONS or extension not in MAGIC_SIGNATURES:
        return None
    return (
        f"File content does not match the .{extension} signature "
        f"(expected one of {', '.join(repr(s) for s in MAGIC_SIGNATURES[extension])})."
    )


# --------------------------------------------------------------------------- #
# Path safety
# --------------------------------------------------------------------------- #
def is_safe_relative_path(path: str | Path, root: str | Path) -> bool:
    """Return ``True`` when ``path`` resolves to a location inside ``root``.

    The check is defensive on three levels:

    * no ``..`` component may appear in the *literal* relative path;
    * the fully resolved (symlinks followed, ``..`` normalised) path must still
      be inside the resolved ``root``;
    * an absolute ``path`` is only accepted when it is already inside ``root``.

    This defeats both naive traversal (``../../etc/passwd``) and cleverer tricks
    (a symlink inside the storage root pointing outside it).
    """
    if path is None:
        return False
    candidate = Path(str(path))
    root_path = Path(str(root))

    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
            root_resolved = root_path.resolve()
            return resolved == root_resolved or root_resolved in resolved.parents
        except (OSError, ValueError):
            return False

    literal = Path(str(path))
    if any(part == ".." for part in literal.parts):
        return False
    if literal.is_absolute():
        return False
    try:
        resolved = (root_path / literal).resolve()
        root_resolved = root_path.resolve()
    except (OSError, ValueError):
        return False
    return resolved == root_resolved or root_resolved in resolved.parents


def resolve_safe_path(root: str | Path, relative: str | Path) -> Path:
    """Resolve ``relative`` inside ``root`` or raise :class:`SecurityError`.

    This is the single choke-point used by both the upload writer and the
    download/read routers, so every filesystem access in DocuTrace goes through
    the same validation.
    """
    if not is_safe_relative_path(relative, root):
        raise SecurityError(
            f"Refusing to access {str(relative)!r}: path escapes the allowed root "
            f"{Path(str(root)).resolve()}."
        )
    root_path = Path(str(root))
    candidate = Path(str(relative))
    if candidate.is_absolute():
        return candidate.resolve()
    return (root_path / candidate).resolve()


def safe_join(root: str | Path, *parts: str) -> Path:
    """Like :func:`resolve_safe_path` but for a path built from segments.

    Any segment containing a separator or a ``..`` component raises
    :class:`SecurityError` *before* the join happens, so no untrusted segment is
    ever interpolated into a filesystem path.
    """
    cleaned: list[str] = []
    for part in parts:
        if part is None:
            continue
        text = str(part)
        if text in {"", ".", ".."}:
            raise SecurityError(f"Unsafe path segment: {text!r}")
        if "/" in text or "\\" in text:
            raise SecurityError(f"Path segment must not contain separators: {text!r}")
        cleaned.append(text)
    if not cleaned:
        raise SecurityError("At least one path segment is required.")
    return resolve_safe_path(root, Path(*cleaned))


def contains_null_bytes(value: str) -> bool:
    """Return ``True`` when ``value`` embeds a NUL (truncation attack)."""
    return "\x00" in value


def mask_sequence(values: Iterable[str], keep: int = 4) -> Sequence[str]:
    """Mask every value but the last ``keep`` characters (for logging digests)."""
    out: list[str] = []
    for value in values:
        text = str(value)
        out.append(("*" * max(0, len(text) - keep)) + text[-keep:] if len(text) > keep else text)
    return out
