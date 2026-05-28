# MINOS-CORE Development Guidelines

## Project Overview

MINOS-CORE is an AI-driven three-table generation tool for APQP workflows. It processes engineering drawings (PDF/images) and generates:
- Process Flow Diagram (PFD)
- Process Failure Mode and Effects Analysis (PFMEA)
- Control Plan (CP)

**Main workflow:**
```
drawing PDF/image → render page evidence → AI drawing analysis
→ infer_process_flow_from_drawing → infer_pfmea_from_process_flow
→ generate_control_plan_from_pfmea → quality gates → export three tables
```

**One-command backend entry:**
```bash
python -m minos_core.cli generate-three-tables --input path/to/drawing.png --output-dir out/case001
```

## Architecture

4-layer structure:
- **Tauri Frontend** → FastAPI Desktop Sidecar → Desktop Services (SQLite) → Core Library (Pipeline)

See `docs/architecture/README.md` for details.

---

## Security Requirements

### Secrets Management
- **NEVER commit API keys, tokens, or credentials** to version control
- All AI configuration must use:
  - Environment variables (e.g., `MINOS_OPENAI_API_KEY`)
  - Codex config files (excluded from git)
- Check `.gitignore` includes:
  ```
  *.pem
  *.key
  *.crt
  secrets.json
  credentials.json
  auth.json
  .env
  *.sqlite3
  *.db
  ```

### Logging and Observability
- **Use structured logging (structlog), NEVER use print()**
  ```python
  import structlog
  logger = structlog.get_logger(__name__)
  
  # Good
  logger.info("processing_file", file_path=str(path), size=file_size)
  
  # Bad
  print(f"Processing {path}")
  ```

- **Redact sensitive data in all logs and diagnostics**
  ```python
  from minos_core.observability.redaction import redact_sensitive_data
  
  logger.info("api_response", data=redact_sensitive_data(response_data))
  ```

### Input Validation
- Validate all user inputs at system boundaries
- Use `minos_core.validation.InputValidator` for:
  - Path traversal protection: `InputValidator.validate_path_traversal(path, base_dir)`
  - SQL injection prevention: Use parameterized queries or whitelist validation
- Never trust external data (API responses, user uploads, file content)

### HTTPS and SSL
- All external HTTP requests must use HTTPS with certificate verification
- Exception: localhost development (127.0.0.1, ::1) may use HTTP
- Use `ssl.create_default_context()` for certificate validation

---

## Testing

### Running Tests
```bash
# Run all tests
python -m unittest discover -s tests -v

# Run specific test file
python -m pytest tests/desktop/services/test_project_store.py -v

# Run with coverage
pytest --cov=minos_core --cov=minos_desktop --cov=minos_platform --cov-report=html
```

### Test Requirements
- **Minimum 80% code coverage required**
- All new features must include tests (TDD approach)
- Test structure:
  - Unit tests: Individual functions, utilities, domain models
  - Integration tests: API endpoints, database operations, service interactions
  - E2E tests: Complete workflows (create project → run analysis → export)

### Real API Tests
- Real API tests (calling OpenAI, etc.) only run in CI with:
  ```bash
  export MINOS_RUN_REAL_ACCEPTANCE=1
  ```
- Local tests should use mocks or fixtures
- Use `@pytest.mark.skipif(not os.getenv("MINOS_RUN_REAL_ACCEPTANCE"), reason="...")` for real API tests

### Test File Organization
- Keep test files under 800 lines
- Split large test files by service/module:
  ```
  tests/desktop/services/test_project_store.py
  tests/desktop/services/test_run_service.py
  tests/desktop/services/test_settings_store.py
  ```

---

## Dependencies

### Version Management
- **Always pin versions with upper bounds** in `pyproject.toml`:
  ```toml
  dependencies = [
      "structlog>=24.1.0,<25.0",
  ]
  
  [project.optional-dependencies]
  desktop-api = [
      "fastapi>=0.100,<1.0",
      "uvicorn>=0.23,<1.0",
  ]
  ```

### Dependency Verification
- **Run `pip check` before committing dependency changes**
- Verify no conflicts:
  ```bash
  pip install -e ".[desktop-api,platform,ocr]"
  pip check
  ```

### Optional Dependencies
- `desktop-api`: FastAPI, Uvicorn, SSE-Starlette
- `platform`: SQLAlchemy, aiosqlite
- `ocr`: PyMuPDF, Pillow, RapidOCR, ONNX Runtime

---

## Code Style

