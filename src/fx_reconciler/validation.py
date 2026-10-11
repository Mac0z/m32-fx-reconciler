"""Pure lexical and field validation, independent of Decimal context."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import cast

from .models import Side, Timestamp

_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_TIMESTAMP = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]+))?(Z|[+-][0-9]{2}:[0-9]{2})?"
)


class FieldInvalid(ValueError):
    """Controlled reason for a field failure; never contains raw input."""


def identifier(text: str) -> str:
    value = text.strip()
    if not value:
        raise FieldInvalid("required nonempty identifier")
    return value


def positive_decimal(text: str) -> Decimal:
    value = text.strip()
    if not _DECIMAL.fullmatch(value):
        raise FieldInvalid("expected finite positive ASCII decimal")
    # Construction is exact. Isolate the implementation-limit error flag too.
    with localcontext() as context:
        context.traps[InvalidOperation] = True
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise FieldInvalid("decimal outside supported representation") from None
    if not number.is_finite() or number.is_zero() or number.is_signed():
        raise FieldInvalid("expected finite strictly positive decimal")
    return number


def timestamp(text: str) -> Timestamp:
    match = _TIMESTAMP.fullmatch(text.strip())
    if match is None:
        raise FieldInvalid("expected YYYY-MM-DDTHH:MM:SS[.fraction][Z|±HH:MM]")
    year, month, day, hour, minute, second = map(int, match.group(1, 2, 3, 4, 5, 6))
    try:
        calendar = date(year, month, day)
    except ValueError:
        raise FieldInvalid("invalid calendar date") from None
    if hour > 23 or minute > 59 or second > 59:
        raise FieldInvalid("invalid time of day")
    offset = match.group(8)
    offset_seconds = 0
    if offset and offset != "Z":
        offset_hour, offset_minute = int(offset[1:3]), int(offset[4:6])
        if offset_hour > 23 or offset_minute > 59:
            raise FieldInvalid("invalid UTC offset")
        offset_seconds = (offset_hour * 3600 + offset_minute * 60) * (1 if offset[0] == "+" else -1)
    seconds = ((calendar.toordinal() - 1) * 86400 + hour * 3600 +
               minute * 60 + second - offset_seconds)
    return Timestamp(seconds, (match.group(7) or "").rstrip("0"))


def currency_pair(text: str) -> str:
    value = text.strip()
    if not re.fullmatch(r"[A-Z]{6}", value):
        raise FieldInvalid("expected six uppercase ASCII letters")
    return value


def side(text: str) -> Side:
    value = text.strip()
    if value not in ("BUY", "SELL"):
        raise FieldInvalid("expected BUY or SELL")
    return cast(Side, value)
