# SPEC.md

## 1. Product intent and authority

Build `m32-fx-reconciler`, a production-quality Python 3.14 command-line application that validates orders and execution fills, reconciles fills to orders, calculates FX execution statistics, and produces deterministic human-readable, CSV and JSON reports.

This document is the product source of truth. `AGENTS.md` defines durable implementation policy without changing product requirements. Repository visibility must be **public**. Committed fixtures, examples and published artifacts must contain synthetic data only.

Structured operational logging is required throughout the application workflow. Each reconciliation invocation produces its own UTC-timestamped log file. Logs are operational artifacts, not part of the financial report.

## 2. Scope and non-goals

### In scope

- Local orders and fills CSV ingestion with actionable validation errors.
- Zero, one or many fills per order.
- Duplicate-ID detection, orphan-fill detection and chronological validation.
- Order classification, filled and remaining quantity, VWAP and signed FX slippage.
- Console reporting, optional detailed CSV export and machine-readable JSON output.
- Structured per-run file logging covering ingestion, validation, reconciliation, serialization, publication and failures.
- Documented exit codes, comprehensive automated tests, realistic examples, installation documentation and GitHub Actions CI.

### Out of scope

- Broker connectivity, streaming ingestion, databases, web services and a GUI.
- Matching orders by attributes other than `order_id`.
- Currency conversion, fees, commissions, market-price benchmarks or P&L accounting.
- Inferring, repairing, deduplicating or dropping invalid financial records.
- A complete currency-code registry; currency-pair validation is structural.
- Treating adverse slippage as an exit-code reconciliation break.
- Remote logging, telemetry, automatic log rotation or automatic deletion of old logs.

## 3. Runtime, packaging and dependencies

- Supported and tested runtime: Python **3.14**.
- Provide an installable package using `pyproject.toml`, a `src/` layout and the console entry point `fx-reconcile`.
- Also support `python -m fx_reconciler` with equivalent behavior.
- Use type hints throughout application code and tests.
- Use `pathlib.Path` for file paths and standard-library CSV, JSON, decimal, datetime, logging and CLI facilities.
- No third-party runtime dependencies are required or permitted without a documented SPEC amendment. Use `pytest` as a development/test dependency; a minimal packaging build backend is permitted.
- Additional development tooling must have a demonstrated need and Python 3.14 compatibility.
- Do not claim support for additional Python versions without testing them.

## 4. CLI interface and exit behavior

```text
fx-reconcile --orders ORDERS.csv --fills FILLS.csv [--output REPORT.csv] [--json] [--log-dir DIRECTORY]
python -m fx_reconciler --orders ORDERS.csv --fills FILLS.csv [--output REPORT.csv] [--json] [--log-dir DIRECTORY]
```

- `--orders` and `--fills` are required file paths.
- Without `--json`, stdout contains the human-readable report.
- With `--json`, stdout contains exactly one JSON report followed by LF, without a human summary, log messages or banners.
- `--output` writes the detailed per-order CSV report. It may be combined with `--json`; JSON goes to stdout and CSV goes to the specified file.
- `--log-dir` overrides the default log directory described in section 9. Relative paths are resolved against the invocation's working directory.
- `--help` documents all arguments and exits successfully without reading inputs or creating logs or reports.
- Invocation errors detected before execution starts return `2` without requiring a log file.
- Diagnostics go to stderr, never stdout. Ordinary successful or reconciliation-break runs must not emit logging banners to either stream.
- For a syntactically valid reconciliation invocation, initialize the run log before loading inputs. Logging is enabled by default and has no silent-disable fallback.
- Fully validate inputs before publishing financial reports. Invalid input must not publish a partial financial report or replace an existing CSV output. An operational log may still be created.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Valid inputs and no overfilled orders or orphan fills. Unfilled and partially filled orders are not breaks. |
| `1` | Valid inputs with one or more overfilled orders or orphan fills. Produce the complete report. |
| `2` | Invalid invocation, unreadable input, malformed CSV or invalid data, including duplicate IDs and fills before known parent orders. |
| `3` | Operational failure while creating or emitting reports or required logs, including an unwritable destination. |

