# ADR 004: Observability Foundations

## Status

Accepted

## Context

MINOS-CORE had grown a thicket of `print()` calls, ad-hoc `logging.getLogger`
loggers with inconsistent formatting, bare `RuntimeError` / `ValueError`
raises with no semantic typing, and scattered `tempfile.TemporaryDirectory`
plus `subprocess.run` invocations whose lifecycle was hard to audit. There
was no shared way to report which environment variable (or fallback) supplied
a given configuration value, which made the `minos-core doctor` command
limited to surface checks. Operators who needed to debug failures had to
correlate stdout chunks with random log lines and then guess whether an error
was retriable.

## Decision

Introduce a single `minos_core.observability` package that owns four
concerns:

1. **Structured logging** (`logging.py`). A thin wrapper around `structlog`
   configures a shared processor chain (timestamper, level, logger name,
   caller info, exception formatting) and renders either ISO-timestamped
   JSON or human-readable console output, controlled by `MINOS_LOG_LEVEL`
   and `MINOS_LOG_JSON`. Correlation IDs (`request_id`, `project_id`,
   `run_id`) flow through `contextvars`.
2. **Semantic error hierarchy** (`errors.py`). `MinosError` carries a stable
   `code`, `context`, `retriable` flag, and Chinese-localised
   `user_message_zh`. Subclasses (`ConfigurationError`, `ValidationError`,
   `ExternalServiceError`, `ResourceError`, `PipelineError`) multi-inherit
   from the matching stdlib exception (`RuntimeError` / `ValueError`) so
   existing `except` clauses keep working while callers gain richer types.
3. **Resource context managers** (`resources.py`). `temporary_directory`
   yields a `Path` and tolerates Windows cleanup quirks;
   `managed_subprocess` logs spawn/exit, escalates from `terminate` to
   `kill` after a grace period, and surfaces missing executables as
   `ResourceError` with localised messaging.
4. **Configuration diagnostics** (`config_diagnostics.py`). `describe_config_sources`
   reports key/value/source/detail tuples that `minos-core doctor` renders
   alongside the existing checks. Secrets are redacted to first/last three
   characters plus length.

## Consequences

* Every adapter/pipeline log call can now be parsed by log aggregators
  without bespoke regex.
* `minos-core doctor` answers "where did this value come from?" without
  leaking secrets.
* Existing callers that catch `ValueError` / `RuntimeError` continue to
  function; they can opt into richer typing incrementally.
* `structlog` is a new runtime dependency (>= 24.1.0).
