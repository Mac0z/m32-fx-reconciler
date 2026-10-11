"""CSV I/O and located validation; invalid files never expose partial records."""
import csv
import sys
from pathlib import Path
from typing import Callable, Literal, overload

from . import validation as v
from .models import (ErrorCategory as C, Failure, Fill, InputError, InputKind,
                     Order, SourceLocation, Success)

ORDER_COLUMNS = ("order_id", "timestamp", "currency_pair", "side", "quantity", "limit_price")
FILL_COLUMNS = ("fill_id", "order_id", "timestamp", "quantity", "price")


@overload
def load_csv(path: Path, kind: Literal["orders"]) -> Success[tuple[Order, ...]] | Failure: ...
@overload
def load_csv(path: Path, kind: Literal["fills"]) -> Success[tuple[Fill, ...]] | Failure: ...


def load_csv(path: Path, kind: InputKind) -> Success[tuple[Order, ...]] | Success[tuple[Fill, ...]] | Failure:
    columns = ORDER_COLUMNS if kind == "orders" else FILL_COLUMNS
    errors: list[InputError] = []
    orders: list[Order] = []
    fills: list[Fill] = []
    seen: dict[str, SourceLocation] = {}
    record = 0
    end = 0
    start = 1
    reader: csv.reader | None = None
    previous_limit = csv.field_size_limit()
    # CSV's small default field limit is not an identifier contract. Scope the
    # parser capacity change to this adapter and restore it even on failure.
    csv.field_size_limit(sys.maxsize)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header: list[str] | None = None
            for row in reader:
                start, end = end + 1, reader.line_num
                if not row:  # Only genuinely empty physical lines.
                    continue
                record += 1
                location = SourceLocation(kind, path, record, start, end)
                if header is None:
                    header = [cell.strip() for cell in row]
                    seen_headers: set[str] = set()
                    for name in header:
                        if name in seen_headers:
                            errors.append(InputError(C.STRUCTURE, location, "duplicate header name", name))
                        seen_headers.add(name)
                    for name in columns:
                        if name not in seen_headers:
                            errors.append(InputError(C.STRUCTURE, location, "missing required header column", name))
                    for name in header:
                        if name not in columns:
                            errors.append(InputError(C.STRUCTURE, location, "unexpected header column", name))
                    if errors:
                        return Failure(tuple(errors))
                    continue
                if len(row) != len(header):
                    errors.append(InputError(C.STRUCTURE, location, "record field count differs from header"))
                    continue
                raw = dict(zip(header, row, strict=True))
                id_field = columns[0]
                id_value = raw[id_field].strip()
                if id_value:
                    if id_value in seen:
                        errors.append(InputError(C.DUPLICATE, location, "duplicate identifier", id_field, seen[id_value]))
                    else:
                        seen[id_value] = location
                row_errors: list[InputError] = []

                def parse[T](field: str, validator: Callable[[str], T]) -> T | None:
                    try:
                        return validator(raw[field])
                    except v.FieldInvalid as error:
                        row_errors.append(InputError(C.FIELD, location, str(error), field))
                        return None

                identity = parse(id_field, v.identifier)
                instant = parse("timestamp", v.timestamp)
                quantity = parse("quantity", v.positive_decimal)
                price = parse("limit_price" if kind == "orders" else "price", v.positive_decimal)
                if kind == "orders":
                    pair = parse("currency_pair", v.currency_pair)
                    direction = parse("side", v.side)
                    if not row_errors:
                        assert identity is not None and instant is not None and quantity is not None and price is not None
                        assert pair is not None and direction is not None
                        orders.append(Order(identity, instant, pair, direction, quantity, price, location))
                else:
                    parent = parse("order_id", v.identifier)
                    if not row_errors:
                        assert identity is not None and instant is not None and quantity is not None and price is not None and parent is not None
                        fills.append(Fill(identity, parent, instant, quantity, price, location))
                errors.extend(row_errors)
            if header is None:
                errors.append(InputError(C.STRUCTURE, SourceLocation(kind, path, 0, 1, max(end, 1)), "required header absent"))
    except (OSError, UnicodeDecodeError):
        errors.append(InputError(C.READ, SourceLocation(kind, path, record + 1, end + 1, max(end + 1, reader.line_num if reader else 1)), "cannot read UTF-8 input"))
    except csv.Error:
        errors.append(InputError(C.STRUCTURE, SourceLocation(kind, path, record + 1, end + 1, max(end + 1, reader.line_num if reader else 1)), "malformed CSV syntax"))
    finally:
        csv.field_size_limit(previous_limit)
    if errors:
        return Failure(tuple(errors))
    return Success(tuple(orders)) if kind == "orders" else Success(tuple(fills))


def load_orders(path: Path) -> Success[tuple[Order, ...]] | Failure:
    return load_csv(path, "orders")


def load_fills(path: Path) -> Success[tuple[Fill, ...]] | Failure:
    return load_csv(path, "fills")
