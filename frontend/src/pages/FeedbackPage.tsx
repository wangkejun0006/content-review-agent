import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, BadgeCheck, BarChart3, Link2, Plus, Sparkles, Store, TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal, StatusBadge, TextAreaField } from '../components/ui'
import { api } from '../lib/api'
import type { AttributionEvidence, AttributionStrength, CommerceSnapshot, FeedbackRun, Publication } from '../types'

const scopeLabels = { store: '店铺', sku: 'SKU', campaign: '活动' }
const evidenceLabels = { dedicated_link: '专属链接', code: '专属口令/码', campaign: '同一活动', manual_link: '人工关联' }
const strengthLabels = { direct: '直接归因', assisted: '辅助归因', correlative: '同期相关' }

function publicationLabel(publication: Publication) {
  return `笔记 ${publication.platform_content_id} · ${new Date(publication.published_at).toLocaleDateString('zh-CN')}`
}

function commerceLabel(snapshot: CommerceSnapshot) {
  return `${scopeLabels[snapshot.scope_type]} ${snapshot.scope_key} · ${new Date(snapshot.captured_at).toLocaleDateString('zh-CN')}`
}

function SelectField({ label, example, value, onChange, children }: {
  label: string
  example?: string
  value: string
  onChange: (value: string) => void
  children: React.ReactNode
}) {
  return <label className="block space-y-2"><span className="flex items-baseline justify-between gap-3"><span className="text-sm font-semibold text-graphite">{label}</span>{example && <span className="text-xs text-slate-400">示例：{example}</span>}</span><select className="field-control" value={value} onChange={(event) => onChange(event.target.value)}>{children}</select></label>
}

function CommerceModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [scopeType, setScopeType] = useState<'store' | 'sku' | 'campaign'>('sku')
  const [scopeKey, setScopeKey] = useState('')
  const [capturedAt, setCapturedAt] = useState(new Date().toISOString().slice(0, 16))
  const [metrics, setMetrics] = useState<Record<string, string>>({ impressions: '', product_views: '', add_to_cart: '', orders: '', paid_orders: '', gmv: '' })
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () => api.createCommerceSnapshot({
      captured_at: new Date(capturedAt).toISOString(),
      scope_type: scopeType,
      scope_key: scopeKey,
      ...Object.fromEntries(Object.entries(metrics).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])),
    }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['commerce-snapshots'] }); onClose() },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '京东数据保存失败'),
  })
  const metricFields = [['impressions', '曝光'], ['product_views', '商品访问'], ['add_to_cart', '加购'], ['orders', '订单'], ['paid_orders', '支付订单'], ['gmv', 'GMV（元）']]
  return <Modal title="录入京东累计数据" description="按店铺、SKU 或活动保存一个时间点的累计快照，不要求上传消费者个人信息。" onClose={onClose}>
    <div className="space-y-5"><Callout title="先选对统计口径">同一条趋势应持续使用相同的范围类型和标识，例如始终记录 SKU：Paper Orbit-NOTE01。</Callout><div className="grid gap-4 sm:grid-cols-2"><SelectField label="数据范围" example="单品请选择 SKU" value={scopeType} onChange={(value) => setScopeType(value as typeof scopeType)}><option value="store">整个店铺</option><option value="sku">单个 SKU</option><option value="campaign">营销活动</option></SelectField><Field label="范围标识" example="Paper Orbit-NOTE01" value={scopeKey} onChange={(event) => setScopeKey(event.target.value)} /></div><Field label="采集时间" example="从京东后台导出数据的时间" type="datetime-local" value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} /><div className="grid grid-cols-2 gap-4">{metricFields.map(([key, label]) => <Field key={key} label={label} example="累计值" type="number" min={0} step={key === 'gmv' ? '0.01' : '1'} value={metrics[key]} onChange={(event) => setMetrics({ ...metrics, [key]: event.target.value })} />)}</div>{error && <p className="text-sm text-red-600">{error}</p>}<div className="flex justify-end"><Button disabled={!scopeKey || !Object.values(metrics).some(Boolean)} loading={mutation.isPending} onClick={() => mutation.mutate()}><Store className="h-4 w-4" />保存京东快照</Button></div></div>
  </Modal>
}

