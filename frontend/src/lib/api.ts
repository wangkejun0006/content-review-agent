import type { CampaignBrief, AgentLLMBinding, AttributionEvidence, AuditEventPage, ClaimCoverage, CommerceSnapshot, ComplianceReport, ContentCandidate, GrowthRun, EvidenceDocument, EvidenceImportDraft, FeedbackRecommendation, FeedbackRun, ManagedUser, MetricSnapshot, LLMConfigurationStatus, LLMProviderConfig, LLMUsageReport, LoginContext, OperationalJob, OperationsStatus, Publication, ProductImportDraft, ProductMedia, PlatformRuleImportDraft, RegistryItem, RegistryItemDetail, RegistryRevision, Role, RunContext, ScoreReport, StrategyPlan, TokenResponse } from '../types'

const TOKEN_KEY = 'smart-growth-token'
const AUTH_NOTICE_KEY = 'smart-growth-auth-notice'
export const AUTH_EXPIRED_EVENT = 'smart-growth-auth-expired'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => {
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(AUTH_NOTICE_KEY)
  },
  expire: () => {
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.setItem(AUTH_NOTICE_KEY, '服务器安全配置已更新或登录已过期，请重新登录。')
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
  },
  getNotice: () => sessionStorage.getItem(AUTH_NOTICE_KEY),
  clearNotice: () => sessionStorage.removeItem(AUTH_NOTICE_KEY),
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData) && init.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Preserve the safe generic message for non-JSON errors.
    }
    if (response.status === 401 && token) tokenStore.expire()
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  loginContext: () => request<LoginContext>('/v1/auth/login-context'),
  login: (email: string, password: string, brandId: string) =>
    request<TokenResponse>('/v1/auth/token', {
      method: 'POST',
      body: JSON.stringify({ email, password, brand_id: brandId }),
    }),
  listUsers: () => request<ManagedUser[]>('/v1/auth/users'),
  createUser: (payload: { email: string; display_name: string; password: string; role: Role }) =>
    request<ManagedUser>('/v1/auth/users', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listRegistry: (type: string, includeArchived = false) =>
    request<RegistryItem[]>(`/v1/registry/${type}${includeArchived ? '?include_archived=true' : ''}`),
  getRegistryItem: (type: string, id: string) => request<RegistryItemDetail>(`/v1/registry/${type}/${id}`),
  createRegistryItem: (type: string, payload: Record<string, unknown>) =>
    request<RegistryItemDetail>(`/v1/registry/${type}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createRegistryRevision: (type: string, itemId: string, payload: Record<string, unknown>) =>
    request<RegistryRevision>(`/v1/registry/${type}/${itemId}/revisions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateRegistryRevision: (type: string, itemId: string, revisionId: string, payload: Record<string, unknown>) =>
    request<RegistryRevision>(`/v1/registry/${type}/${itemId}/revisions/${revisionId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  archiveRegistryItem: (type: string, itemId: string) =>
    request<RegistryItem>(`/v1/registry/${type}/${itemId}/archive`, { method: 'POST' }),
  restoreRegistryItem: (type: string, itemId: string) =>
    request<RegistryItem>(`/v1/registry/${type}/${itemId}/restore`, { method: 'POST' }),
  permanentlyDeleteRegistryItem: (type: string, itemId: string) =>
    request<void>(`/v1/registry/${type}/${itemId}`, { method: 'DELETE' }),
  resolveIngestion: (id: string, payload: Record<string, unknown>) =>
    request(`/v1/ingestions/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  activateRevision: (type: string, itemId: string, revisionId: string) => request<RegistryRevision>(`/v1/registry/${type}/${itemId}/revisions/${revisionId}/activate`, { method: 'POST' }),
  productAiDraft: (pastedText: string, files: File[]) => {
    const body = new FormData()
    body.set('pasted_text', pastedText)
    files.forEach((file) => body.append('files', file))
    return request<ProductImportDraft>('/v1/registry/product/ai-drafts', {
      method: 'POST',
      body,
    })
  },
  evidenceAiDraft: (sourceUri: string, pastedText: string, file: File | null) => {
    const body = new FormData()
    body.set('source_uri', sourceUri)
    body.set('pasted_text', pastedText)
    if (file) body.set('file', file)
    return request<EvidenceImportDraft>('/v1/evidence/ai-drafts', {
      method: 'POST',
      body,
    })
  },
  listProductMedia: (productItemId?: string) => request<ProductMedia[]>(`/v1/product-media${productItemId ? `?product_item_id=${productItemId}` : ''}`),
  uploadProductMedia: (productItemId: string, altText: string, file: File, isPrimary: boolean) => {
    const body = new FormData()
    body.set('product_item_id', productItemId)
    body.set('alt_text', altText)
    body.set('is_primary', String(isPrimary))
    body.set('file', file)
    return request<ProductMedia>('/v1/product-media', { method: 'POST', body })
  },
  makeProductMediaPrimary: (id: string) =>
    request<ProductMedia>(`/v1/product-media/${id}/primary`, {
      method: 'POST',
    }),
  platformRuleAiDraft: (sourceUrl: string, verifiedAt: string, pastedText: string, file: File | null) => {
    const body = new FormData()
    body.set('source_url', sourceUrl)
    body.set('verified_at', new Date(verifiedAt).toISOString())
    body.set('pasted_text', pastedText)
    if (file) body.set('file', file)
    return request<PlatformRuleImportDraft>('/v1/registry/platform_rule/ai-drafts', {
      method: 'POST',
      body,
    })
  },
  listBriefs: (includeArchived = false) =>
    request<CampaignBrief[]>(`/v1/briefs${includeArchived ? '?include_archived=true' : ''}`),
  createBrief: (payload: Record<string, unknown>) =>
    request<CampaignBrief>('/v1/briefs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateBrief: (id: string, payload: Record<string, unknown>) =>
    request<CampaignBrief>(`/v1/briefs/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  archiveBrief: (id: string) => request<CampaignBrief>(`/v1/briefs/${id}/archive`, { method: 'POST' }),
  restoreBrief: (id: string) => request<CampaignBrief>(`/v1/briefs/${id}/restore`, { method: 'POST' }),
  permanentlyDeleteBrief: (id: string) => request<void>(`/v1/briefs/${id}`, { method: 'DELETE' }),
  listRuns: (includeArchived = false) =>
    request<GrowthRun[]>(`/v1/growth-runs${includeArchived ? '?include_archived=true' : ''}`),
  getRun: (id: string) => request<GrowthRun>(`/v1/growth-runs/${id}`),
  getRunContexts: (id: string) => request<RunContext[]>(`/v1/growth-runs/${id}/contexts`),
  createRun: (briefId: string) =>
    request<GrowthRun>('/v1/growth-runs', {
      method: 'POST',
      headers: { 'Idempotency-Key': `ui-run-${crypto.randomUUID()}` },
      body: JSON.stringify({ brief_id: briefId }),
    }),
  archiveRun: (id: string) => request<GrowthRun>(`/v1/growth-runs/${id}/archive`, { method: 'POST' }),
  restoreRun: (id: string) => request<GrowthRun>(`/v1/growth-runs/${id}/restore`, { method: 'POST' }),
  permanentlyDeleteRun: (id: string) =>
    request<void>(`/v1/growth-runs/${id}`, { method: 'DELETE' }),
  getCandidates: (runId: string) => request<ContentCandidate[]>(`/v1/growth-runs/${runId}/candidates`),
  getStrategy: (runId: string) => request<StrategyPlan>(`/v1/growth-runs/${runId}/strategy`),
  getCompliance: (runId: string) => request<ComplianceReport[]>(`/v1/growth-runs/${runId}/compliance-reports`),
  getScores: (runId: string) => request<ScoreReport[]>(`/v1/growth-runs/${runId}/score-reports`),
  submitReview: (runId: string, payload: Record<string, unknown>) =>
    request(`/v1/growth-runs/${runId}/reviews`, {
      method: 'POST',
      headers: { 'Idempotency-Key': `ui-review-${crypto.randomUUID()}` },
      body: JSON.stringify(payload),
    }),
  listEvidence: () => request<EvidenceDocument[]>('/v1/evidence'),
  createEvidence: (payload: Record<string, unknown>) =>
    request<EvidenceDocument>('/v1/evidence', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  verifyEvidence: (id: string) => request<EvidenceDocument>(`/v1/evidence/${id}/verify`, { method: 'POST' }),
  getClaimCoverage: () => request<ClaimCoverage>('/v1/claim-coverage'),
  getRunClaimCoverage: (runId: string) =>
    request<ClaimCoverage>(`/v1/growth-runs/${runId}/claim-coverage`),
  listPublications: () => request<Publication[]>('/v1/publications'),
  createPublication: (payload: Record<string, unknown>) =>
    request<Publication>('/v1/publications', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listMetricSnapshots: (publicationId: string) => request<MetricSnapshot[]>(`/v1/publications/${publicationId}/metric-snapshots`),
  createMetricSnapshot: (publicationId: string, payload: Record<string, unknown>) =>
    request<MetricSnapshot>(`/v1/publications/${publicationId}/metric-snapshots`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listCommerceSnapshots: () => request<CommerceSnapshot[]>('/v1/commerce-snapshots'),
  createCommerceSnapshot: (payload: Record<string, unknown>) =>
    request<CommerceSnapshot>('/v1/commerce-snapshots', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listAttributionEvidence: () => request<AttributionEvidence[]>('/v1/attribution-evidence'),
  createAttributionEvidence: (payload: Record<string, unknown>) =>
    request<AttributionEvidence>('/v1/attribution-evidence', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listFeedbackRuns: () => request<FeedbackRun[]>('/v1/feedback-runs'),
  getFeedbackRun: (id: string) => request<FeedbackRun>(`/v1/feedback-runs/${id}`),
  createFeedbackRun: (publicationIds: string[], commerceSnapshotIds: string[]) =>
    request<FeedbackRun>('/v1/feedback-runs', {
      method: 'POST',
      headers: { 'Idempotency-Key': `ui-feedback-${crypto.randomUUID()}` },
      body: JSON.stringify({
        publication_ids: publicationIds,
        commerce_snapshot_ids: commerceSnapshotIds,
      }),
    }),
  getFeedbackRecommendation: (id: string) => request<FeedbackRecommendation>(`/v1/feedback-runs/${id}/recommendation`),
  activateStrategyInsight: (revisionId: string) =>
    request<RegistryRevision>(`/v1/strategy-insights/${revisionId}/activate`, {
      method: 'POST',
    }),
  getLLMStatus: () => request<LLMConfigurationStatus>('/v1/llm/status'),
  getLLMUsage: (days = 30) => request<LLMUsageReport>(`/v1/llm/usage?days=${days}`),
  listLLMProviders: () => request<LLMProviderConfig[]>('/v1/llm/providers'),
  createLLMProvider: (payload: Record<string, unknown>) =>
    request<LLMProviderConfig>('/v1/llm/providers', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateLLMProvider: (id: string, payload: Record<string, unknown>) =>
    request<LLMProviderConfig>(`/v1/llm/providers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  testLLMProvider: (id: string) =>
    request<{ status: 'ok'; message: string }>(`/v1/llm/providers/${id}/test`, {
      method: 'POST',
    }),
  listLLMBindings: () => request<AgentLLMBinding[]>('/v1/llm/bindings'),
  upsertLLMBinding: (purpose: string, providerConfigId: string, modelOverride: string) =>
    request<AgentLLMBinding>(`/v1/llm/bindings/${purpose}`, {
      method: 'PUT',
      body: JSON.stringify({
        provider_config_id: providerConfigId,
        model_override: modelOverride || null,
      }),
    }),
  getOperationsStatus: () => request<OperationsStatus>('/v1/operations/status'),
  retryFailedJob: (jobId: string) =>
    request<OperationalJob>(`/v1/operations/jobs/${jobId}/retry`, { method: 'POST' }),
  listAuditEvents: (filters: {
    actorId?: string
    action?: string
    resourceType?: string
    createdFrom?: string
    createdTo?: string
    limit?: number
    offset?: number
  }) => {
    const params = new URLSearchParams()
    if (filters.actorId) params.set('actor_id', filters.actorId)
    if (filters.action) params.set('action', filters.action)
    if (filters.resourceType) params.set('resource_type', filters.resourceType)
    if (filters.createdFrom) params.set('created_from', filters.createdFrom)
    if (filters.createdTo) params.set('created_to', filters.createdTo)
    params.set('limit', String(filters.limit || 50))
    params.set('offset', String(filters.offset || 0))
    return request<AuditEventPage>(`/v1/audit-events?${params.toString()}`)
  },
}
