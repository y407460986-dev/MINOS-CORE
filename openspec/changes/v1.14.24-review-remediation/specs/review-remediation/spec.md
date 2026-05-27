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

### Requirement: Enforce company process boundary in PFD generation
The system SHALL apply a global structured company process-boundary profile to PFD generation so the generated flow describes the company's assembly/manufacturing scope and does not expand supplier manufacturing processes.

#### Scenario: supplier forging steps are automatically removed
- **GIVEN** the company process boundary marks forged parts as purchased inputs
- **AND** a generated PFD contains supplier steps such as heating billet, forging forming, forged-part heat treatment, or shot blasting
- **WHEN** the PFD is post-processed
- **THEN** those supplier manufacturing steps are removed from internal PFD steps
- **AND** the remaining internal steps are relinked with valid `process_step_id`, `previous_step_ids`, and `next_step_ids`
- **AND** the metadata records that process-boundary adjustments were applied

#### Scenario: purchased forged parts remain as incoming inspection inputs
- **GIVEN** supplier forging steps were removed
- **WHEN** the first incoming inspection step is inspected
- **THEN** the step mentions the purchased forged part as an incoming material or inspection function
- **AND** downstream in-house steps such as punching, machining, assembly, riveting, inspection, and packaging remain available

### Requirement: Allow editing global company process boundary settings
The desktop settings API and UI SHALL expose the global company process-boundary profile for viewing and editing without creating project-level overrides.

#### Scenario: settings API returns the default boundary
- **GIVEN** no process-boundary setting has been saved
- **WHEN** desktop settings are requested
- **THEN** the response includes `process_boundary_config` with the default enabled company profile

#### Scenario: process boundary patch persists a full profile
- **GIVEN** the settings page submits a full process-boundary profile
- **WHEN** `/api/settings/process-boundary` is patched
- **THEN** the profile is saved to the existing settings store and returned by subsequent settings requests

#### Scenario: empty patch is rejected
- **GIVEN** the settings page or caller sends an empty JSON object
- **WHEN** `/api/settings/process-boundary` is patched
- **THEN** the API rejects it instead of clearing the structure or treating it as restore default

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
