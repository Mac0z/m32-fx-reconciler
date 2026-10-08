# AGENTS.md

## 1. Authority and working rules

- Read `SPEC.md` before implementing or changing behavior. SPEC is the product source of truth; this file is the implementation-policy source of truth.
- Implement M1, M2 and M3 in order, retaining earlier tests and documentation.
- Do not weaken validation, discard records, change financial conventions or disable required logging to make tests pass.
- Treat explicit defaults in SPEC as decisions, not blockers. Stop and report a genuinely blocking contradiction rather than inventing a requirement or claiming compliance.
- Keep the repository **public**. Commit only synthetic financial fixtures, examples and artifacts.
- Do not claim commands, tests or CI passed unless actually executed successfully.

## 2. Architecture and implementation boundaries

- Use an installable `src/fx_reconciler/` package and `pyproject.toml`.
- Separate domain models/reconciliation, input validation/CSV loading, report rendering, logging infrastructure and CLI orchestration. Preserve the boundaries even if modules are renamed.
- Prefer small immutable dataclasses and explicit typed result/error objects. Use type hints throughout code and tests.
- Pure domain functions must not access files, print, read environment variables, read the clock, configure logging or terminate the process. Inject validated data and return results.
- Loaders return validated records or structured errors and preserve source locations for diagnostics and duplicate detection.
- Renderers consume completed domain results and return deterministic text/bytes or write through a narrow injected destination. They must not change calculations.
- Keep entry points thin and route both through the same CLI implementation.
- Only CLI orchestration maps expected failures to exit codes. Avoid broad exception handling that hides programming defects.
- Cover application stages through adapter/orchestration logging, not filesystem logging inside pure arithmetic helpers.
- Avoid ambient configuration, global mutable registries and unnecessary frameworks.

## 3. Financial arithmetic invariants

- Use `Decimal` for parsed quantities and prices. Never construct Decimal from float or route financial arithmetic through floats.
- Reject nonfinite values before comparisons or aggregation.
- Preserve parsed decimal values exactly. Formatting must not use context-sensitive normalization that accidentally rounds them.
- Do not assume default precision or an arbitrary large fixed precision makes sums/products exact. Derive sufficient local precision or use exact coefficient arithmetic, retaining Decimal-valued public domain fields.
- Use local contexts and traps for unintended `Inexact`/`Rounded` results where exact operations are expected. Never mutate the global Decimal context.
- Keep VWAP and pips as explicit exact numerator/denominator pairs with positive denominators until rendering.
- Compute signed monetary slippage directly from `executed_notional - limit_price * filled_quantity`, not rounded VWAP.
- Round derived ratios only once, in final rendering, using the SPEC half-even policy. Determine flags against exact ratios, not digit counts. Integer-scaled exact division is permitted in the renderer.
- Preserve negative remaining quantity and all fills for overfilled orders.
- Test correctness with deliberately low ambient precision and operands needing more than default precision.

## 4. Parsing and validation

- Use standard-library CSV parsing, `pathlib.Path`, UTF-8 BOM-aware input and explicit newline handling.
- Validate headers before records. Detect duplicate names after trimming; do not let a dictionary overwrite them.
- Detect duplicate order/fill IDs without overwriting records; retain both source locations.
- Use identical trimming and comparison rules for parent references and order declarations.
- Distinguish structural errors, field errors, duplicate IDs, chronology errors and valid orphans.
- Validate every orphan independently. Unknown parents do not excuse malformed quantities, prices, IDs or timestamps.
- Use UTC instants independent of host timezone. Preserve arbitrary fractional-second precision supported by SPEC instead of accepting datetime truncation.
- Never use floating-point POSIX timestamps for financial chronology.
- Keep diagnostics stable, useful, bounded and escaped. Use controlled previews rather than raw file/record dumps.
- Fail closed on invalid input. Never reconcile a subset and present it as complete.

## 5. Reporting and filesystem safety

