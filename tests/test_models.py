from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from fx_reconciler.csv_input import load_orders
from fx_reconciler.models import Failure, Success, Timestamp


def test_immutable_values() -> None:
    path = Path(__file__).parent / 'fixtures' / 'clean' / 'orders.csv'
    result = load_orders(path)
    assert isinstance(result, Success)
    with pytest.raises(FrozenInstanceError):
        result.value[0].order_id = 'changed'  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.value[0].source.line_start = 9  # type: ignore[misc]


@pytest.mark.parametrize('fraction', ['0', '10', '١', '-1', '1.1'])
def test_timestamp_representation(fraction: str) -> None:
    with pytest.raises(ValueError):
        Timestamp(0, fraction)


def test_failure_requires_errors() -> None:
    with pytest.raises(ValueError):
        Failure(())
