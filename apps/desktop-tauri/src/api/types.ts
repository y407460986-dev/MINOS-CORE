export type HealthResponse = {
  ok: boolean;
  status?: string;
  service?: string;
  version?: string;
};

export type BootstrapPayload = {
  appName: string;
  version: string;
  apiBaseUrl: string;
  apiToken?: string;
  sidecarManaged: boolean;
  workspaceRoot?: string;
};

export type TableKind = "pfd" | "pfmea" | "cp";

export type RiskLevel = "low" | "medium" | "high";

export type RowStatus = "draft" | "review" | "approved";

export type DrawingAnalysisMode = "hybrid" | "ocr_only" | "vision_only";

export type CreateProjectRequest = {
  project_name: string;
  drawing_path: string;
  component_drawings?: string[];
  output_dir?: string;
  context?: Record<string, unknown> & {
    analysis_mode?: DrawingAnalysisMode;
    ocr_engine?: string;
  };
};

export type WorkbenchRow = {
  id: string;
  table: TableKind;
  process: string;
  characteristic: string;
  risk: RiskLevel;
  status: RowStatus;
  owner: string;
  evidence: string;
  linkedRows: string[];
  rowId: string;
  rowIdField: string;
  raw: Record<string, unknown>;
};

export type ProcessFlowStep = {
  process_step_id?: string;
  id?: string;
  step_id?: string;
  flow_symbol?: string;
  flow_type?: string;
  flow_type_display?: string;
  operation_type?: string;
  operation?: string;
  process_step?: string;
  process_item?: string;
  input_material?: unknown;
  output_result?: unknown;
  previous_step_ids?: unknown;
  equipment?: unknown;
  next_step_ids?: unknown;
  [key: string]: unknown;
};

export type DesktopProject = {
  id: number;
  project_name: string;
  drawing_path: string;
  output_dir: string;
  context: Record<string, unknown>;
};

export type DesktopRun = {
  id: number;
  project_id: number | null;
  status: string;
  status_display: string;
  blocked_stage?: string | null;
  manual_review_required?: boolean;
  manual_review_count?: number;
  output_dir: string;
  raw_result?: Record<string, unknown>;
  current_result: Record<string, unknown>;
  chain_stages?: ChainState | null;
  exports?: Record<string, string>;
  failure_message?: string;
};

export type DesktopSettings = {
  default_output_dir: string;
  ai_config: {
    provider: string;
    model: string;
    model_configured: boolean;
    model_source: string;
    base_url: string;
    base_url_configured: boolean;
    base_url_source: string;
    base_url_override: string;
    base_url_locked_by_env: boolean;
    api_key_configured: boolean;
    api_key_source: string;
    api_key_env_name: string;
    api_key_override_set: boolean;
    api_key_locked_by_env: boolean;
    model_override: string;
    model_locked_by_env: boolean;
    wire_api: string;
    responses_path: string;
  };
};

export type AIConfigUpdatePayload = {
  base_url?: string;
  api_key?: string;
  model?: string;
};

export type DesktopDataManagementStatus = {
  data_dir: string;
  db_path: string;
  output_dir: string;
  log_dir: string;
  backup_dir: string;
  project_count: number;
  run_count: number;
  knowledge_rule_count: number;
  output_size_bytes: number;
  db_size_bytes: number;
  last_backup_path: string;
  last_backup_created_at: string;
};

export type DesktopDataBackupResult = {
  backup_path: string;
  created_at: string;
  size_bytes: number;
};

export type DesktopDataClearScope = "workspace" | "factory_reset";

export type DesktopDataClearRequest = {
  scope: DesktopDataClearScope;
  delete_outputs: boolean;
  confirm_text: string;
};

export type ExportResponse = {
  run_id: number;
  export_mode: "draft" | "final";
  output_dir: string;
  exports: Record<string, string>;
  quality_gate?: Record<string, unknown>;
  export_result?: Record<string, unknown>;
};

export type ClosureTask = {
  id: string;
  type:
    | "knowledge_recommendation"
    | "action_item"
    | "change_impact"
    | "manual_review"
    | "automation_review"
    | "pfmea_action"
    | "linkage_sync"
    | "closure_task";
  title: string;
  state: string;
  targetId?: string;
  source?: string;
  raw: Record<string, unknown>;
};

export type DrawingAnalysisIdentity = {
  part_name?: string;
  drawing_number?: string;
  revision?: string;
  [key: string]: unknown;
};

export type DrawingAnalysisItem = {
  item_id?: string;
  id?: string;
  label?: string;
  name?: string;
  value?: unknown;
  evidence_refs?: string[];
  confidence?: number | string;
  needs_confirmation?: boolean;
  [key: string]: unknown;
};

