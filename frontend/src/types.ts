export type Role = 'admin' | 'editor' | 'reviewer'
export type RevisionStatus = 'draft' | 'active' | 'retired'
export type RunStatus = 'queued' | 'running' | 'waiting_human' | 'phase1_ready' | 'waiting_knowledge_review' | 'content_draft_ready' | 'ready_for_manual_publish' | 'rejected' | 'failed'

export interface Principal {
  userId: string
  brandId: string
  role: Role
  email: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_at: string
}

export interface LoginContext {
  brand_id: string | null
  brand_name: string | null
  requires_brand_id: boolean
}

export interface ManagedUser {
  id: string
  email: string
  display_name: string
  brand_id: string
  role: Role
}

export interface ProductPayload {
  name: string
  sku: string | null
  product_type: 'desk_accessory' | 'stationery'
  description: string
  features: string[]
  materials: string[]
  non_medical_disclaimer: string
}

export interface ProductMedia {
  id: string
  product_item_id: string
  media_type: string
  file_name: string
  mime_type: string
  byte_size: number
  width: number
  height: number
  alt_text: string
  is_primary: boolean
  url: string
  created_at: string
}

export interface IngestionAnalysis {
  ingestion_id: string
  duplicate_status: 'none' | 'possible' | 'exact'
  matches: Array<{
    match_type: 'exact_source' | 'same_sku' | 'same_stable_key' | 'similar_text'
    entity_type: string
    item_id: string | null
    revision_id: string | null
    evidence_document_id: string | null
    label: string
    similarity: number
    recommended_action: 'cancel' | 'new_revision' | 'review'
  }>
  recommended_action: 'new_item' | 'new_revision' | 'cancel' | 'review'
  llm_skipped: boolean
  message: string
}

export interface ProductImportDraft {
  stable_key: string
  payload: ProductPayload
  search_text: string
  field_confidence: Record<string, number>
  missing_fields: string[]
  warnings: string[]
  source_summaries: Array<{ source_name: string; summary: string }>
  dedup?: IngestionAnalysis | null
}

export interface EvidenceImportDraft {
  title: string
  document_type: 'product_specification' | 'test_report' | 'material_certificate' | 'brand_approval' | 'other'
  source_uri: string
  content: string
  source_summary: string
  relevant_excerpts: string[]
  confidence: number
  warnings: string[]
  dedup?: IngestionAnalysis | null
}

export interface PlatformRuleImportDraft {
  stable_key: string
  payload: {
    platform: 'xhs'
    category: 'content_compliance' | 'ai_content' | 'health_claim' | 'recommendation'
    rule_text: string
    severity: 'blocker' | 'warning' | 'information'
    source_url: string
    effective_from: string | null
    verified_at: string
  }
  search_text: string
  confidence: number
  source_excerpt: string
  warnings: string[]
  dedup: IngestionAnalysis
}