function AttributionModal({ publications, commerce, onClose }: { publications: Publication[]; commerce: CommerceSnapshot[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [publicationId, setPublicationId] = useState(publications[0]?.id || '')
  const [commerceId, setCommerceId] = useState(commerce[0]?.id || '')
  const [evidenceType, setEvidenceType] = useState<'dedicated_link' | 'code' | 'campaign' | 'manual_link'>('dedicated_link')
  const [strength, setStrength] = useState<AttributionStrength>('direct')
  const [reference, setReference] = useState('')
  const [error, setError] = useState('')
  const directAllowed = evidenceType === 'dedicated_link' || evidenceType === 'code'
  const mutation = useMutation({
    mutationFn: () => api.createAttributionEvidence({ publication_id: publicationId, commerce_snapshot_id: commerceId, evidence_type: evidenceType, strength, details: { reference } }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['attribution-evidence'] }); onClose() },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '归因证据保存失败'),
  })
  function changeEvidenceType(value: typeof evidenceType) {
    setEvidenceType(value)
    if ((value === 'campaign' || value === 'manual_link') && strength === 'direct') setStrength('assisted')
  }
  return <Modal title="建立小红书 → 京东归因证据" description="关联一条已发布笔记和一个京东数据快照，并明确证据强度。" onClose={onClose}>
    <div className="space-y-5"><Callout title="归因强度不是效果好坏">只有专属链接或专属口令能登记为直接归因；同活动或人工关联最多是辅助归因/同期相关。</Callout><SelectField label="小红书发布记录" value={publicationId} onChange={setPublicationId}>{publications.map((item) => <option key={item.id} value={item.id}>{publicationLabel(item)}</option>)}</SelectField><SelectField label="京东数据快照" value={commerceId} onChange={setCommerceId}>{commerce.map((item) => <option key={item.id} value={item.id}>{commerceLabel(item)}</option>)}</SelectField><div className="grid gap-4 sm:grid-cols-2"><SelectField label="证据类型" example="有专属口令就选专属口令" value={evidenceType} onChange={(value) => changeEvidenceType(value as typeof evidenceType)}><option value="dedicated_link">专属链接</option><option value="code">专属口令/码</option><option value="campaign">同一活动</option><option value="manual_link">人工关联</option></SelectField><SelectField label="归因强度" value={strength} onChange={(value) => setStrength(value as AttributionStrength)}>{directAllowed && <option value="direct">直接归因</option>}<option value="assisted">辅助归因</option><option value="correlative">同期相关</option></SelectField></div><TextAreaField label="证据说明" example="笔记使用专属口令 NOTE01BLUE；京东活动后台可查该口令订单" hint="请写运营人员可以复核的说明，不需要填写 JSON。" value={reference} onChange={(event) => setReference(event.target.value)} />{error && <p className="text-sm text-red-600">{error}</p>}<div className="flex justify-end"><Button disabled={!publicationId || !commerceId || !reference} loading={mutation.isPending} onClick={() => mutation.mutate()}><Link2 className="h-4 w-4" />保存归因证据</Button></div></div>
  </Modal>
}

function FeedbackRunModal({ publications, eligibleIds, commerce, onClose }: { publications: Publication[]; eligibleIds: Set<string>; commerce: CommerceSnapshot[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [publicationIds, setPublicationIds] = useState<string[]>([])
  const [commerceIds, setCommerceIds] = useState<string[]>([])
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () => api.createFeedbackRun(publicationIds, commerceIds),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['feedback-runs'] }); onClose() },
    onError: (reason) => setError(reason instanceof Error ? reason.message : 'Feedback 任务创建失败'),
  })
  const toggle = (id: string, values: string[], setter: (next: string[]) => void) => setter(values.includes(id) ? values.filter((value) => value !== id) : [...values, id])
  return <Modal title="创建 Feedback 分析" description="冻结所选发布记录、指标快照、京东快照和归因证据，生成可审计的策略建议。" onClose={onClose} wide>
    <div className="space-y-6"><Callout title="这是明确触发的 AI 任务">Fake 模式不会付费；切换 managed 后，点击“开始分析”会调用已绑定的 Feedback Agent 模型。没有归因证据时，系统只能输出同期相关性。</Callout><div><h3 className="text-sm font-bold">1. 选择有指标的小红书笔记</h3><div className="mt-3 grid gap-3 md:grid-cols-2">{publications.map((item) => { const eligible = eligibleIds.has(item.id); return <label key={item.id} className={`flex gap-3 rounded-2xl border p-4 ${eligible ? 'cursor-pointer border-slate-200 bg-white' : 'cursor-not-allowed border-slate-100 bg-slate-50 opacity-55'}`}><input type="checkbox" disabled={!eligible} checked={publicationIds.includes(item.id)} onChange={() => toggle(item.id, publicationIds, setPublicationIds)} /><span><span className="block text-sm font-semibold">{publicationLabel(item)}</span><span className="mt-1 block text-xs text-slate-500">{eligible ? '已有指标，可分析' : '请先到“发布与数据”录入指标'}</span></span></label> })}</div></div><div><h3 className="text-sm font-bold">2. 可选：加入京东快照</h3><p className="mt-1 text-xs text-slate-500">如果已建立归因证据，请选择相应的京东快照；不选择也可以只分析小红书表现。</p><div className="mt-3 grid gap-3 md:grid-cols-2">{commerce.map((item) => <label key={item.id} className="flex cursor-pointer gap-3 rounded-2xl border border-slate-200 bg-white p-4"><input type="checkbox" checked={commerceIds.includes(item.id)} onChange={() => toggle(item.id, commerceIds, setCommerceIds)} /><span className="text-sm font-semibold">{commerceLabel(item)}</span></label>)}</div>{!commerce.length && <p className="mt-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-500">尚无京东快照，可以先只分析小红书数据。</p>}</div>{error && <p className="text-sm text-red-600">{error}</p>}<div className="flex justify-end"><Button disabled={!publicationIds.length} loading={mutation.isPending} onClick={() => mutation.mutate()}><Sparkles className="h-4 w-4" />开始分析</Button></div></div>
  </Modal>
}

