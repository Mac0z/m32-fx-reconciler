"""Immutable input values and explicit validation results."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal

InputKind = Literal["orders", "fills"]
Side = Literal["BUY", "SELL"]


@dataclass(frozen=True, slots=True, order=True)
class Timestamp:
    """UTC seconds since ordinal day 1, and canonical fractional digits.

    Fractions omit trailing zeros. Lexical ordering of these digits is exact
    for fractions in [0, 1), including an empty string representing zero.
    """
    seconds: int
    fraction: str = ""

    def __post_init__(self) -> None:
        if self.fraction and (not self.fraction.isascii() or
                              not self.fraction.isdigit() or
                              self.fraction.endswith("0")):
            raise ValueError("fraction must be canonical ASCII digits")

    def canonical(self) -> str:
        days, second = divmod(self.seconds, 86400)
        # Gregorian cycles also cover offset normalization across year bounds.
        cycles, day = divmod(days, 146097)
        calendar = date.fromordinal(day + 1)
        year = calendar.year + cycles * 400
        hour, second = divmod(second, 3600)
        minute, second = divmod(second, 60)
        suffix = f".{self.fraction}" if self.fraction else ""
        return (f"{year:04d}-{calendar.month:02d}-{calendar.day:02d}T"
                f"{hour:02d}:{minute:02d}:{second:02d}{suffix}Z")


@dataclass(frozen=True, slots=True)
class SourceLocation:
    kind: InputKind
    path: Path
    record: int
    line_start: int
    line_end: int


class ErrorCategory(StrEnum):
    STRUCTURE = "structure"
    FIELD = "field"
    DUPLICATE = "duplicate_id"
    CHRONOLOGY = "chronology"
    READ = "input_read"


@dataclass(frozen=True, slots=True)
class InputError:
    category: ErrorCategory
    location: SourceLocation
    message: str
    field: str | None = None
    related: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class Success[T]:
    value: T


@dataclass(frozen=True, slots=True)
class Failure:
    errors: tuple[InputError, ...]

    def __post_init__(self) -> None:
        if not self.errors:
            raise ValueError("failure requires errors")


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    timestamp: Timestamp
    currency_pair: str
    side: Side
    quantity: Decimal
    limit_price: Decimal
    source: SourceLocation


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    order_id: str
    timestamp: Timestamp
    quantity: Decimal
    price: Decimal
    source: SourceLocation


@dataclass(frozen=True, slots=True)
class Inputs:
    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]
