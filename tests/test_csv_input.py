from pathlib import Path
from decimal import Decimal
import csv
import io

import pytest

from fx_reconciler.csv_input import FILL_COLUMNS, ORDER_COLUMNS, load_fills, load_orders
from fx_reconciler.diagnostics import format_error
from fx_reconciler.models import ErrorCategory as C, Failure, Success

HEADER = ','.join(ORDER_COLUMNS) + '\n'
ROW = '001,2024-01-01T00:00:00,EURUSD,BUY,100,1.1\n'


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding='utf-8', newline='')
    return path


@pytest.mark.parametrize('prefix', ['', '\ufeff'])
@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_bom_reordered_headers(tmp_path: Path, prefix: str, newline: str) -> None:
    text = (' limit_price , quantity , side , currency_pair , timestamp , order_id ' + newline +
            ' 1.1000 , 1e5 , BUY , ABCXYZ , 2024-01-01T00:00:00Z , 001 ' + newline)
    result = load_orders(write(tmp_path / 'orders.csv', prefix + text))
    assert isinstance(result, Success)
    order = result.value[0]
    assert order.order_id == '001' and order.currency_pair == 'ABCXYZ'
    assert order.quantity == Decimal('100000') and order.limit_price.as_tuple().exponent == -4


@pytest.mark.parametrize('header', ['', '\n\n', 'order_id,order_id,timestamp,currency_pair,side,quantity,limit_price\n',
    ' order_id ,order_id,timestamp,currency_pair,side,quantity,limit_price\n',
    'ORDER_ID,timestamp,currency_pair,side,quantity,limit_price\n',
    'order_id,timestamp,currency_pair,side,quantity\n', HEADER.rstrip('\n') + ',extra\n'])
def test_invalid_headers(tmp_path: Path, header: str) -> None:
    result = load_orders(write(tmp_path / 'orders.csv', header))
    assert isinstance(result, Failure)
    assert all(error.category == C.STRUCTURE for error in result.errors)
    assert not hasattr(result, 'value')


def test_header_only(tmp_path: Path) -> None:
    assert load_orders(write(tmp_path / 'orders.csv', '\n' + HEADER + '\n')) == Success(())
    assert load_fills(write(tmp_path / 'fills.csv', ','.join(FILL_COLUMNS) + '\n')) == Success(())


@pytest.mark.parametrize(('row', 'category'), [
    (',,,,,\n', C.FIELD), (' , , , , , \n', C.FIELD),
    (' \n', C.STRUCTURE), ('a,b\n', C.STRUCTURE), (ROW.rstrip('\n') + ',x\n', C.STRUCTURE),
    ('"unterminated', C.STRUCTURE), ('"a"x,2024-01-01T00:00:00,EURUSD,BUY,1,1\n', C.STRUCTURE),
])
def test_bad_records(tmp_path: Path, row: str, category: C) -> None:
    result = load_orders(write(tmp_path / 'orders.csv', HEADER + ROW + row))
    assert isinstance(result, Failure) and result.errors[0].category == category
    assert not hasattr(result, 'value')


@pytest.mark.parametrize('field', ORDER_COLUMNS)
def test_all_required_order_fields(tmp_path: Path, field: str) -> None:
    values = ROW.rstrip('\n').split(',')
    values[ORDER_COLUMNS.index(field)] = ' '
    result = load_orders(write(tmp_path / 'orders.csv', HEADER + ','.join(values) + '\n'))
    assert isinstance(result, Failure)
    assert any(error.field == field and error.category == C.FIELD for error in result.errors)


def test_multiline_blank_lines_and_duplicates(tmp_path: Path) -> None:
    text = '\n' + HEADER + '\n"A,\nB",2024-01-01T00:00:00,EURUSD,BUY,1,1\n\n" A,\nB ",2024-01-01T00:00:00,EURUSD,BUY,1,1\n'
    result = load_orders(write(tmp_path / 'orders.csv', text))
    assert isinstance(result, Failure)
    error = result.errors[0]
    assert error.category == C.DUPLICATE
    assert (error.location.record, error.location.line_start, error.location.line_end) == (3, 7, 8)
    assert error.related is not None
    assert (error.related.record, error.related.line_start, error.related.line_end) == (2, 4, 5)
    assert 'first occurrence' in format_error(error)
    valid = load_orders(write(tmp_path / 'orders.csv', '\n' + HEADER + '\n"A,\nB",2024-01-01T00:00:00,EURUSD,BUY,1,1\n'))
    assert isinstance(valid, Success) and valid.value[0].order_id == 'A,\nB'


def test_duplicate_invalid_first_row(tmp_path: Path) -> None:
    result = load_orders(write(tmp_path / 'orders.csv', HEADER + ROW.replace('100,', 'bad,') + ROW))
    assert isinstance(result, Failure)
    assert [error.category for error in result.errors] == [C.FIELD, C.DUPLICATE]
    assert result.errors[1].related is not None and result.errors[1].related.line_start == 2


def test_case_distinct_and_spreadsheet_ids(tmp_path: Path) -> None:
    rows = ''.join(ROW.replace('001,', value + ',') for value in ('001', 'a', 'A', '=1+1'))
    result = load_orders(write(tmp_path / 'orders.csv', HEADER + rows))
    assert isinstance(result, Success)
    assert tuple(order.order_id for order in result.value) == ('001', 'a', 'A', '=1+1')


def test_io_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for path in (tmp_path / 'missing', tmp_path):
        result = load_orders(path)
        assert isinstance(result, Failure) and result.errors[0].category == C.READ
    path = tmp_path / 'bad.csv'
    path.write_bytes(b'\xff')
    assert isinstance(load_orders(path), Failure)

    def fail_open(self: Path, *args: object, **kwargs: object) -> io.TextIOBase:
        raise PermissionError('controlled failure containing secret')

    monkeypatch.setattr(Path, 'open', fail_open)
    result = load_orders(path)
    assert isinstance(result, Failure) and result.errors[0].category == C.READ
    assert 'secret' not in format_error(result.errors[0])
    assert capsys.readouterr() == ('', '')


def test_unexpected_defect_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_open(self: Path, *args: object, **kwargs: object) -> io.TextIOBase:
        raise RuntimeError('programming defect')
    monkeypatch.setattr(Path, 'open', fail_open)
    with pytest.raises(RuntimeError, match='programming defect'):
        load_orders(tmp_path / 'orders.csv')


def test_safe_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / ('\x1b\n' + 'x' * 200)
    result = load_orders(write(path, HEADER + ROW.replace('100,', 'invalid' * 100 + ',')))
    assert isinstance(result, Failure)
    formatted = format_error(result.errors[0])
    assert '\x1b' not in formatted and '\n' not in formatted
    assert '\\u001b' in formatted and '\\n' in formatted
    assert 'invalidinvalid' not in formatted and len(formatted) < 400
    assert formatted == format_error(result.errors[0])


def test_large_identifier_and_parser_limit_restored(tmp_path: Path) -> None:
    original = csv.field_size_limit()
    try:
        csv.field_size_limit(10)
        value = 'X' * 150000
        result = load_orders(write(tmp_path / 'orders.csv', HEADER + ROW.replace('001,', value + ',')))
        assert isinstance(result, Success) and result.value[0].order_id == value
        assert csv.field_size_limit() == 10
        result = load_orders(tmp_path / 'missing.csv')
        assert isinstance(result, Failure) and csv.field_size_limit() == 10
    finally:
        csv.field_size_limit(original)
