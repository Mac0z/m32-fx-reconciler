# m32-fx-reconciler — M1

M1 implements immutable typed inputs, exact decimal/timestamp validation,
fail-closed CSV ingestion and located diagnostics. M2 reconciliation and M3
CLI, reports, operational logging, publication and GitHub Actions are deferred.
There is intentionally no console script or module entry point yet. This is not
final product acceptance or a claim that CI has passed.

Use Python 3.14 (other versions are not supported):

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
.venv/bin/python -c "import sys, fx_reconciler; assert sys.version_info[:2] == (3, 14)"
.venv/bin/python -m pip wheel --no-deps --wheel-dir .wheel-check .
```

The runtime uses only the standard library. Build/test dependencies are pinned
in `pyproject.toml`. Tests import the installed package, without `PYTHONPATH`.
Imports and validation create no logs or reports, configure no logging and
produce no console output. Runtime logs/build artifacts are excluded from
version control and package data.

Required orders columns are
`order_id,timestamp,currency_pair,side,quantity,limit_price`; fills columns are
`fill_id,order_id,timestamp,quantity,price`. Headers are case-sensitive, may be
reordered, and must contain exactly these columns without duplicates. Inputs
are UTF-8 with optional BOM, with standard CSV quoting and multiline fields.
Empty physical lines are ignored; delimiter-only and populated whitespace-only
records are invalid. Header-only files are valid.

All fields and headers have surrounding whitespace trimmed. IDs remain strings:
leading zeros, internal newlines, commas, case and spreadsheet-like content are
preserved. Import untrusted string columns as text in spreadsheet software to
avoid formula interpretation. IDs must be nonempty; order IDs and fill IDs have
separate namespaces. Duplicates, including invalid rows and orphan fills, fail
validation and identify both occurrences. There is no repair or deduplication.

Currency pairs are exactly six uppercase ASCII letters; no currency registry
is imposed. Side is exactly `BUY` or `SELL`. Quantity is in base-currency units;
prices are quote currency per base currency. Quantity and price must be finite
and strictly positive. ASCII ordinary/scientific decimal notation is accepted,
including `+1`, `.5`, `1.` and `1e-20`; embedded whitespace, underscores, Unicode
digits, NaN and infinity are rejected. Decimal values are constructed directly
from text without floats, rounding, normalization or global-context mutation.
Long coefficients and scientific notation retain their represented value.

Timestamps use `YYYY-MM-DDTHH:MM:SS[.fraction][Z|±HH:MM]`, with fixed-width ASCII
components, uppercase T/Z and one or more fractional digits. Offset-free values
mean UTC. Valid offsets are below 24 hours, with minutes below 60. Impossible
dates/times, leap seconds and 24:00:00 are rejected. UTC ordering uses integer
seconds and canonical fractional digits, preserving precision beyond six digits
without Decimal arithmetic, host timezone or floating-point POSIX timestamps.
`Timestamp.canonical()` emits UTC with Z and removes insignificant fractional
zeros. Offset normalization across the calendar endpoints retains the instant
using a proleptic Gregorian coordinate (year 0000 or 10000 may result).

```python
from pathlib import Path
from fx_reconciler.input_validation import load_inputs
from fx_reconciler.models import Failure
from fx_reconciler.diagnostics import format_error

result = load_inputs(Path('tests/fixtures/clean/orders.csv'),
                     Path('tests/fixtures/clean/fills.csv'))
if isinstance(result, Failure):
    diagnostics = tuple(format_error(error) for error in result.errors)
else:
    inputs = result.value
```

`load_orders` and `load_fills` return `Success[tuple[Order, ...]]` /
`Success[tuple[Fill, ...]]` or `Failure`. `load_inputs` additionally checks exact
chronology for known parents: equality passes, earlier fills fail. Unknown
parents are valid orphans, retained in the fills tuple without association to
any known order. All orphan fields and IDs still receive normal validation.
A failure exposes errors only, never a successful partial dataset. Pure field
validators raise only controlled `FieldInvalid` exceptions for invalid fields;
I/O adapters convert expected read, decoding and CSV errors to structured errors.
Unexpected programming defects propagate.

Errors distinguish structure, field, duplicate_id, chronology and input_read.
Each carries input kind, Path, nonempty CSV record number (header is record 1),
physical start/end lines and optional field/related source location. Empty-file
errors use record 0. Diagnostics escape and bound variable text without dumping
rows or modifying identifiers. On read/decode failure the location is the next
record being read; text decoding may read ahead, so its exact byte is unavailable.

Fixtures are synthetic. `clean` contains the SPEC BUY EURUSD and SELL USDJPY
anchors; `breaks` contains an overfill and a valid orphan; `invalid` contains an
earlier fill. M1 asserts only their input behavior. Statuses, VWAP, pips,
slippage, final-only half-even rounding, exit codes, atomic CSV overwrite and
per-run logs remain M2/M3 work; no calculated financial outputs are supplied.
