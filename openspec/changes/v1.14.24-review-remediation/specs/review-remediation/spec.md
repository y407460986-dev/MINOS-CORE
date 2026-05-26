# Review Remediation Spec

## ADDED Requirements

### Requirement: Harden platform and desktop delivery boundaries
The system SHALL default platform APIs to local-only operation, reject unauthenticated non-dev access, protect artifact integrity, redact stored AI secrets from ordinary backups, and block final exports when quality gates have not cleared.

#### Scenario: unauthenticated platform access is rejected by default
- **GIVEN** the platform API starts without an explicit dev auth bypass
- **WHEN** a protected endpoint is requested without a valid token
- **THEN** the API rejects the request instead of serving it anonymously

#### Scenario: failed final gate blocks final export
- **GIVEN** a review result or edited three-table result has `final_export_allowed=false`
- **WHEN** a caller requests `export_mode=final`
- **THEN** the export is rejected and no final workbook is written

#### Scenario: draft export remains available for review
- **GIVEN** the final gate is blocked but draft review artifacts are still needed
- **WHEN** a caller requests a draft export
- **THEN** the system may write draft-marked artifacts without claiming final release

### Requirement: Preserve canonical three-table provenance
The system SHALL expose PFD, PFMEA, and Control Plan bundles with canonical document metadata and row-level provenance fields throughout core generation and result envelopes.

#### Scenario: generated bundles carry row provenance
- **GIVEN** a drawing-driven three-table run produces PFD, PFMEA, and Control Plan rows
- **WHEN** the run result is assembled
- **THEN** each table bundle includes `schema_version`
- **AND** each row includes `schema_version`, `evidence_refs`, `confidence`, `ai_inferred`, and `needs_confirmation`

#### Scenario: special characteristic class is not the characteristic identity
- **GIVEN** a row references a concrete special characteristic such as `SC-001`
- **WHEN** the row is normalized into the canonical bundle
- **THEN** `special_characteristic_class` contains the class such as `SC`
- **AND** `characteristic_refs` keeps the concrete characteristic identity

### Requirement: Persist desktop chain state across long-running stages
The desktop API SHALL persist running and terminal stage state so reconnects and duplicate requests cannot misrepresent the current run.

#### Scenario: reconnect returns persisted terminal state
- **GIVEN** a chain stage has already reached `done` or `failed`
- **WHEN** an SSE client reconnects after the in-memory stream has gone quiet
- **THEN** the API returns the persisted terminal state rather than `not_running`

#### Scenario: invalid stage transitions are rejected
- **GIVEN** a run is not in the expected stage status for confirmation or regeneration
- **WHEN** the corresponding action endpoint is called
- **THEN** the API returns a structured conflict response and does not enqueue a duplicate background job

### Requirement: Make CI and acceptance checks representative
The project SHALL use pytest as the official Python test entry, install the test dependencies CI actually needs, keep real API tests marker-selectable, avoid developer-machine absolute paths, and verify generated Excel files by opening workbooks.

#### Scenario: real API acceptance marker selects a target test
- **GIVEN** CI or a maintainer runs the real API acceptance marker selection
- **WHEN** pytest collects `real_api and acceptance`
- **THEN** at least one intended target test is selected, even if it later skips for missing secrets

#### Scenario: workbook openability is checked
- **GIVEN** the system generates three-table Excel artifacts
- **WHEN** acceptance checks inspect the artifacts
- **THEN** they open the workbook sheets through `openpyxl` instead of only checking zip structure

### Requirement: Defer broad architecture splitting
The system SHALL keep this remediation focused on delivery risk and canonical contracts, while recording the next architecture split points without performing broad refactors in the same pass.

#### Scenario: first remediation pass avoids unrelated rewrites
- **GIVEN** security, state, and canonical contract work is in progress
- **WHEN** large modules such as `pipeline.py`, `quality_gates`, or `DesktopRunService` expose unrelated cleanup opportunities
- **THEN** the remediation records the follow-up split and avoids expanding the implementation scope

#### Scenario: quality gate side effects are tracked for migration
- **GIVEN** quality gate code derives review issue projections, knowledge recommendation display items, or automatic confirmation payloads
- **WHEN** the architecture follow-up is planned
- **THEN** those projections are listed for migration outside pure gate judgment
