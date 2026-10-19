import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BadgeCheck, CheckCircle2, FileCheck2, Gauge, Plus, ShieldAlert, Sparkles, Upload } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal, StatusBadge, TextAreaField } from '../components/ui'
import { api } from '../lib/api'
import type { EvidenceDocument, IngestionAnalysis, ProductPayload, RegistryItemDetail } from '../types'

function EvidenceModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'ai' | 'manual'>('ai')
  const [form, setForm] = useState({
    title: '',
    documentType: 'product_specification',
    sourceUri: '',
    content: '',
  })
  const [sourceText, setSourceText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [aiNotes, setAiNotes] = useState<{
    summary: string
    excerpts: string[]
    warnings: string[]
  } | null>(null)
  const [dedup, setDedup] = useState<IngestionAnalysis | null>(null)
  const [duplicateReason, setDuplicateReason] = useState('')
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: async () => {
      const currentDedup = dedup
      const document = await api.createEvidence({
        title: form.title,
        document_type: form.documentType,
        source_uri: form.sourceUri,
        content: form.content,
      })
      if (currentDedup)
        await api.resolveIngestion(currentDedup.ingestion_id, {
          decision: currentDedup.duplicate_status === 'none' ? 'new_item' : 'independent',
          decision_reason: duplicateReason,
          resulting_evidence_document_id: document.id,
        })
      return document
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['evidence'] })
      await queryClient.invalidateQueries({ queryKey: ['claim-coverage'] })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '证据保存失败'),
  })
  const aiMutation = useMutation({
    mutationFn: () => api.evidenceAiDraft(form.sourceUri, sourceText, file),
    onSuccess: (draft) => {
      setForm({
        title: draft.title,
        documentType: draft.document_type,
        sourceUri: draft.source_uri,
        content: draft.content,
      })
      setAiNotes({
        summary: draft.source_summary,
        excerpts: draft.relevant_excerpts,
        warnings: draft.warnings,
      })
      setDedup(draft.dedup || null)
      setError('')
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : 'AI 整理失败'),
  })
  return (
    <Modal title="录入证据文档" description="AI 可协助分类和摘录，但原始证据、来源与最终核验仍由运营人员负责。" onClose={onClose} wide>
      <div className="space-y-5">
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === 'ai' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => setMode('ai')}>
            <Sparkles className="mr-2 inline h-4 w-4" />
            AI 整理资料
          </button>
          <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === 'manual' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => setMode('manual')}>
            手动填写
          </button>
        </div>
        <Callout title="什么可以作为证据">优先使用确认版规格书、检测报告、材料证明或品牌正式批准文件。AI 不会核验文件真实性，也不会把供应商宣传自动变成产品事实。</Callout>
        {mode === 'ai' && (
          <div className="space-y-5 rounded-2xl border border-brand-100 bg-brand-50/30 p-5">
            <Field label="原文件位置或来源 URL" example="repo://knowledge/products/NOTE01/spec-v1.pdf" hint="填写团队以后仍能找到原文件的位置；本地文件名本身不足以追溯。" value={form.sourceUri} onChange={(event) => setForm({ ...form, sourceUri: event.target.value })} />
            <label className="block rounded-2xl border-2 border-dashed border-brand-200 bg-white p-5 text-center">
              <Upload className="mx-auto h-6 w-6 text-brand-600" />
              <span className="mt-2 block text-sm font-semibold">上传规格书、检测报告或材料证明</span>
              <span className="mt-1 block text-xs text-slate-500">支持 TXT、Markdown、PDF、Word、Excel，单文件不超过 15 MB</span>
              <input className="mt-4 block w-full text-xs" type="file" accept=".txt,.md,.pdf,.docx,.xlsx" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            </label>
            <TextAreaField label="也可以粘贴原文" example="粘贴文件中与产品规格、材料或检测结论有关的原始文字……" hint="上传文件与粘贴内容可二选一；两者都有时会合并整理。" value={sourceText} onChange={(event) => setSourceText(event.target.value)} />
            <div className="flex justify-end">
              <Button disabled={!form.sourceUri || (!file && !sourceText.trim())} loading={aiMutation.isPending} onClick={() => aiMutation.mutate()}>
                <Sparkles className="h-4 w-4" />
                调用 LLM 整理
              </Button>
            </div>
          </div>
        )}
        {(mode === 'manual' || aiNotes) && (
          <div className="space-y-5">
            {aiNotes && (
              <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4 text-xs leading-5 text-blue-900">
                <p className="font-bold">AI 整理摘要</p>
                <p className="mt-1">{aiNotes.summary}</p>
                {!!aiNotes.excerpts.length && <p className="mt-2 text-blue-700">识别到 {aiNotes.excerpts.length} 条可能相关摘录；请在下方原文中核对。</p>}
                {aiNotes.warnings.map((warning) => (
                  <p className="mt-1 text-amber-700" key={warning}>
                    注意：{warning}
                  </p>
                ))}
              </div>
            )}
            {dedup && dedup.duplicate_status !== 'none' && (
              <Callout title="发现相近证据文档" tone="warning">
                <p>
                  {dedup.message}：{dedup.matches.map((match) => match.label).join('、')}
                </p>
                <div className="mt-3">
                  <TextAreaField label="仍作为独立证据保存的原因" example="这是同一产品的新版本检测报告，报告编号和测试日期不同。" value={duplicateReason} onChange={(event) => setDuplicateReason(event.target.value)} />
                </div>
              </Callout>
            )}
            <div className="grid gap-5 md:grid-cols-2">
              <Field label="证据标题" example="NOTE01 功能与材料确认表 v1" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
              <label className="block space-y-2">
                <span className="text-sm font-semibold">文档类型</span>
                <select className="field-control" value={form.documentType} onChange={(event) => setForm({ ...form, documentType: event.target.value })}>
                  <option value="product_specification">产品规格</option>
                  <option value="test_report">检测报告</option>
                  <option value="material_certificate">材料证明</option>
                  <option value="brand_approval">品牌批准文件</option>
                  <option value="other">其他正式资料</option>
                </select>
              </label>
            </div>
            {mode === 'manual' && <Field label="来源位置" example="repo://knowledge/products/... 或正式文件 URL" value={form.sourceUri} onChange={(event) => setForm({ ...form, sourceUri: event.target.value })} />}
            <TextAreaField label="证据原文" example="粘贴必要原文并保留章节、页码或表格标题。" hint="AI 模式会保留提取出的原文；可以删除无关内容，但不要把摘要当作原文。" value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} />
          </div>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end">
          <Button disabled={!form.title || !form.sourceUri || !form.content || (!!dedup && dedup.duplicate_status !== 'none' && !duplicateReason.trim())} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            保存待核验证据
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ClaimModal({ products, evidence, onClose }: { products: RegistryItemDetail[]; evidence: EvidenceDocument[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    stableKey: '',
    statement: '',
    allowed: '',
    forbidden: '',
    riskLevel: 'medium',
    productId: products[0]?.id || '',
    evidenceId: evidence[0]?.id || '',
  })
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () =>
      api.createRegistryItem('product_claim', {
        stable_key: form.stableKey,
        payload: {
          statement: form.statement,
          allowed_expressions: form.allowed
            .split('\n')
            .map((item) => item.trim())
            .filter(Boolean),
          forbidden_expressions: form.forbidden
            .split('\n')
            .map((item) => item.trim())
            .filter(Boolean),
          risk_level: form.riskLevel,
          product_item_ids: [form.productId],
          evidence_document_ids: [form.evidenceId],
          effective_from: null,
          effective_to: null,
        },
        search_text: `${form.statement} ${form.allowed}`,
        source_uri: 'ui://claim-and-evidence',
        verification_status: 'provisional',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['registry', 'product_claim'],
      })
      await queryClient.invalidateQueries({ queryKey: ['claim-coverage'] })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : 'Claim 保存失败'),
  })
  return (
    <Modal title="创建 Product Claim 草稿" description="定义允许怎样说、绝对不能怎样说，并关联具体产品和已核验证据。" onClose={onClose} wide>
      <div className="space-y-5">
        <Callout title="Claim 不是文案">Claim 是可复用的宣传边界。Writer 只能使用已激活 Claim 的允许表述，Compliance 会检查引用和禁用表述。</Callout>
        <div className="grid gap-5 md:grid-cols-2">
          <Field
            label="Claim Key"
            example="note01-nfc-interaction"
            value={form.stableKey}
            onChange={(event) =>
              setForm({
                ...form,
                stableKey: event.target.value.toLowerCase().replace(/\s+/g, '-'),
              })
            }
          />
          <label className="block space-y-2">
            <span className="text-sm font-semibold">风险等级</span>
            <select className="field-control" value={form.riskLevel} onChange={(event) => setForm({ ...form, riskLevel: event.target.value })}>
              <option value="low">低</option>
              <option value="medium">中</option>
              <option value="high">高</option>
              <option value="critical">关键</option>
            </select>
          </label>
          <label className="block space-y-2">
            <span className="text-sm font-semibold">适用产品</span>
            <select className="field-control" value={form.productId} onChange={(event) => setForm({ ...form, productId: event.target.value })}>
              {products.map((product) => {
                const payload = product.revisions.find((revision) => revision.id === product.current_revision_id)?.payload as unknown as ProductPayload
                return (
                  <option key={product.id} value={product.id}>
                    {payload?.name || product.stable_key}
                  </option>
                )
              })}
            </select>
          </label>
          <label className="block space-y-2">
            <span className="text-sm font-semibold">证据文档</span>
            <select className="field-control" value={form.evidenceId} onChange={(event) => setForm({ ...form, evidenceId: event.target.value })}>
              {evidence.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
        </div>
        <TextAreaField label="声明事实" example="NOTE01 支持 NFC 信息交互。" value={form.statement} onChange={(event) => setForm({ ...form, statement: event.target.value })} />
        <div className="grid gap-5 md:grid-cols-2">
          <TextAreaField label="允许表述" example={'支持 NFC 数字体验\n通过 NFC 打开预设数字内容'} hint="每行一项，必须能由所选证据支持。" value={form.allowed} onChange={(event) => setForm({ ...form, allowed: event.target.value })} />
          <TextAreaField label="禁止表述" example={'治疗焦虑\n保证改善睡眠\n医疗级监测'} hint="每行一项，包括容易越界的近似说法。" value={form.forbidden} onChange={(event) => setForm({ ...form, forbidden: event.target.value })} />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end">
          <Button disabled={!form.stableKey || !form.statement || !form.allowed.trim() || !form.productId || !form.evidenceId} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            保存 Claim 草稿
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function ClaimsPage() {
  const { principal } = useAuth()
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const canReview = principal?.role === 'admin' || principal?.role === 'reviewer'
  const queryClient = useQueryClient()
  const [showEvidence, setShowEvidence] = useState(false)
  const [showClaim, setShowClaim] = useState(false)
  const evidence = useQuery({
    queryKey: ['evidence'],
    queryFn: api.listEvidence,
  })
  const claimItems = useQuery({
    queryKey: ['registry', 'product_claim'],
    queryFn: () => api.listRegistry('product_claim'),
  })
  const coverage = useQuery({
    queryKey: ['claim-coverage'],
    queryFn: api.getClaimCoverage,
  })
  const claims = useQuery({
    queryKey: ['registry', 'product_claim', 'details', claimItems.data?.map((item) => item.updated_at).join(',')],
    queryFn: () => Promise.all((claimItems.data || []).map((item) => api.getRegistryItem('product_claim', item.id))),
    enabled: !!claimItems.data,
  })
  const productItems = useQuery({
    queryKey: ['registry', 'product'],
    queryFn: () => api.listRegistry('product'),
  })
  const products = useQuery({
    queryKey: ['registry', 'product', 'claim-details', productItems.data?.map((item) => item.updated_at).join(',')],
    queryFn: () => Promise.all((productItems.data || []).filter((item) => item.current_revision_id).map((item) => api.getRegistryItem('product', item.id))),
    enabled: !!productItems.data,
  })
  const verifiedEvidence = useMemo(() => (evidence.data || []).filter((item) => item.verified_at && item.is_active), [evidence.data])
  const verify = useMutation({
    mutationFn: api.verifyEvidence,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['evidence'] })
      await queryClient.invalidateQueries({ queryKey: ['claim-coverage'] })
    },
  })
  const activate = useMutation({
    mutationFn: ({ itemId, revisionId }: { itemId: string; revisionId: string }) => api.activateRevision('product_claim', itemId, revisionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['registry', 'product_claim'],
      })
      await queryClient.invalidateQueries({ queryKey: ['claim-coverage'] })
    },
  })
  if ([evidence, claimItems, claims, products, coverage].some((query) => query.isLoading)) return <LoadingBlock label="正在读取声明与证据" />
  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Claims & Evidence"
        title="声明与证据"
        description="将“产品是什么”与“对外可以怎么说”分开治理，所有效果声明都必须回到证据。"
        actions={
          canWrite ? (
            <>
              <Button variant="secondary" onClick={() => setShowEvidence(true)}>
                <FileCheck2 className="h-4 w-4" />
                录入证据
              </Button>
              <Button disabled={!verifiedEvidence.length || !(products.data || []).length} onClick={() => setShowClaim(true)}>
                <Plus className="h-4 w-4" />
                新建 Claim
              </Button>
            </>
          ) : undefined
        }
      />
      {!verifiedEvidence.length && (
        <Callout title="先核验证据，再创建可激活 Claim" tone="warning">
          Editor/Admin 可以录入证据；Reviewer/Admin 核验后，证据才能支撑 Claim 激活。
        </Callout>
      )}
      {coverage.data && (
        <Card className="mt-6 p-5">
          <div className="flex items-center gap-2 text-sm font-bold text-graphite"><Gauge className="h-5 w-5 text-brand-600" />知识覆盖率</div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-brand-50 p-4"><p className="text-2xl font-bold text-brand-800">{coverage.data.product_claim_coverage_percent}%</p><p className="mt-1 text-xs text-slate-500">有 Claim 的产品 · {coverage.data.products_with_claims}/{coverage.data.products_total}</p></div>
            <div className="rounded-2xl bg-emerald-50 p-4"><p className="text-2xl font-bold text-emerald-800">{coverage.data.claim_evidence_coverage_percent}%</p><p className="mt-1 text-xs text-slate-500">证据完整的 Claim · {coverage.data.fully_supported_claims}/{coverage.data.claims_total}</p></div>
            <div className="rounded-2xl bg-slate-50 p-4"><p className="text-2xl font-bold text-slate-800">{coverage.data.verified_evidence_documents}</p><p className="mt-1 text-xs text-slate-500">实际支撑 Claim 的已核验证据</p></div>
          </div>
          <div className="mt-4 grid gap-2 lg:grid-cols-2">
            {coverage.data.products.map((product) => (
              <div key={product.product_item_id} className="rounded-xl border border-slate-100 bg-white px-4 py-3">
                <div className="flex items-center justify-between gap-3"><span className="text-sm font-semibold">{product.product_name}</span><span className={`text-xs font-bold ${product.status === 'covered' ? 'text-emerald-700' : 'text-amber-700'}`}>{product.status === 'covered' ? '覆盖完整' : product.status === 'no_claims' ? '缺少 Claim' : '证据有缺口'}</span></div>
                <p className="mt-1 text-xs text-slate-500">Claim {product.fully_supported_claims}/{product.active_claims} 完整 · 证据 {product.verified_evidence_documents} 份</p>
                {product.warnings.map((warning) => <p key={warning} className="mt-1 text-xs text-amber-700">{warning}</p>)}
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] leading-5 text-slate-400">覆盖率用于提示知识准备程度，不等于产品真实性认证；缺失项不会阻断内容生成。</p>
        </Card>
      )}
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <div>
          <h2 className="mb-3 text-sm font-bold text-slate-500">证据文档</h2>
          <div className="space-y-3">
            {(evidence.data || []).map((item) => (
              <Card key={item.id} className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold">{item.title}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {item.document_type} · {item.source_uri}
                    </p>
                    <p className="mt-3 line-clamp-3 text-xs leading-5 text-slate-600">{item.content}</p>
                  </div>
                  {item.verified_at ? (
                    <span className="flex items-center gap-1 text-xs font-bold text-emerald-600">
                      <CheckCircle2 className="h-4 w-4" />
                      已核验
                    </span>
                  ) : canReview ? (
                    <Button variant="secondary" loading={verify.isPending} onClick={() => verify.mutate(item.id)}>
                      核验证据
                    </Button>
                  ) : (
                    <span className="text-xs text-amber-600">待核验</span>
                  )}
                </div>
              </Card>
            ))}
            {!(evidence.data || []).length && (
              <Card>
                <EmptyState icon={<FileCheck2 className="h-6 w-6" />} title="还没有证据" description="先录入能够支持产品声明的正式资料。" />
              </Card>
            )}
          </div>
        </div>
        <div>
          <h2 className="mb-3 text-sm font-bold text-slate-500">Product Claims</h2>
          <div className="space-y-3">
            {(claims.data || []).map((claim) => {
              const current = claim.revisions.find((revision) => revision.id === claim.current_revision_id)
              const latest = [...claim.revisions].sort((a, b) => b.version - a.version)[0]
              const payload = (current || latest)?.payload as Record<string, unknown>
              const draft = claim.revisions.find((revision) => revision.status === 'draft')
              return (
                <Card key={claim.id} className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={current ? 'active' : 'draft'} />
                        <span className="text-xs font-bold uppercase text-red-500">{String(payload.risk_level)}</span>
                      </div>
                      <p className="mt-3 font-semibold">{String(payload.statement)}</p>
                      <p className="mt-2 text-xs leading-5 text-slate-500">
                        允许：
                        {((payload.allowed_expressions as string[]) || []).join('；')}
                      </p>
                    </div>
                    {draft && canReview && (
                      <Button
                        variant="secondary"
                        loading={activate.isPending}
                        onClick={() =>
                          activate.mutate({
                            itemId: claim.id,
                            revisionId: draft.id,
                          })
                        }
                      >
                        <BadgeCheck className="h-4 w-4" />
                        激活
                      </Button>
                    )}
                  </div>
                </Card>
              )
            })}
            {!(claims.data || []).length && (
              <Card>
                <EmptyState icon={<ShieldAlert className="h-6 w-6" />} title="还没有 Product Claim" description="有已核验证据后，再建立允许表述和禁止表述。" />
              </Card>
            )}
          </div>
        </div>
      </div>
      {showEvidence && <EvidenceModal onClose={() => setShowEvidence(false)} />}
      {showClaim && <ClaimModal products={products.data || []} evidence={verifiedEvidence} onClose={() => setShowClaim(false)} />}
    </div>
  )
}