export interface RegistryItem {
  id: string
  brand_id: string
  registry_type: string
  stable_key: string
  current_revision_id: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface RegistryRevision {
  id: string
  item_id: string
  version: number
  status: RevisionStatus
  verification_status: 'provisional' | 'verified'
  payload: Record<string, unknown>
  search_text: string
  source_uri: string | null
  created_at: string
  activated_at: string | null
}

export interface RegistryItemDetail extends RegistryItem {
  revisions: RegistryRevision[]
}

export interface CampaignBrief {
  id: string
  brand_id: string
  name: string
  objective: string
  product_item_ids: string[]
  audience_item_ids: string[]
  constraints: Record<string, unknown>
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface GrowthRun {
  id: string
  brand_id: string
  brief_id: string
  thread_id: string
  status: RunStatus
  gate_status: string
  error: Record<string, unknown> | null
  recommended_candidate_id: string | null
  selected_candidate_id: string | null
  created_at: string
  updated_at: string
  archived_at: string | null
  registry_revision_ids: string[]
  job_id: string | null
}

export interface RunContext {
  id: string
  context_type: 'product' | 'policy' | 'trend'
  payload: Record<string, unknown>
}

export interface WriterPayload {
  route_key: string
  angle_key: string
  title_options: string[]
  recommended_title: string
  body: string
  visual_brief: {
    cover_concept: string
    cover_text: string
    scene: string
    shot_list: string[]
    props_and_background: string[]
    avoid_elements: string[]
  }
  media_plan: {
    preferred_format: 'image_set' | 'video'
    rationale: string
    preferred_generation_prompt: string
    alternate_format: 'image_set' | 'video'
    alternate_generation_prompt: string
    aspect_ratio: string
    duration_seconds: number | null
    image_sequence: string[]
    shot_list: string[]
    voiceover: string
    on_screen_text: string[]
    negative_prompts: string[]
    shooting_notes: string[]
    product_media_ids: string[]
    claim_revision_ids: string[]
  }
  tags: string[]
  cta: string
  cited_claim_revision_ids: string[]
  source_revision_ids: string[]
}

export interface StrategyPlan {
  id: string
  payload: {
    objective: string
    target_audience: string
    key_message: string
    brand_voice: string[]
    guardrails: string[]
    marketing_support: {
      policy: 'organic_only' | 'evaluate' | 'required'
      recommended: boolean
      program_revision_ids: string[]
      program_names: string[]
      rationale: string[]
      prerequisites: string[]
      application_checklist: string[]
      budget_assumptions: string[]
      measurement_plan: string[]
      human_decision_required: true
    }
  }
}

export interface ContentCandidate {
  id: string
  route_key: string
  angle_key: string
  current_version: number
  content_version_id: string
  payload: WriterPayload
}

export interface ComplianceReport {
  id: string
  content_version_id: string
  deterministic_pass: boolean
  semantic_pass: boolean
  has_blockers: boolean
  summary: string
  findings: Array<{
    id: string
    category: string
    severity: string
    message: string
    source: string
    evidence_excerpt: string
    suggestion: string
  }>
}

export interface ScoreReport {
  id: string
  content_version_id: string
  total_score: number
  pass_threshold: number
  passed: boolean
  summary: string
  revision_suggestions: string[]
  dimensions: Array<{ name: string; score: number; rationale: string }>
}

export interface EvidenceDocument {
  id: string
  brand_id: string
  title: string
  document_type: string
  source_uri: string
  content: string
  verified_by: string | null
  verified_at: string | null
  is_active: boolean
  created_at: string
}

export interface Publication {
  id: string
  brand_id: string
  content_version_id: string
  platform: 'xhs'
  platform_content_id: string
  url: string
  published_at: string
  created_at: string
}

export interface MetricSnapshot {
  id: string
  publication_id: string
  captured_at: string
  impressions: number | null
  views: number | null
  likes: number | null
  collections: number | null
  comments: number | null
  shares: number | null
  follows: number | null
  profile_visits: number | null
  outbound_clicks: number | null
  is_correction: boolean
  created_at: string
}

export interface CommerceSnapshot {
  id: string
  brand_id: string
  captured_at: string
  scope_type: 'store' | 'sku' | 'campaign'
  scope_key: string
  impressions: number | null
  product_views: number | null
  add_to_cart: number | null
  orders: number | null
  paid_orders: number | null
  gmv: string | number | null
  created_at: string
}

export type AttributionStrength = 'direct' | 'assisted' | 'correlative'

export interface AttributionEvidence {
  id: string
  brand_id: string
  publication_id: string
  commerce_snapshot_id: string
  evidence_type: 'dedicated_link' | 'code' | 'campaign' | 'manual_link'
  strength: AttributionStrength
  details: Record<string, unknown>
  created_at: string
}

export interface FeedbackRun {
  id: string
  brand_id: string
  thread_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  publication_ids: string[]
  metric_snapshot_ids: string[]
  commerce_snapshot_ids: string[]
  attribution_evidence_ids: string[]
  prompt_revision_id: string | null
  input_checksum: string | null
  error: Record<string, unknown> | null
  recommendation_id: string | null
  strategy_insight_revision_id: string | null
  job_id: string | null
  created_at: string
}

export interface FeedbackRecommendation {
  id: string
  feedback_run_id: string
  recommendation: {
    summary: string
    observations: Array<{
      statement: string
      evidence_ids: string[]
      attribution_scope: AttributionStrength
      confidence: number
    }>
    hypotheses: Array<{
      statement: string
      rationale: string
      attribution_scope: AttributionStrength
      confidence: number
    }>
    actions: Array<{
      action: string
      rationale: string
      priority: 'high' | 'medium' | 'low'
      expected_signal: string
    }>
    confidence: number
    attribution_scope: AttributionStrength
    limitations: string[]
  }
  confidence: string | number
  attribution_scope: AttributionStrength
  input_checksum: string
  strategy_insight_revision_id: string | null
  created_at: string
}

export interface LLMConfigurationStatus {
  credential_storage_ready: boolean
  runtime_mode: string
  supported_purposes: string[]
}

export interface LLMProviderConfig {
  id: string
  name: string
  provider_type: string
  base_url: string
  default_model: string
  is_enabled: boolean
  has_api_key: boolean
  last_tested_at: string | null
  last_test_status: string | null
  last_test_message: string | null
  created_at: string
  updated_at: string
}

export interface AgentLLMBinding {
  id: string
  purpose: string
  provider_config_id: string
  model_override: string | null
}

export interface LLMUsageTotals {
  calls: number
  successful_calls: number
  failed_calls: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  unreported_token_calls: number
  average_latency_ms: number
}

export interface LLMUsageReport {
  requested_days: number | null
  period_start: string | null
  period_end: string
  totals: LLMUsageTotals
  by_provider: Array<LLMUsageTotals & { provider: string; model: string }>
  by_purpose: Array<LLMUsageTotals & { purpose: string }>
}

export interface OperationalJob {
  id: string
  job_type: 'growth_run' | 'feedback_run'
  status: 'queued' | 'running' | 'waiting_human' | 'succeeded' | 'failed'
  attempts: number
  max_attempts: number
  manual_retries: number
  related_resource_id: string | null
  last_error: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface OperationsStatus {
  checked_at: string
  worker: {
    online: boolean
    worker_id: string | null
    hostname: string | null
    process_id: number | null
    status: string
    current_job_id: string | null
    started_at: string | null
    last_seen_at: string | null
    stale_after_seconds: number
  }
  queue: {
    queued: number
    running: number
    waiting_human: number
    succeeded: number
    failed: number
  }
  failed_jobs: OperationalJob[]
}

export interface ClaimCoverage {
  scope: 'current_active_registry' | 'run_registry_snapshot'
  run_id: string | null
  products_total: number
  products_with_claims: number
  product_claim_coverage_percent: number
  claims_total: number
  fully_supported_claims: number
  claim_evidence_coverage_percent: number
  verified_evidence_documents: number
  products: Array<{
    product_item_id: string
    product_revision_id: string
    product_name: string
    active_claims: number
    fully_supported_claims: number
    verified_evidence_documents: number
    status: 'covered' | 'no_claims' | 'evidence_gap'
    warnings: string[]
  }>
}

export interface AuditEvent {
  id: string
  actor_id: string | null
  actor_email: string | null
  actor_display_name: string | null
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown>
  created_at: string
}

export interface AuditEventPage {
  total: number
  limit: number
  offset: number
  items: AuditEvent[]
}
