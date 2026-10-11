"""Cross-file validation and I/O adapter; no reconciliation arithmetic."""
from pathlib import Path

from .csv_input import load_fills, load_orders
from .models import ErrorCategory, Failure, InputError, Inputs, Order, SourceLocation, Success


def validate_inputs(inputs: Inputs) -> Success[Inputs] | Failure:
    """Check parent-relative chronology on already validated file records."""
    errors: list[InputError] = []
    # Defend the pure adapter too: callers may combine individually valid files.
    for records, field in ((inputs.orders, "order_id"), (inputs.fills, "fill_id")):
        seen: dict[str, SourceLocation] = {}
        for record in records:
            identity = record.order_id if isinstance(record, Order) else record.fill_id
            if identity in seen:
                errors.append(InputError(ErrorCategory.DUPLICATE, record.source,
                                         "duplicate identifier", field, seen[identity]))
            else:
                seen[identity] = record.source
    if errors:
        return Failure(tuple(errors))
    parents = {order.order_id: order for order in inputs.orders}
    for fill in inputs.fills:
        parent = parents.get(fill.order_id)
        if parent is not None and fill.timestamp < parent.timestamp:
            errors.append(InputError(ErrorCategory.CHRONOLOGY, fill.source,
                                     "fill precedes known parent order", "timestamp", parent.source))
    return Failure(tuple(errors)) if errors else Success(inputs)


def load_inputs(orders_path: Path, fills_path: Path) -> Success[Inputs] | Failure:
    orders = load_orders(orders_path)
    fills = load_fills(fills_path)
    errors = tuple(error for result in (orders, fills) if isinstance(result, Failure)
                   for error in result.errors)
    if errors:
        return Failure(errors)
    assert isinstance(orders, Success) and isinstance(fills, Success)
    return validate_inputs(Inputs(orders.value, fills.value))