export type SpecialCharacteristicJudgment = {
  judgment_id?: string;
  candidate_id?: string;
  classification?: "SC" | "CC" | "unknown";
  verdict?: "confirmed" | "rejected" | "needs_human_review";
  linked_feature?: string;
  confidence?: number;
  reasoning_summary?: string;
};

export type DeclaredSpecialCharacteristic = {
  declaration_id?: string;
  classification?: "SC" | "CC";
  expected_count?: number;
  source_text?: string;
  evidence_refs?: string[];
};

export type DeclaredSpecialTotals = {
  CC?: number;
  SC?: number;
};

export type SpecialCharacteristicSearchCoverage = {
  CC?: number;
  SC?: number;
};

export type SpecialCharacteristicLocation = {
  location_id?: string;
  classification?: "SC" | "CC" | "unknown";
  linked_feature?: string;
  symbol_text_or_shape?: string;
  confidence?: number;
  evidence_refs?: string[];
};

export type SpecialCharacteristicDiscovery = {
  declared_totals?: DeclaredSpecialTotals;
  found_counts?: DeclaredSpecialTotals;
  missing_counts?: DeclaredSpecialTotals;
  extra_counts?: DeclaredSpecialTotals;
  search_coverage?: SpecialCharacteristicSearchCoverage;
  risks?: Record<string, unknown>[];
};

export type DrawingAnalysisResponse = {
  document_type?: string;
  schema_version?: string;
  drawing_identity?: DrawingAnalysisIdentity;
  materials?: DrawingAnalysisItem[];
  surface_treatments?: DrawingAnalysisItem[];
  dimensions?: DrawingAnalysisItem[];
  tolerances?: DrawingAnalysisItem[];
  special_characteristics?: DrawingAnalysisItem[];
  special_characteristic_judgments?: SpecialCharacteristicJudgment[];
  declared_special_characteristics?: DeclaredSpecialCharacteristic[];
  declared_totals?: DeclaredSpecialTotals;
  special_characteristic_locations?: SpecialCharacteristicLocation[];
  special_characteristic_discovery?: SpecialCharacteristicDiscovery;
  technical_requirements?: DrawingAnalysisItem[];
  inspection_requirements?: DrawingAnalysisItem[];
  manufacturing_clues?: DrawingAnalysisItem[];
  uncertainties?: DrawingAnalysisItem[];
  evidence?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export type PartFamilyResponse = {
  run_id?: number;
  part_family: string;
  confidence?: number;
  source?: string;
  candidates?: Array<{
    value: string;
    label?: string;
    confidence?: number;
    reason?: string;
  }>;
  context?: Record<string, unknown>;
  raw?: Record<string, unknown>;
};

export type PartFamilyKnowledgeFamily = {
  family_key: string;
  family_name: string;
  knowledge_path?: string;
  default_seed_dir?: string;
  default_seed_workbook?: string;
  available?: boolean;
  failure_message?: string;
  process_route_template_count?: number;
  pfmea_pattern_count?: number;
  control_plan_pattern_count?: number;
  special_characteristic_pattern_count?: number;
  source_ref_count?: number;
};

export type KnowledgeFamiliesResponse = {
  schema_version?: string;
  families: PartFamilyKnowledgeFamily[];
};

export type KnowledgeImportSeedsRequest = {
  seed_dirs?: Record<string, string>;
  output_dir?: string;
  write_files?: boolean;
};

export type KnowledgeImportSeedsResponse = {
  status: string;
  write_files: boolean;
  output_dir: string;
  families: PartFamilyKnowledgeFamily[];
};

export type ClosureTasksResponse = {
  run_id?: number;
  title?: string;
  summary?: Record<string, unknown>;
  tasks?: Record<string, unknown>[];
  rows?: Record<string, unknown>[];
  raw?: Record<string, unknown>;
};

export type LinkageApplySyncRequest = {
  suggestion_ids?: string[];
  apply_all?: boolean;
  reason?: string;
};

export type LinkageApplySyncResponse = {
  run_id?: number;
  applied_count?: number;
  skipped_count?: number;
  run?: DesktopRun;
  current_result?: Record<string, unknown>;
  message?: string;
  raw?: Record<string, unknown>;
};

// ---- 链式确认流程类型 ----

export type StageStatus =
  | "not_started"
  | "running"
  | "generated"
  | "confirmed"
  | "blocked"
  | "failed";

export type ChainStageKey = "pfd" | "pfmea" | "cp";

export type StageConfirmInfo = {
  status: StageStatus;
  generated_at: string;
  confirmed_at: string;
  confirmed_by: string;
  row_count: number;
  pending_count: number;
};

export type ChainState = {
  pfd: StageConfirmInfo;
  pfmea: StageConfirmInfo;
  cp: StageConfirmInfo;
  pipeline_mode: "batch" | "chain";
  current_stage: ChainStageKey | "complete";
};

export type ChainConfirmRequest = {
  confirmed_by?: string;
  edit_patch?: Record<string, unknown>;
  reason?: string;
};
