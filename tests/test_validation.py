from decimal import Decimal, Inexact, InvalidOperation, ROUND_DOWN, Rounded, getcontext, localcontext
import os
import time

import pytest

from fx_reconciler.validation import FieldInvalid, currency_pair, identifier, positive_decimal, side, timestamp


@pytest.mark.parametrize(('text', 'expected'), [
    ('1', '1'), (' +1 ', '1'), ('1.', '1'), ('.125', '0.125'),
    ('1.23e+40', '12300000000000000000000000000000000000000'),
    ('4E-40', '0.0000000000000000000000000000000000000004'),
    ('123456789012345678901234567890123456789.00100',
     '123456789012345678901234567890123456789.00100'),
])
def test_exact_decimals(text: str, expected: str) -> None:
    assert positive_decimal(text) == Decimal(expected)
    if text.strip().endswith('00100'):
        assert positive_decimal(text).as_tuple().exponent == -5


@pytest.mark.parametrize('text', ['', ' ', '0', '-0', '+0.0', '-1', 'NaN', 'sNaN',
    'Infinity', '-Infinity', '1_0', '1 0', '١', '１', '1e', 'e1', '--1', '+', '.',
    '1e+-1', '1\n2', '1,000'])
def test_invalid_decimals(text: str) -> None:
    with pytest.raises(FieldInvalid):
        positive_decimal(text)


@pytest.mark.parametrize(('text', 'canonical'), [
    ('2024-02-29T00:00:00', '2024-02-29T00:00:00Z'),
    ('2024-02-29T00:00:00Z', '2024-02-29T00:00:00Z'),
    ('2024-03-01T00:30:00+01:00', '2024-02-29T23:30:00Z'),
    ('2024-12-31T23:30:00-01:00', '2025-01-01T00:30:00Z'),
    ('2024-01-01T01:00:00.123456789000+01:00', '2024-01-01T00:00:00.123456789Z'),
    ('2024-01-01T00:00:00.000Z', '2024-01-01T00:00:00Z'),
    ('0001-01-01T00:00:00+00:01', '0000-12-31T23:59:00Z'),
    ('9999-12-31T23:59:00-00:01', '10000-01-01T00:00:00Z'),
])
def test_timestamps(text: str, canonical: str) -> None:
    assert timestamp(text).canonical() == canonical


@pytest.mark.parametrize('text', ['2023-02-29T00:00:00', '0000-01-01T00:00:00',
    '2024-13-01T00:00:00', '2024-01-00T00:00:00', '2024-04-31T00:00:00',
    '2024-01-01T24:00:00', '2024-01-01T00:60:00', '2024-01-01T00:00:60',
    '2024-01-01T00:00:00+24:00', '2024-01-01T00:00:00-01:60',
    '2024-01-01', '2024-01-01t00:00:00', '2024-01-01T00:00:00z',
    '2024-01-01 00:00:00', '2024-01-01T00:00:00.Z',
    '2024-1-01T00:00:00', '２０２４-01-01T00:00:00',
    '2024-01-01T00:00:00+0100', '2024-01-01T00:00:00.١Z'])
def test_invalid_timestamps(text: str) -> None:
    with pytest.raises(FieldInvalid):
        timestamp(text)


def test_fraction_comparisons() -> None:
    base = '2024-01-01T00:00:00'
    assert timestamp(base + '.0000001') < timestamp(base + '.0000002')
    assert timestamp(base + '.1000') == timestamp(base + '.1Z')
    assert timestamp(base + '.09') < timestamp(base + '.1') < timestamp(base + '.11')
    assert timestamp(base + '.123456' + '7' * 5000) > timestamp(base + '.123456')
    assert timestamp(base) == timestamp('2024-01-01T01:00:00+01:00')


def test_context_independence() -> None:
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = ROUND_DOWN
        for signal in ctx.traps:
            ctx.traps[signal] = True
        before = ctx.copy()
        assert positive_decimal('12345678901234567890123456789.12345') == Decimal('12345678901234567890123456789.12345')
        assert timestamp('2024-01-01T00:00:00.0000001') < timestamp('2024-01-01T00:00:00.0000002')
        for text in ('NaN', '-1', '0', '1e99999999999999999999999999'):
            with pytest.raises(FieldInvalid):
                positive_decimal(text)
        assert ctx.prec == before.prec and ctx.rounding == before.rounding
        assert ctx.traps == before.traps and ctx.flags == before.flags


def test_timezone_independence(monkeypatch: pytest.MonkeyPatch) -> None:
    prior = os.environ.get('TZ')
    try:
        for zone in ('UTC0', 'EST5EDT', 'JST-9'):
            monkeypatch.setenv('TZ', zone)
            if hasattr(time, 'tzset'):
                time.tzset()
            assert timestamp('2024-01-01T00:00:00') == timestamp('2024-01-01T09:00:00+09:00')
    finally:
        if prior is None:
            monkeypatch.delenv('TZ', raising=False)
        else:
            monkeypatch.setenv('TZ', prior)
        if hasattr(time, 'tzset'):
            time.tzset()


@pytest.mark.parametrize('text', ['001', '=SUM(A1)', 'A,b', 'A\nB', '\x1b[31m'])
def test_identifiers_preserved(text: str) -> None:
    assert identifier(' ' + text + ' ') == text


@pytest.mark.parametrize('text', ['', ' ', '\t\n'])
def test_empty_identifier(text: str) -> None:
    with pytest.raises(FieldInvalid):
        identifier(text)


@pytest.mark.parametrize('text', ['EURUSD', 'USDJPY', 'ABCXYZ'])
def test_currency_pair(text: str) -> None:
    assert currency_pair(' ' + text + ' ') == text


@pytest.mark.parametrize('text', ['eurusd', 'EURUS', 'EURUSDD', 'EUR1SD', 'ÉURUSD', ''])
def test_bad_pair(text: str) -> None:
    with pytest.raises(FieldInvalid):
        currency_pair(text)


@pytest.mark.parametrize('text', ['BUY', 'SELL'])
def test_side(text: str) -> None:
    assert side(' ' + text + ' ') == text


@pytest.mark.parametrize('text', ['buy', 'Sell', '', 'LONG'])
def test_bad_side(text: str) -> None:
    with pytest.raises(FieldInvalid):
        side(text)