Operational failures take precedence over reconciliation status. Expected failures must be user-facing and traceback-free. An unexpected programming defect must not be classified as a successful reconciliation or an ordinary reconciliation break.

A logging failure must not silently downgrade to an unlogged run. Report it on stderr and return `3`; stop further report publication. Already completed filesystem replacements or bytes already written to stdout cannot be retracted. Do not claim a transaction spanning logs, CSV and stdout.

## 5. Input contracts

### CSV structure

- Read UTF-8 CSV and accept an optional UTF-8 BOM.
- Use standard comma-separated CSV quoting, including quoted commas and multiline fields.
- A header is required; required columns may appear in any order.
- Trim surrounding whitespace from header names and field values. Header names are case-sensitive.
- Reject duplicate, missing and unexpected header columns. Reject records with the wrong field count or malformed CSV syntax.
- Ignore genuinely empty physical lines. A populated record consisting of delimiters or whitespace fields is not an empty line and must fail required-value validation.
- A header-only file is valid. A file without a header is invalid.
- Identifiers are nonempty strings after trimming, compared case-sensitively. Preserve their content without numeric coercion or case folding.
- Errors identify the input kind, source path, record/line location and field where applicable. Duplicate-ID errors identify both occurrences.
- Diagnostics must be stable, escaped and bounded; do not dump entire records or files.
- Fail closed: no invalid record may be silently skipped to produce an apparently complete report.

### Orders

Required columns:

```csv
order_id,timestamp,currency_pair,side,quantity,limit_price
```

- `order_id`: unique throughout the orders file.
- `timestamp`: a valid timestamp in the supported profile below.
- `currency_pair`: exactly six uppercase ASCII letters, such as `EURUSD` or `USDJPY`. The first three identify the base currency; the last three identify the quote currency. No currency registry is required.
- `side`: exactly `BUY` or `SELL` after trimming.
- `quantity`: finite, strictly positive decimal quantity in base-currency units.
- `limit_price`: finite, strictly positive decimal quote-currency price per base-currency unit.

### Fills

Required columns:

```csv
fill_id,order_id,timestamp,quantity,price
```

- `fill_id`: unique throughout the fills file, including orphan fills.
- `order_id`: nonempty parent identifier, normalized using the same trimming rules as declared order IDs.
- `timestamp`: a valid timestamp in the supported profile.
- `quantity` and `price`: finite, strictly positive decimals, using the same units as the parent order where known.
- For a known parent, the fill timestamp must be greater than or equal to the order timestamp after normalization. Earlier fills are invalid input, not reconciliation breaks.
- An unknown parent creates an orphan fill, not an invalid reference. Validate all independent fields normally, retain the fill in the report, and do not attach it to an order. Parent-relative chronology cannot be checked for an orphan.

### Numeric interpretation

- Construct quantities and prices directly from decimal text, never through binary floating-point.
- Accept ordinary decimal notation and scientific decimal notation, with an optional sign, decimal point and exponent. Numeric digits are ASCII; embedded whitespace and underscores are not supported.
- Reject malformed values, NaN, signaling NaN, infinities, zero and negative quantities or prices.
- Parsing must preserve the represented decimal value exactly, independently of the ambient Decimal context.

### Timestamp interpretation

- Supported calendar-date ISO-8601 profile: `YYYY-MM-DDTHH:MM:SS[.fraction][Z|±HH:MM]`.
- Date and time components use fixed-width ASCII digits. Fractional seconds, when present, contain one or more digits. Use uppercase `T` and `Z`.
- Offset-aware timestamps represent absolute instants and are normalized to UTC. Offset-free timestamps are interpreted as UTC, never host-local time.
- Reject impossible dates, times and offsets. A date alone is not a timestamp. Leap-second notation and `24:00:00` are not supported.
- Preserve fractional-second precision for comparison; do not silently truncate digits beyond datetime's microsecond resolution.
- Do not use floating-point POSIX timestamps for ordering.
- Normalize report timestamps to UTC with `Z`, retaining meaningful fractional digits and omitting insignificant trailing zeros.