- Centralize canonical decimal, timestamp and ratio rendering so console, CSV and JSON agree.
- Follow SPEC sorting, CSV columns, JSON schema, compact separators, null semantics, flags and UTF-8/LF policy exactly.
- JSON financial decimals are strings; counts and flags retain integer/boolean types.
- Financial reports must not contain the current clock, elapsed time, machine paths, log paths or nondeterministic identifiers.
- Escape terminal control characters in human output. Preserve identifiers using proper CSV/JSON escaping in machine output.
- Reserve stdout for the selected report. Send expected diagnostics to stderr; do not add logs or banners to either report format.
- Validate output/input and output/active-log aliases before CSV writing, including resolved paths and existing same-file aliases.
- Use a sibling temporary CSV file and atomic replacement. Clean temporary files on handled failures and preserve existing reports on invalid input.
- Publish requested CSV before stdout. Do not promise rollback across a completed CSV replacement, later logging and stdout.
- Never modify inputs through symlink, hard-link or resolved-path aliases.
- Preserve spreadsheet-like identifiers rather than silently sanitizing them. Document importing untrusted string columns as text.
- Keep expected I/O failures traceback-free with narrow exception handling.

## 6. Structured logging policy

- Implement SPEC's required per-run JSON Lines logging using standard-library logging and a dedicated application-owned logger/handler.
- Do not configure root logging, propagate file events into console handlers or create log files during import.
- Resolve the default directory from the installed package location: the directory containing `fx_reconciler/__init__.py`, followed by `logs`. Do not substitute the working directory, console-script directory, Python executable location or a home directory.
- Support the explicit `--log-dir` override. If the default directory is unwritable, fail with code `3` and suggest the override; never silently disable or relocate logging.
- Initialize logging after valid argument parsing and before input loading. `--help` and argument errors must not require log-file creation.
- Use timezone-aware UTC for every record timestamp and the timestamped filename. Do not depend on localtime formatter defaults.
- Create run files exclusively with the SPEC name pattern; handle timestamp collisions with exclusive-create numeric suffix retries. Never truncate, append to or follow an existing log-file symlink.
- Emit stable events for run start, ingestion/validation, reconciliation, breaks, serialization, publication and completion. Include appropriate counts, categories, stages and exit codes, not raw financial records.
- Keep log messages controlled and metadata typed. Never log order/fill IDs, quantities, prices, complete rows, raw exception representations or credentials.
- Respect pure-domain boundaries: log lifecycle and returned results/errors at adapters or orchestration. Do not add hidden clock or logging I/O to financial functions.
- Inject or wrap the UTC clock and narrow log destination interfaces for tests. Do not expose test-only clock controls as public CLI options.
- Flush completed stage/error records and close handlers on success and handled failure. Keep logger state scoped to the invocation so repeated calls do not duplicate handlers.
- Treat create/write/flush/close failures as code `3`. If the logging mechanism fails, report directly to stderr without recursive attempts. Stop further report publication; do not pretend previously emitted bytes can be retracted.
- Exclude runtime logs from version control, source/wheel distributions and ordinary published artifacts. Do not add unrequested rotation, cleanup jobs or remote log transport.

## 7. Dependency and compatibility policy

- Target and test Python 3.14. Do not substitute an older interpreter because tooling is inconvenient.
- Runtime dependencies are standard-library only unless SPEC is explicitly amended.
- Use pytest and a minimal build backend. Avoid numerical, dataframe, timezone, CLI or structured-logging libraries for standard-library problems.
- Select compatible released build/development dependency versions and record them in `pyproject.toml` or reproducible development dependency configuration. Do not invent package versions or action hashes.
- Added tools must solve a demonstrated problem and work on Python 3.14. Do not introduce databases, remote services, telemetry or network clients.
- Document reproducible install/test commands. Do not rely on undeclared global packages or a `PYTHONPATH` workaround to hide broken installation.

## 8. Tests and fixtures