function RecommendationCard({ run, canActivate, activeInsightIds }: { run: FeedbackRun; canActivate: boolean; activeInsightIds: Set<string> }) {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['feedback-recommendation', run.id], queryFn: () => api.getFeedbackRecommendation(run.id), enabled: run.status === 'succeeded' && !!run.recommendation_id })
  const [message, setMessage] = useState('')
  const activate = useMutation({
    mutationFn: api.activateStrategyInsight,
    onSuccess: async () => { setMessage('策略洞察已激活，将从后续 Growth Run 开始参与策略上下文。'); await queryClient.invalidateQueries({ queryKey: ['strategy-insights'] }) },
    onError: (reason) => setMessage(reason instanceof Error ? reason.message : '激活失败'),
  })
  const output = query.data?.recommendation
  const insightId = query.data?.strategy_insight_revision_id
  const isActive = !!insightId && activeInsightIds.has(insightId)
  return <Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Activity className="h-4 w-4 text-brand-600" /><p className="font-semibold">Feedback {run.id.slice(0, 8)}</p><StatusBadge status={run.status} /></div><p className="mt-2 text-xs text-slate-500">{new Date(run.created_at).toLocaleString('zh-CN')} · {run.publication_ids.length} 条笔记 · {run.metric_snapshot_ids.length} 个指标快照</p></div>{output && <div className="rounded-xl bg-brand-50 px-3 py-2 text-right"><p className="text-xs text-brand-700">可信度</p><p className="font-bold text-brand-900">{Math.round(output.confidence * 100)}%</p></div>}</div>{run.status === 'failed' && <p className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{JSON.stringify(run.error || '分析失败')}</p>}{(run.status === 'queued' || run.status === 'running') && <p className="mt-4 text-sm text-slate-500">Worker 正在处理，页面会自动刷新状态…</p>}{query.isLoading && <p className="mt-4 text-sm text-slate-500">正在读取策略建议…</p>}{output && <div className="mt-5 space-y-5"><Callout title={`${strengthLabels[output.attribution_scope]}结论`} tone="success">{output.summary}</Callout><div className="grid gap-5 lg:grid-cols-2"><div><h4 className="text-sm font-bold">数据观察</h4><ul className="mt-2 space-y-2">{output.observations.map((item, index) => <li key={index} className="rounded-xl bg-slate-50 p-3 text-sm"><p>{item.statement}</p><p className="mt-1 text-xs text-slate-400">{strengthLabels[item.attribution_scope]} · 可信度 {Math.round(item.confidence * 100)}%</p></li>)}</ul></div><div><h4 className="text-sm font-bold">下一步动作</h4><ul className="mt-2 space-y-2">{output.actions.map((item, index) => <li key={index} className="rounded-xl bg-blue-50/60 p-3 text-sm"><div className="flex justify-between gap-3"><p className="font-semibold">{item.action}</p><span className="text-[10px] font-bold uppercase text-brand-600">{item.priority}</span></div><p className="mt-1 text-xs leading-5 text-slate-600">{item.rationale}</p><p className="mt-1 text-xs text-slate-400">观察信号：{item.expected_signal}</p></li>)}</ul></div></div>{output.hypotheses.length > 0 && <div><h4 className="text-sm font-bold">待验证假设</h4><div className="mt-2 grid gap-2 md:grid-cols-2">{output.hypotheses.map((item, index) => <div key={index} className="rounded-xl border border-amber-100 bg-amber-50/60 p-3 text-sm"><p className="font-semibold">{item.statement}</p><p className="mt-1 text-xs leading-5 text-slate-600">{item.rationale}</p></div>)}</div></div>}{output.limitations.length > 0 && <Callout title="结论边界" tone="warning"><ul className="list-disc pl-4">{output.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></Callout>}<div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4"><p className="text-xs text-slate-500">策略建议先以草稿保存，Reviewer 激活后才影响后续内容策略。</p>{isActive ? <span className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-700"><BadgeCheck className="h-4 w-4" />Strategy Insight 已激活</span> : canActivate && insightId ? <Button variant="secondary" loading={activate.isPending} onClick={() => activate.mutate(insightId)}><BadgeCheck className="h-4 w-4" />激活 Strategy Insight</Button> : null}</div>{message && <p className="rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-800">{message}</p>}</div>}</Card>
}