## 6. Reconciliation and exact arithmetic

For each order, use every validated fill whose normalized `order_id` matches that order. Input-row order must not influence results.

Let:

- `Q` be ordered quantity.
- `F = sum(fill.quantity)` be total filled quantity.
- `N = sum(fill.quantity * fill.price)` be executed quote-currency notional.
- `L` be order limit price.
- `s = +1` for BUY and `s = -1` for SELL.

Classify each order exclusively:

| Condition | Status |
| --- | --- |
| `F == 0` | `UNFILLED` |
| `0 < F < Q` | `PARTIALLY_FILLED` |
| `F == Q` | `FILLED` |
| `F > Q` | `OVERFILLED` |

- Remaining quantity is exactly `Q - F`. Preserve negative remaining quantity for overfills.
- Fill count is the number of matching fills.
- For `F > 0`, VWAP is `N / F`.
- For `F == 0`, VWAP and both slippage metrics are absent: JSON `null`, empty CSV cells and a clear console placeholder. Filled quantity, executed notional and fill count are zero.
- Statistics apply to partially filled and overfilled orders as well as exactly filled orders. Include all executed quantity; never cap it at ordered quantity.
- Orphans contribute to no order's quantities or statistics.
- Above-limit BUY fills and below-limit SELL fills remain valid input; slippage represents their execution quality.

### FX units and sign convention

Pip size is `0.01` when the quote currency is `JPY`; otherwise it is `0.0001`.

For `F > 0`:

```text
slippage_pips  = s * (VWAP - L) / pip_size
               = s * (N - L * F) / (F * pip_size)
slippage_quote = s * (N - L * F)
```

**Positive slippage is adverse; negative slippage is favorable.** BUY executions above the limit and SELL executions below the limit have positive slippage. Monetary slippage is signed quote-currency value over all executed quantity, not a per-unit difference.

### No silent intermediate rounding

- Quantities, prices, sums, products, comparisons, remaining quantities and monetary slippage must be exact decimal computations.
- Neither the default Decimal precision nor an arbitrary larger fixed precision is a correctness guarantee. Derive sufficient local precision with arithmetic traps, or use an equivalent exact decimal-coefficient strategy.
- Represent VWAP and slippage in pips as explicit exact numerator/denominator pairs of Decimal values until rendering. Denominators must be positive.
- Do not reuse rendered VWAP in another calculation. Compute monetary slippage directly from the exact signed notional difference.
- Only final presentation of VWAP and slippage in pips may round: at most **12 fractional digits**, `ROUND_HALF_EVEN`, with trailing zeros removed.
- Expose `vwap_rounded` and `slippage_pips_rounded`; a flag is true only when the displayed value differs from the exact ratio. Both flags are false for absent metrics.
- Render quantities, prices, executed notional and monetary slippage exactly, without display quantization. Use plain decimal notation, omit unnecessary trailing fractional zeros and normalize signed zero to `0`.
- Never change the global Decimal context or convert financial values to floats.

## 7. Reporting contracts

### Determinism

For identical file contents and reporting options, financial report bytes and reconciliation exit status must be identical when I/O succeeds, independently of timezone, locale, current time, hash seed or platform line endings.

- Sort orders lexicographically by normalized `order_id`, using case-sensitive Python string ordering.
- Sort orphans lexicographically by normalized `fill_id`.
- Use fixed field/column order, UTF-8 and LF line endings.
- Financial reports must not contain generation times, durations, machine paths, log filenames or random identifiers.
- Operational logs intentionally contain run timestamps and are excluded from report-byte determinism. Clock changes must not change financial results.

### Human-readable report

Print a readable summary with exactly these counters:

- total orders
- filled
- partially filled
- unfilled
- overfilled
- orphan fills