- Build unit tests for validators and pure calculations, serializer contract tests, logging tests and subprocess integration tests for the installed CLI.
- Implement every SPEC test category. Do not replace requested automated cases with manual examples.
- Use hand-calculated expected values, not production helpers to compute expectations.
- Cover single/multiple fills, every status, valid/malformed orphans, duplicate-ID variants, timestamp errors, BUY/SELL symmetry and JPY/non-JPY pips.
- Include repeating-ratio and exact half-even cases proving display rounding and exact monetary results.
- Test Decimal-context independence, timezone independence and input/fill permutation invariance.
- Compare deterministic CSV/JSON as bytes, including field ordering, escaping, decimal strings and trailing LF.
- Exercise codes `0`, `1`, `2`, `3`, both entry points, separate stdout/stderr and combined `--json --output`.
- Test failed writes, aliases and atomic replacement with temporary directories and controlled failure injection.
- Test logging across clean, broken, invalid and operational-failure runs. Verify JSONL schema, required stage events, UTC timestamps, correct location, per-run filenames and collision behavior.
- Verify reports contain no logging messages or clock-dependent data; change the injected logging clock and confirm identical financial outputs.
- Assert that logs exclude identifiable financial values and raw rows, including on validation failures.
- Test unwritable log directories and write/flush/close failures without relying solely on permission bits that behave differently under privileged users or different operating systems.
- Verify `--help`, argument errors and imports create no logs. Verify repeated in-process invocations do not accumulate handlers.
- For normal subprocess tests, pass a temporary `--log-dir` so installed packages need not be writable. Separately test default path resolution in a controlled writable installation/location.
- Keep fixtures small, realistic, synthetic and reviewable. Maintain distinct clean, reconciliation-break and invalid datasets.
- Tests must be hermetic: no network, live broker, real customer data or dependence on host timezone/current time. Production logging reads UTC time; tests control it where assertions require exact values.
- Do not weaken assertions, omit failures or regenerate goldens without reviewing semantics.

## 9. CI

- Commit a GitHub Actions workflow running on pushes and pull requests.
- Select explicit Python `3.14`, install the package and declared test dependencies, then run the complete pytest suite without deselecting integrations or logging tests.
- Include installed-entry-point smoke tests. Use a writable temporary log directory; do not test only directly imported source files.
- Additional compatible declared lint/type checks may supplement but not replace the full suite.
- Use minimal permissions, normally `contents: read`, and disable persisted checkout credentials when unnecessary.
- Pin third-party actions to verified immutable commit SHAs with version comments. Resolve actual SHAs during implementation; never fabricate them in drafts.
- Do not expose repository secrets to untrusted pull-request code or run contributed code in privileged `pull_request_target` workflows.
- CI needs no service, secret or real financial data. Do not upload unrestricted runtime logs.

## 10. Security and publication

- Treat CSV content and path arguments as untrusted. No `eval`, executable deserialization, shell interpolation or dynamic code loading.
- Do not make application-runtime network calls or send orders/fills/logs to external services.
- Do not commit credentials, customer data, local paths or operational run logs. Review any intentionally published sample log separately and use only synthetic controlled content.
- Use explicit encodings, locale-independent formatting and secure exclusive log creation.
- Keep error previews bounded and escaped. Do not log entire rows or exception objects that may carry raw input.
- Remediate discovered security defects with regression tests and compatible fixes, not undocumented changes to IDs, financial conventions or exit behavior.

## 11. Documentation and definition of done

- Keep README, `--help`, examples, fixtures and outputs aligned with SPEC.
- Document base/quote units, offset-free UTC, supported timestamp syntax, negative remaining quantity, positive-adverse slippage, final-only rounding, orphan treatment, CSV overwrite behavior and every exit code.
- Explain that overfills/orphans are reconciliation breaks; adverse slippage, unfilled orders and partial fills alone do not cause code `1`.
- Document structured logging, UTC timestamps, default package-relative `logs` directory, per-run naming, the writable `--log-dir` override, logging failure code `3` and operator-managed retention.
- Keep nondeterministic operational logs out of golden financial outputs. Example commands should use a clearly writable log directory when appropriate.
- Generate example financial outputs from committed inputs and review them against hand calculations.
- A milestone is done only when implementation, automated acceptance tests and associated documentation are present and passing.
- Final delivery additionally requires successful Python 3.14 CI, installed CLI verification, realistic synthetic examples and comprehensive documentation. Do not claim completion based only on this draft.