### Immutability
- **Use immutability patterns (no in-place mutations)**
  ```python
  # Good - return new object
  def update_status(record: dict, new_status: str) -> dict:
      return {**record, "status": new_status}
  
  # Bad - mutate in place
  def update_status(record: dict, new_status: str) -> None:
      record["status"] = new_status
  ```

### Function and File Size
- **Functions < 50 lines**
- **Files < 800 lines**
- Extract utilities and helpers when files grow large
- Organize by feature/domain, not by type

### Error Handling
- **Explicit error handling, no silent failures**
  ```python
  # Good
  try:
      result = risky_operation()
  except SpecificError as e:
      logger.error("operation_failed", error=str(e))
      raise
  
  # Bad
  try:
      result = risky_operation()
  except:
      pass  # Silent failure
  ```

### Naming Conventions
- Variables and functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

---

## CLI Commands

### Core Commands
```bash
# Generate three tables from drawing
python -m minos_core.cli generate-three-tables --input drawing.png --output-dir out/

# List available samples
python -m minos_core.cli list

# Run diagnostics
python -m minos_core.cli doctor

# Desktop API server
python -m minos_desktop.api.cli --port 8080 --db-path data/minos.db --output-dir out/
```

---

## Quality Gates

### Pre-Commit Checklist
- [ ] All tests pass (`python -m unittest discover -s tests -v`)
- [ ] Coverage >= 80% (`pytest --cov`)
- [ ] No hardcoded secrets or credentials
- [ ] No `print()` statements (use `structlog`)
- [ ] Dependencies have upper bounds
- [ ] `pip check` passes
- [ ] No files > 800 lines
- [ ] No functions > 50 lines

### Code Review Focus
- Security: SQL injection, path traversal, HTTPS validation
- Error handling: Explicit error messages, no silent failures
- Testing: New code has tests, edge cases covered
- Logging: Structured logs with sensitive data redaction
- Immutability: No in-place mutations

---

## Common Patterns

### Repository Pattern
- Encapsulate data access behind consistent interfaces
- Standard operations: `find_all()`, `find_by_id()`, `create()`, `update()`, `delete()`
- Example: `minos_desktop.services.project_store.ProjectStore`

### Service Layer
- Business logic in service classes
- Services coordinate between repositories and domain models
- Example: `minos_desktop.services.run_service.DesktopRunService`

### Domain Models
- Immutable dataclasses in `minos_core.domain`
- Use `@dataclass(frozen=True)` for immutability
- Factory methods: `from_mapping()`, `from_dict()`

---

## Troubleshooting

### Build Failures
```bash
# Check Python version (requires >=3.11)
python --version

# Reinstall dependencies
pip install -e ".[desktop-api,platform,ocr]"

# Run diagnostics
python -m minos_core.cli doctor
```

### Test Failures
```bash
# Run specific test with verbose output
python -m pytest tests/path/to/test_file.py::test_function_name -v -s

# Check test isolation (run in random order)
python -m pytest tests/ --random-order
```

### Database Issues
```bash
# Check database schema version
sqlite3 data/minos.db "SELECT version FROM schema_version;"

# Reset database (WARNING: deletes all data)
rm data/minos.db
python -m minos_desktop.api.cli  # Will recreate on startup
```

---

## File Paths and Conventions

### Project Structure
```
D:/MINOS-CORE/
├── minos_core/           # Core library (pipeline, domain, adapters)
├── minos_desktop/        # Desktop services and API
├── minos_platform/       # Platform services (future)
├── tests/                # Test suite
├── docs/                 # Documentation
├── samples/              # Sample inputs and expected outputs
└── pyproject.toml        # Project configuration
```

### Output Conventions
- Draft outputs: `*_draft.xlsx`, `*_draft.json`
- Final outputs: `*_final.xlsx`, `*_final.json`
- Manifests: `run_manifest.json`, `three_table_generation_result.json`

---

## Plugin System

MINOS-CORE supports plugins for:
- OCR engines (`minos_core.plugins.ocr`)
- Knowledge sources (`minos_core.plugins.knowledge`)

See `docs/plugins.md` and `docs/adr/005-extensibility.md` for details.

---

## References

- Architecture: `docs/architecture/README.md`
- Module Map: `docs/architecture/modules.md`
- Data Flow: `docs/architecture/data-flow.md`
- ADRs: `docs/adr/`
- v3.1.0 Security Fixes: `C:\Users\fgtan\.claude\plans\skill-fizzy-raccoon.md`