The four order-status counters are mutually exclusive and sum to total orders. Print one detailed row per order with identity, status, ordered/filled/remaining quantity, fill count, VWAP, slippage in pips, signed monetary slippage and quote currency. Include a detailed orphan section when orphans exist. Clearly identify positive-adverse slippage, the final-only rounding policy and rounded values.

Escape user-provided control characters rather than sending terminal escape sequences verbatim. No particular decorative table layout is required, but it must be readable and deterministic.

### Detailed CSV report

Exact column order:

```text
order_id,order_timestamp,currency_pair,side,order_quantity,limit_price,filled_quantity,remaining_quantity,status,fill_count,executed_notional,vwap,slippage_pips,slippage_quote,quote_currency,vwap_rounded,slippage_pips_rounded
```

- Include every order. With zero orders, emit the header only.
- Use empty cells for absent metrics and lowercase `true`/`false` for flags.
- This is a per-order report. Orphans appear in console/JSON and affect the exit code; do not insert another table into the CSV.
- Quote correctly and preserve identifiers without spreadsheet-oriented mutation.

### JSON report

Top-level fields:

- `report_schema_version`: string `1.0`.
- `summary`: integer counters `total_orders`, `filled`, `partially_filled`, `unfilled`, `overfilled`, `orphan_fills`.
- `arithmetic`: `derived_decimal_places: 12`, `rounding: ROUND_HALF_EVEN`, `slippage_convention: positive_is_adverse`.
- `orders`: sorted array of objects using the CSV column names above.
- `orphan_fills`: sorted array of objects with `fill_id`, `order_id`, normalized `timestamp`, `quantity`, `price`, and `reason: UNKNOWN_ORDER`.

All financial decimal fields are JSON strings, not numbers. Counts are integers, flags are booleans and absent metrics are `null`. Use recursively sorted object keys, compact separators `(',', ':')`, unescaped Unicode encoded as UTF-8, and exactly one trailing LF. Reject NaN/Infinity serialization.

## 8. Architecture and boundaries

Suggested package boundaries:

```text
src/fx_reconciler/
  models.py          # Typed input, ratio and report-domain values
  validation.py      # Decimal, timestamp and field validation
  csv_input.py       # CSV structure and source-location diagnostics
  reconciliation.py # Pure aggregation, classification and exact ratios
  reporting.py      # Deterministic console, CSV and JSON serializers
  logging_setup.py  # Run-log destination, structured formatter and lifecycle
  cli.py            # Arguments, I/O orchestration and exit codes
  __main__.py        # Thin module entry point
```

Equivalent naming is allowed; separation is mandatory.

- Domain reconciliation accepts validated objects and has no filesystem, console, CLI, clock or JSON dependencies.
- Parsers return records or structured validation failures; they do not print or terminate the process.
- Serializers consume completed results, do not read inputs, and do not change calculations.
- The CLI owns I/O, logging lifecycle and mapping known failures to exit codes.
- Use immutable typed domain objects where practical. Model exact ratios explicitly rather than storing rounded domain results.
- Application-wide logging must respect these boundaries: log orchestration stages and structured results/errors at adapters; pure calculations need not perform logging I/O.

## 9. Structured logging contract

### Default location and per-run files

- For this application, the **application directory** is the filesystem directory containing the installed `fx_reconciler` package's `__init__.py`, not the current working directory, console-script directory or Python executable directory.
- The default log directory is `<application_directory>/logs`. In an editable `src/` installation this is `src/fx_reconciler/logs`.
- `--log-dir DIRECTORY` is the explicit override. Create the selected directory, including missing parents, if possible.
- If the default installation location is read-only, return `3` with a useful stderr diagnostic suggesting a writable `--log-dir`. Never silently redirect logs to another directory.
- Create one new UTF-8 JSON Lines file for each syntactically valid reconciliation invocation, including invocations whose input is invalid.
- Filename pattern: `fx-reconcile-YYYYMMDDTHHMMSS.ffffffZ.jsonl`, using the run-start UTC timestamp. On collision, append an integer suffix before `.jsonl` and retry exclusive creation, retaining the UTC timestamp. Never append to or truncate an existing run's file.
- Keep the selected run log open for that invocation and close it on success and handled failure. Do not configure or create files at module import time.

