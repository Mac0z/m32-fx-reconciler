"""Bounded human diagnostics, separate from structured error metadata."""
import json

from .models import ErrorCategory, InputError, SourceLocation


def _preview(text: str) -> str:
    # Escape first so truncation bounds displayed output, including controls.
    escaped = json.dumps(text[:160], ensure_ascii=True)
    return escaped if len(escaped) <= 180 else escaped[:177] + "..."


def _location(source: SourceLocation) -> str:
    return (f"{source.kind} {_preview(str(source.path))}: record {source.record}, "
            f"lines {source.line_start}-{source.line_end}")


def format_error(error: InputError) -> str:
    field = f" field {_preview(error.field)}" if error.field else ""
    label = "first occurrence" if error.category == ErrorCategory.DUPLICATE else "related order"
    related = f"; {label} at {_location(error.related)}" if error.related else ""
    return (f"{_location(error.location)} [{error.category}]{field}: "
            f"{_preview(error.message)}{related}")