function EvidenceCard({ evidence, publications, commerce }: { evidence: AttributionEvidence; publications: Publication[]; commerce: CommerceSnapshot[] }) {
  const publication = publications.find((item) => item.id === evidence.publication_id)
  const snapshot = commerce.find((item) => item.id === evidence.commerce_snapshot_id)
  return <Card className="p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-bold text-brand-600">{evidenceLabels[evidence.evidence_type]}</p><p className="mt-2 text-sm font-semibold">{publication ? publicationLabel(publication) : evidence.publication_id.slice(0, 8)}</p><p className="mt-1 text-xs text-slate-500">→ {snapshot ? commerceLabel(snapshot) : evidence.commerce_snapshot_id.slice(0, 8)}</p></div><span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-600">{strengthLabels[evidence.strength]}</span></div>{typeof evidence.details.reference === 'string' && <p className="mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">{evidence.details.reference}</p>}</Card>
}

export function FeedbackPage() {
  const { principal } = useAuth()
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const canActivate = principal?.role === 'admin' || principal?.role === 'reviewer'
  const [modal, setModal] = useState<'commerce' | 'attribution' | 'feedback' | null>(null)
  const publications = useQuery({ queryKey: ['publications'], queryFn: api.listPublications })
  const commerce = useQuery({ queryKey: ['commerce-snapshots'], queryFn: api.listCommerceSnapshots })
  const evidence = useQuery({ queryKey: ['attribution-evidence'], queryFn: api.listAttributionEvidence })
  const runs = useQuery({ queryKey: ['feedback-runs'], queryFn: api.listFeedbackRuns, refetchInterval: (query) => query.state.data?.some((run) => run.status === 'queued' || run.status === 'running') ? 2000 : false })
  const insights = useQuery({ queryKey: ['strategy-insights'], queryFn: () => api.listRegistry('strategy_insight') })
  const publicationKey = (publications.data || []).map((item) => item.id).join(',')
  const metrics = useQuery({ queryKey: ['feedback-publication-metrics', publicationKey], queryFn: async () => Promise.all((publications.data || []).map(async (item) => ({ publicationId: item.id, rows: await api.listMetricSnapshots(item.id) }))), enabled: !!publications.data })
  const eligibleIds = useMemo(() => new Set((metrics.data || []).filter((item) => item.rows.length).map((item) => item.publicationId)), [metrics.data])
  const activeInsightIds = useMemo(() => new Set((insights.data || []).map((item) => item.current_revision_id).filter((id): id is string => !!id)), [insights.data])
  if (publications.isLoading || commerce.isLoading || evidence.isLoading || runs.isLoading || metrics.isLoading || insights.isLoading) return <LoadingBlock label="正在读取增长反馈资产" />
  const publicationRows = publications.data || []
  const commerceRows = commerce.data || []
  const evidenceRows = evidence.data || []
  const feedbackRuns = runs.data || []
  return <div className="animate-fade-up"><PageHeader eyebrow="Commerce Attribution & Feedback" title="增长反馈" description="把发布表现、京东结果和证据强度串起来，生成有边界、可审核、可复用的策略资产。" actions={canWrite ? <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => setModal('commerce')}><Plus className="h-4 w-4" />京东快照</Button><Button variant="secondary" disabled={!publicationRows.length || !commerceRows.length} onClick={() => setModal('attribution')}><Link2 className="h-4 w-4" />归因证据</Button><Button disabled={!eligibleIds.size} onClick={() => setModal('feedback')}><Sparkles className="h-4 w-4" />Feedback 分析</Button></div> : undefined} />
    <div className="mb-6 grid gap-4 md:grid-cols-3"><Card className="p-5"><Store className="h-5 w-5 text-brand-600" /><p className="mt-3 text-2xl font-bold">{commerceRows.length}</p><p className="text-xs text-slate-500">京东累计快照</p></Card><Card className="p-5"><Link2 className="h-5 w-5 text-brand-600" /><p className="mt-3 text-2xl font-bold">{evidenceRows.length}</p><p className="text-xs text-slate-500">归因证据</p></Card><Card className="p-5"><TrendingUp className="h-5 w-5 text-brand-600" /><p className="mt-3 text-2xl font-bold">{feedbackRuns.length}</p><p className="text-xs text-slate-500">Feedback 运行</p></Card></div>
    <div className="space-y-8"><section><div className="mb-3 flex items-end justify-between"><div><h2 className="font-bold">Feedback 分析记录</h2><p className="mt-1 text-xs text-slate-500">输出只代表内部分析；没有直接证据时不会给出因果结论。</p></div></div>{feedbackRuns.length ? <div className="space-y-4">{feedbackRuns.map((run) => <RecommendationCard key={run.id} run={run} canActivate={canActivate} activeInsightIds={activeInsightIds} />)}</div> : <Card><EmptyState icon={<BarChart3 className="h-6 w-6" />} title="尚无 Feedback 分析" description="先登记发布记录并录入至少一个小红书指标快照，再显式创建分析任务。" /></Card>}</section>
      <section className="grid gap-6 xl:grid-cols-2"><div><h2 className="mb-3 font-bold">京东数据快照</h2>{commerceRows.length ? <div className="space-y-3">{commerceRows.map((item) => <Card key={item.id} className="p-4"><div className="flex items-start justify-between"><div><p className="text-xs font-bold text-brand-600">{scopeLabels[item.scope_type]}</p><p className="mt-1 font-semibold">{item.scope_key}</p><p className="mt-1 text-xs text-slate-400">{new Date(item.captured_at).toLocaleString('zh-CN')}</p></div><div className="text-right"><p className="font-bold">¥{item.gmv ?? '—'}</p><p className="text-xs text-slate-500">GMV</p></div></div><div className="mt-4 grid grid-cols-4 gap-2 rounded-xl bg-slate-50 p-3 text-center"><div><p className="text-sm font-bold">{item.product_views ?? '—'}</p><p className="text-[10px] text-slate-500">访问</p></div><div><p className="text-sm font-bold">{item.add_to_cart ?? '—'}</p><p className="text-[10px] text-slate-500">加购</p></div><div><p className="text-sm font-bold">{item.orders ?? '—'}</p><p className="text-[10px] text-slate-500">订单</p></div><div><p className="text-sm font-bold">{item.paid_orders ?? '—'}</p><p className="text-[10px] text-slate-500">支付</p></div></div></Card>)}</div> : <Card><EmptyState icon={<Store className="h-6 w-6" />} title="尚无京东数据" description="从京东后台查看店铺、SKU 或活动累计值后手动录入。" /></Card>}</div><div><h2 className="mb-3 font-bold">归因证据</h2>{evidenceRows.length ? <div className="space-y-3">{evidenceRows.map((item) => <EvidenceCard key={item.id} evidence={item} publications={publicationRows} commerce={commerceRows} />)}</div> : <Card><EmptyState icon={<Link2 className="h-6 w-6" />} title="尚无归因证据" description="录入小红书发布记录和京东快照后，可用专属链接、口令或活动关系建立证据。" /></Card>}</div></section></div>
    {modal === 'commerce' && <CommerceModal onClose={() => setModal(null)} />}{modal === 'attribution' && <AttributionModal publications={publicationRows} commerce={commerceRows} onClose={() => setModal(null)} />}{modal === 'feedback' && <FeedbackRunModal publications={publicationRows} eligibleIds={eligibleIds} commerce={commerceRows} onClose={() => setModal(null)} />}
  </div>
}