### Record schema and coverage

Every log record is one JSON object followed by LF with these fields:

- `timestamp`: UTC ISO-8601 timestamp ending in `Z`.
- `level`: uppercase severity such as `INFO`, `WARNING` or `ERROR`.
- `event`: stable machine-readable event name.
- `stage`: workflow stage.
- `message`: concise controlled text, not arbitrary input content.
- `details`: object containing appropriate structured metadata such as input kind, counts, error category, field name, source line number or exit code.

Required coverage:

- Run start and intended reporting mode.
- Orders/fills ingestion and validation start/completion, with validated record counts.
- Validation failures with error category and safe location metadata.
- Reconciliation start/completion, including status and orphan counts.
- A warning-level reconciliation-break event when overfills or orphans exist.
- Serialization readiness and requested CSV publication success/failure.
- Stdout publication success/failure and run completion with final exit code when logging remains available.
- Expected operational failures at the responsible stage.

Do not log every financial row. Logs must not contain raw CSV rows, financial amounts, order/fill IDs, arbitrary exception representations, credentials or entire file contents. Detailed user-facing validation diagnostics remain on stderr; log controlled categories and safe metadata instead. Bound and escape any variable diagnostic fragments. Do not include machine-specific absolute paths in committed examples or artifacts.

Use standard-library logging with an application-owned logger/handler. File logs must not leak to stdout/stderr through root-logger propagation. All timestamps, including filenames, must be explicitly UTC regardless of host timezone. Flush stage-completion and error records so they are inspectable after a handled failure.

Log creation, writing, flushing or closing failures are operational failures with exit `3`. If logging itself fails, use a bounded stderr diagnostic rather than recursive logging attempts. Files left by interrupted or failed runs may contain only completed records; do not promise crash-proof logging.

Logs are not automatically deleted or rotated. README must document location, naming, the writable-directory override and operator-managed retention. Ignore runtime logs in version control and package distributions.

## 10. Persistence, file safety and security

- No database, cache, background service, runtime network access or telemetry.
- Read inputs without modifying them. Runtime writes are limited to the required run log and a CSV report when `--output` is supplied.
- Refuse CSV destinations that alias either input, including resolved paths and existing same-file aliases. Also reject a destination aliasing the active run log.
- Existing non-input, non-log output files may be replaced; document this behavior.
- Write CSV through a sibling temporary file and atomically replace the destination only after successful serialization and close. Clean temporary files on handled failures.
- Publish requested CSV before stdout so an export failure does not announce successful completion on stdout.
- Invalid input must leave an existing CSV report unchanged.
- Create log files exclusively; never truncate an existing file or follow an existing log-file symlink. Logging must not modify inputs or reports.
- Treat CSV values and path arguments as untrusted data: no evaluation, shell execution, dynamic code loading or executable deserialization.
- Bound and escape diagnostics. Expected errors must not expose raw tracebacks or dump records into logs.
- Preserve identifiers in CSV. Document that spreadsheet software can interpret untrusted string cells as formulas and that such fields should be imported as text; do not silently prefix or mutate identifiers.

## 11. Milestones and dependencies

### M1 — Domain model, CSV parsing and validation

Deliver packaging scaffolding, typed domain objects, exact numeric/timestamp parsing, CSV loaders, structural validation, source-location diagnostics and synthetic fixtures.

Acceptance: valid fixtures load without precision loss; invalid inputs fail with located errors; timezone normalization and high-precision fractional chronology are tested; duplicate IDs are never discarded; known-parent chronology is validated.

### M2 — Reconciliation engine and FX execution quality

Depends on M1. Deliver pure reconciliation, all statuses, orphan retention, exact totals and remaining quantity, exact-ratio VWAP/pips, signed monetary slippage and explicit final-rendering precision support.

