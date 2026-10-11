from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from fx_reconciler.input_validation import load_inputs
from fx_reconciler.models import ErrorCategory as C, Failure, Success

OH = 'order_id,timestamp,currency_pair,side,quantity,limit_price\n'
FH = 'fill_id,order_id,timestamp,quantity,price\n'


def load(tmp_path: Path, orders: str, fills: str) -> object:
    op, fp = tmp_path / 'orders.csv', tmp_path / 'fills.csv'
    op.write_text(OH + orders, encoding='utf-8')
    fp.write_text(FH + fills, encoding='utf-8')
    return load_inputs(op, fp)


@pytest.mark.parametrize(('instant', 'valid'), [
    ('2024-01-01T00:00:00.0000001', False),
    ('2024-01-01T00:00:00.0000002', True),
    ('2024-01-01T00:00:00.0000002000Z', True),
    ('2024-01-01T01:00:00.0000002+01:00', True),
    ('2024-01-01T00:00:00.00000021', True),
    ('2023-12-31T23:59:59.999999999999999999', False),
])
def test_chronology(tmp_path: Path, instant: str, valid: bool) -> None:
    with localcontext() as ctx:
        ctx.prec = 1
        result = load(tmp_path, ' O1 ,2024-01-01T00:00:00.0000002,EURUSD,BUY,1,1\n',
                      f'F1, O1 ,{instant},1,1\n')
    assert isinstance(result, Success if valid else Failure)
    if isinstance(result, Failure):
        assert result.errors[0].category == C.CHRONOLOGY
        assert result.errors[0].field == 'timestamp' and result.errors[0].related is not None


def test_orphans_and_independent_namespaces(tmp_path: Path) -> None:
    result = load(tmp_path, 'O1,2024-01-01T00:00:00,EURUSD,BUY,1,1\n',
                  'O1,UNKNOWN,2023-01-01T00:00:00,2,1\nF2,o1,2023-01-01T00:00:00,1,1\n')
    assert isinstance(result, Success)
    assert [fill.order_id for fill in result.value.fills] == ['UNKNOWN', 'o1']
    assert len(result.value.orders) == 1


@pytest.mark.parametrize('field', ['fill_id', 'order_id', 'timestamp', 'quantity', 'price'])
def test_malformed_orphan(tmp_path: Path, field: str) -> None:
    values = ['F1', 'UNKNOWN', '2024-01-01T00:00:00', '1', '1']
    values[['fill_id', 'order_id', 'timestamp', 'quantity', 'price'].index(field)] = ''
    result = load(tmp_path, '', ','.join(values) + '\n')
    assert isinstance(result, Failure)
    assert result.errors[0].category == C.FIELD and result.errors[0].field == field
    assert not hasattr(result, 'value')


@pytest.mark.parametrize('parents', [('UNKNOWN', 'UNKNOWN2'), ('O1', 'UNKNOWN'), ('UNKNOWN', 'O1')])
def test_all_fill_duplicates(tmp_path: Path, parents: tuple[str, str]) -> None:
    result = load(tmp_path, 'O1,2024-01-01T00:00:00,EURUSD,BUY,1,1\n',
                  ''.join(f' {identity} ,{parent},2024-01-01T00:00:00,1,1\n'
                          for identity, parent in zip(('F1', 'F1'), parents, strict=True)))
    assert isinstance(result, Failure) and result.errors[0].category == C.DUPLICATE
    assert result.errors[0].related is not None
    assert result.errors[0].related.line_start == 2 and result.errors[0].location.line_start == 3


def test_fail_closed_both_files(tmp_path: Path) -> None:
    result = load(tmp_path, 'O1,wrong,EURUSD,BUY,1,1\n', 'F1,UNKNOWN,wrong,1,1\n')
    assert isinstance(result, Failure)
    assert [error.location.kind for error in result.errors] == ['orders', 'fills']


@pytest.mark.parametrize(('group', 'valid'), [('clean', True), ('breaks', True), ('invalid', False)])
def test_fixtures(group: str, valid: bool) -> None:
    root = Path(__file__).parent / 'fixtures' / group
    result = load_inputs(root / 'orders.csv', root / 'fills.csv')
    assert isinstance(result, Success if valid else Failure)
    if group == 'clean':
        assert isinstance(result, Success)
        assert [(o.order_id, o.quantity, o.limit_price) for o in result.value.orders] == [
            ('BUY-001', Decimal('100000'), Decimal('1.1000')),
            ('SELL-001', Decimal('100000'), Decimal('150'))]
        assert [f.quantity for f in result.value.fills] == list(map(Decimal, ('40000', '60000', '60000', '40000')))
    if group == 'breaks':
        assert isinstance(result, Success)
        assert [f.order_id for f in result.value.fills] == ['OVER-001', 'UNKNOWN-001']
        assert result.value.fills[0].quantity == Decimal('110')
    if group == 'invalid':
        assert isinstance(result, Failure) and result.errors[0].category == C.CHRONOLOGY


def test_pure_adapter_rejects_combined_duplicates() -> None:
    from fx_reconciler.input_validation import validate_inputs
    from fx_reconciler.models import Inputs
    root = Path(__file__).parent / 'fixtures' / 'clean'
    loaded = load_inputs(root / 'orders.csv', root / 'fills.csv')
    assert isinstance(loaded, Success)
    result = validate_inputs(Inputs(loaded.value.orders * 2, loaded.value.fills * 2))
    assert isinstance(result, Failure)
    assert len(result.errors) == 6
    assert all(error.category == C.DUPLICATE and error.related is not None for error in result.errors)


def test_input_permutation_preserves_values(tmp_path: Path) -> None:
    orders = ['A,2024-01-01T00:00:00,EURUSD,BUY,1,1\n',
              'B,2024-01-01T00:00:00,USDJPY,SELL,2,150\n']
    fills = ['F1,A,2024-01-01T00:00:01,1,1\n',
             'F2,B,2024-01-01T00:00:01,2,150\n',
             'F3,UNKNOWN,2023-01-01T00:00:00,1,1\n']
    first = load(tmp_path, ''.join(orders), ''.join(fills))
    second = load(tmp_path, ''.join(reversed(orders)), ''.join(reversed(fills)))
    assert isinstance(first, Success) and isinstance(second, Success)
    assert sorted((o.order_id, o.timestamp, o.quantity, o.limit_price) for o in first.value.orders) == sorted(
        (o.order_id, o.timestamp, o.quantity, o.limit_price) for o in second.value.orders)
    assert sorted((f.fill_id, f.order_id, f.timestamp, f.quantity, f.price) for f in first.value.fills) == sorted(
        (f.fill_id, f.order_id, f.timestamp, f.quantity, f.price) for f in second.value.fills)
