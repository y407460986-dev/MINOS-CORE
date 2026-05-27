# ADR 001: Module Restructuring for Maintainability

## Status

Accepted

## Context

The MINOS-CORE codebase had several large modules exceeding 800 lines, making them difficult to maintain, test, and understand. Specifically:

- `quality_gates/_support.py`: 728 lines
- `edit_patch.py`: 1339 lines (deferred to future iteration)
- Other modules approaching the threshold

Large modules violate the Single Responsibility Principle and make code navigation, testing, and refactoring more difficult.

## Decision

We will systematically split large modules into smaller, focused modules following these principles:

### Splitting Strategy

1. **Identify cohesive functional groups** within large modules
2. **Extract into separate modules** with clear responsibilities
3. **Maintain backward compatibility** by re-exporting from original module
4. **Keep all modules under 800 lines** as a hard limit

### Implementation: quality_gates/_support.py

Split 728-line `_support.py` into 4 focused modules:

#### 1. `core_evaluators.py` (307 lines)
- Core gate evaluation logic
- Confirmation matching
- Pending field tracking
- AI inference detection
- Flag and label utilities

**Responsibilities:**
- `_metadata_list`, `_strict_aiag_vda_pfmea_gate_enabled`
- `_confirmed_targets`, `_confirmed_field_paths`, `_review_confirmations`
- `_pending_fields`, `_pending_field_paths`
- `_ai_inferred_items`, `_flagged_evidence_ids`, `_flagged_item_labels`
- `_row_needs_confirmation_items`, `_is_mechanical_trace_link`
- `_confirmation_matches_value`, `_is_confirmed`, `_without_confirmed`

#### 2. `evidence_coverage.py` (202 lines)
- Evidence coverage checking
- Evidence validation
- Stage validation

**Responsibilities:**
- `_evidence_coverage_report`, `_ingest_evidence_report`
- `_evidence_sufficient`, `_evidence_manual_review_items`
- `_iter_evidence_required_items`, `_stage_validation`

#### 3. `export_gate.py` (130 lines)
- AI batch confirmation safety checks
- Export gate validation

**Responsibilities:**
- `_with_safe_ai_batch_confirmations`
- `_safe_ai_batch_confirmation_targets`, `_safe_ai_batch_row`
- `_unsafe_ai_batch_review_issues`

#### 4. `report_projections.py` (116 lines)
- Manual review item construction
- Review issue deduplication
- Gate debt reporting

**Responsibilities:**
- `_dict_manual_review_items`, `_recommendation_manual_review_items`
- `_row_needs_confirmation_manual_review_items`
- `_review_issues_from_gate_debts`, `_dedupe_review_issues`

#### 5. `_support.py` (94 lines)
- Re-exports all functions from split modules
- Maintains 100% backward compatibility
- Acts as a facade for the split modules

### Backward Compatibility

The original `_support.py` now serves as a re-export module:

```python
# Re-export from core_evaluators
from .core_evaluators import (
    _ai_inferred_items,
    _confirmation_matches_value,
    # ... all functions
)

# Re-export from evidence_coverage
from .evidence_coverage import (
    _evidence_coverage_report,
    # ... all functions
)

# ... etc
```

This ensures:
- **Zero breaking changes** for existing code
- **Gradual migration path** - consumers can import from new modules when ready
- **No test changes required** - all existing imports continue to work

## Consequences

### Positive

1. **Improved maintainability**: Each module has a clear, focused responsibility
2. **Better testability**: Smaller modules are easier to test in isolation
3. **Enhanced readability**: Developers can quickly find relevant code
4. **Easier refactoring**: Changes are localized to specific modules
5. **No breaking changes**: Backward compatibility maintained via re-exports
6. **Scalable pattern**: Can be applied to other large modules

### Negative

1. **More files**: 4 new files instead of 1 large file
2. **Import overhead**: Slightly more complex import structure (mitigated by re-exports)
3. **Initial learning curve**: Developers need to learn new module structure

### Neutral

1. **File count increase**: From 1 to 5 files (4 new + 1 facade)
2. **Total line count**: Slightly increased due to module headers and imports (~50 lines overhead)

## Future Work

### Immediate Next Steps

1. **Split `edit_patch.py` (1339 lines)** into focused modules:
   - `patch_kernel.py` - Core patch application logic
   - `patch_exports.py` - Export and gate evaluation
   - `patch_metadata.py` - Metadata action handlers
   - `patch_filters.py` - Row filtering and validation

2. **Monitor other large modules** approaching 800 lines:
   - `table_editor.py` (2118 lines) - HIGH PRIORITY
   - `run_service.py` (1987 lines) - HIGH PRIORITY
   - `part_family_knowledge.py` (1374 lines)
   - `pipeline_chain.py` (1236 lines)
   - `drawing_to_pfd.py` (1188 lines)

### Long-term Strategy

1. **Establish module size policy**: Enforce 800-line limit in code review
2. **Automated checks**: Add pre-commit hook to flag large modules
3. **Documentation**: Update contribution guidelines with module splitting best practices
4. **Refactoring sprints**: Dedicate time to systematically address technical debt

## References

- [Single Responsibility Principle](https://en.wikipedia.org/wiki/Single-responsibility_principle)
- [Python Module Best Practices](https://docs.python-guide.org/writing/structure/)
- Track 1 Foundation Branch: `track-1-foundation`
- Related commits:
  - `95a2cfd`: refactor: split quality_gates/_support.py into focused modules

## Decision Makers

- Development Team
- Architecture Review

## Date

2026-05-28