Acceptance: hand-calculated BUY/SELL and EURUSD/USDJPY cases pass; overfills retain every fill and negative remaining quantity; nonterminating ratios do not contaminate monetary results; fill ordering and ambient Decimal precision cannot change results.

### M3 — CLI, reporting, logging, examples, documentation and CI

Depends on M1 and M2. Deliver both entry points, deterministic human/CSV/JSON serializers, safe CSV publication, structured UTC run logs, exit behavior, realistic examples, README and GitHub Actions CI on Python 3.14.

Acceptance: installed CLI works end to end; golden CSV/JSON bytes are stable; all exit codes and logging failure paths are tested; default and overridden log locations and UTC filename/record timestamps are verified; examples regenerate documented reports; CI installs the package and runs the complete suite.

## 12. Tests, documentation and final acceptance

The automated suite must include:

- A fully filled order from one fill and from several partial fills.
- Partially filled, unfilled and overfilled orders.
- Orphans, including malformed orphans and duplicate IDs among orphans.
- Duplicate order IDs and duplicate fill IDs, including duplicates shared between matched and orphan fills.
- Invalid timestamps, equivalent offsets, offset-free UTC, equal order/fill times, earlier fills and sub-microsecond chronological differences.
- EURUSD and USDJPY pips, plus another non-JPY quote currency.
- BUY/SELL favorable, adverse and zero slippage; metrics for partial and overfilled orders.
- High-precision decimals, scientific notation, nonfinite values, exact multiplication/aggregation, low ambient Decimal precision and nonterminating VWAP.
- Remaining quantity, absent metrics, final half-even rounding and exact rounding flags.
- Malformed CSV, missing/duplicate/unexpected headers, wrong-width records, BOM, whitespace, quoted fields, header-only files and unreadable inputs.
- Deterministic CSV/JSON bytes across repeated runs, row permutations, timezone changes and Decimal-context changes.
- JSON decimal-string types, CSV escaping, LF endings and safe human control-character rendering.
- CLI exits `0`, `1`, `2`, `3`, stdout/stderr separation, both installed entry points and combined `--json --output`.
- Input/output alias refusal, active-log/output alias refusal, atomic-write failures and preservation of an existing report on invalid input.
- Default application-relative logging, custom log directories, UTC filename and record timestamps, distinct files for repeated/colliding runs and absence of import/help logging side effects.
- Structured lifecycle coverage on clean, broken and invalid runs; logger isolation from report streams; exclusion of raw identifiers, amounts and rows from logs.
- Log-directory creation, unwritable destinations and injected log write/flush/close failures producing exit `3` without raw tracebacks or recursive logging.
- Financial report invariance when the injected logging clock or log directory changes.

Hand-calculated anchors:

- BUY EURUSD, quantity `100000`, limit `1.1000`, fills `40000 @ 1.1001` and `60000 @ 1.1003`: VWAP `1.10022`, slippage `2.2` pips, monetary slippage `22` USD.
- SELL USDJPY, quantity `100000`, limit `150`, fills `60000 @ 149.98` and `40000 @ 150.01`: VWAP `149.992`, slippage `0.8` pips, monetary slippage `800` JPY.

Final repository contents: `SPEC.md`, `AGENTS.md`, installable application, comprehensive automated tests, realistic synthetic fixtures, example inputs, generated example reports, README and a GitHub Actions workflow running the full suite.

README must explain Python 3.14 installation, both CSV schemas, supported timestamp/numeric syntax, units, reconciliation rules, negative remaining quantity, exact arithmetic and final-only rounding, positive-adverse slippage, orphan treatment, all exit codes, atomic CSV overwrite behavior, spreadsheet import precautions and runnable clean/broken/invalid examples. Explain log schema, UTC naming, default application-relative directory, `--log-dir`, read-only-installation behavior and retention. Examples must not require writing to an unwritable installed package directory.

Final acceptance requires the complete suite and installed CLI checks to pass under Python 3.14, with successful GitHub Actions CI. This draft does not claim any commands, tests or CI have been executed.
