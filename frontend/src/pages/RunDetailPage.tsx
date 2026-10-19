import clsx from 'clsx'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Image as ImageIcon, Film, Megaphone, LoaderCircle, MessageSquareText, RefreshCw, RotateCcw, ShieldAlert, Sparkles, XCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { PageHelpButton } from '../components/PageHeader'
import { Button, Callout, Card, LoadingBlock, StatusBadge, TextAreaField } from '../components/ui'
import { api } from '../lib/api'
import { buildMediaProductionPrompt } from '../lib/mediaPrompt'
import type { ComplianceReport, ContentCandidate, ScoreReport } from '../types'

const dimensionLabels: Record<string, string> = {
  Hook: '开头吸引力',
  Emotion: '情绪共鸣',
  Authenticity: '真实感',
  Visual: '视觉潜力',
  SaveValue: '收藏价值',
  Conversion: '转化自然度',
}

function CandidateCard({ candidate, compliance, score, selected, recommended, finalized, onSelect }: { candidate: ContentCandidate; compliance?: ComplianceReport; score?: ScoreReport; selected: boolean; recommended: boolean; finalized: boolean; onSelect: () => void }) {
  const mediaPrompt = finalized ? buildMediaProductionPrompt(candidate) : candidate.payload.media_plan.preferred_generation_prompt
  return (
    <Card className={clsx('relative cursor-pointer overflow-hidden transition duration-200', selected ? 'ring-2 ring-brand-500 shadow-lift' : 'hover:-translate-y-1 hover:shadow-lift')}>
      <button className="absolute inset-0 z-0" aria-label={`选择候选 ${candidate.route_key}`} onClick={onSelect} />
      <div className="relative z-10 pointer-events-none">
        <div className="border-b border-slate-100 bg-gradient-to-r from-brand-50 to-white p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-brand-700 shadow-sm">{candidate.route_key}</span>
                {recommended && <span className="rounded-full bg-brand-600 px-2.5 py-1 text-[11px] font-bold text-white">系统推荐</span>}
              </div>
              <h2 className="mt-3 text-lg font-bold text-graphite">{candidate.payload.recommended_title}</h2>
            </div>
            {score && <div className={clsx('flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-4 text-base font-bold', score.passed ? 'border-emerald-100 bg-emerald-50 text-emerald-700' : 'border-amber-100 bg-amber-50 text-amber-700')}>{score.total_score}</div>}
          </div>
        </div>
        <div className="p-5">
          <div className="flex flex-wrap gap-2">
            {candidate.payload.title_options.map((title) => (
              <span key={title} className={clsx('rounded-xl px-2.5 py-1.5 text-xs', title === candidate.payload.recommended_title ? 'bg-brand-50 font-semibold text-brand-700' : 'bg-slate-50 text-slate-500')}>
                {title}
              </span>
            ))}
          </div>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-600">{candidate.payload.body}</p>
          <div className="mt-5 rounded-2xl bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
              <ImageIcon className="h-4 w-4 text-brand-600" />
              视觉建议
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {candidate.payload.visual_brief.cover_concept} · {candidate.payload.visual_brief.scene}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {candidate.payload.visual_brief.shot_list.map((shot) => (
                <span key={shot} className="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">
                  {shot}
                </span>
              ))}
            </div>
          </div>
          {candidate.payload.media_plan && (
            <div className="pointer-events-auto relative z-20 mt-4 rounded-2xl border border-brand-100 bg-brand-50/50 p-4" onClick={(event) => event.stopPropagation()}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-bold text-brand-900">
                  {candidate.payload.media_plan.preferred_format === 'video' ? <Film className="h-4 w-4" /> : <ImageIcon className="h-4 w-4" />}
                  {finalized ? '已选方案制作提示词' : '候选媒体提示词'} · {candidate.payload.media_plan.preferred_format === 'video' ? '视频优先' : '图片组优先'}
                </div>
                <button className="rounded-lg bg-white px-2 py-1 text-[11px] font-semibold text-brand-700 shadow-sm" onClick={() => navigator.clipboard.writeText(mediaPrompt)}>
                  {finalized ? '复制完整提示词' : '复制简版提示词'}
                </button>
              </div>
              <p className="mt-2 text-xs leading-5 text-brand-800">{candidate.payload.media_plan.rationale}</p>
              <div className="mt-3 whitespace-pre-wrap rounded-xl bg-white p-3 text-xs leading-5 text-slate-600">{mediaPrompt}</div>
              <details className="mt-3 text-xs text-slate-600">
                <summary className="cursor-pointer font-semibold">查看备用形式与负面提示词</summary>
                <p className="mt-2">
                  备用 {candidate.payload.media_plan.alternate_format === 'video' ? '视频' : '图片组'}：{candidate.payload.media_plan.alternate_generation_prompt}
                </p>
                {candidate.payload.media_plan.negative_prompts.length > 0 && (
                  <p className="mt-2">
                    避免：
                    {candidate.payload.media_plan.negative_prompts.join('、')}
                  </p>
                )}
              </details>
            </div>
          )}
          <div className="mt-5 flex flex-wrap gap-2">
            {candidate.payload.tags.map((tag) => (
              <span key={tag} className="text-xs text-brand-600">
                #{tag}
              </span>
            ))}
          </div>
          <div className="mt-5 border-t border-slate-100 pt-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">合规状态</span>
              {compliance ? (
                <span className={clsx('inline-flex items-center gap-1 text-xs font-bold', compliance.has_blockers ? 'text-red-600' : 'text-emerald-600')}>
                  {compliance.has_blockers ? <ShieldAlert className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
                  {compliance.has_blockers ? '存在阻断项' : '当前版本通过'}
                </span>
              ) : (
                <span className="text-xs text-slate-400">等待报告</span>
              )}
            </div>
            {compliance?.findings.length ? (
              <div className="mt-3 space-y-2">
                {compliance.findings.slice(0, 3).map((finding) => (
                  <div key={finding.id} className={clsx('rounded-xl px-3 py-2 text-xs leading-5', finding.severity === 'blocker' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700')}>
                    <strong>{finding.category}</strong>：{finding.message}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          {score && (
            <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
              {score.dimensions.map((dimension) => (
                <div key={dimension.name}>
                  <div className="flex justify-between text-[11px] text-slate-500">
                    <span>{dimensionLabels[dimension.name] || dimension.name}</span>
                    <span>{dimension.score}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand-500" style={{ width: `${dimension.score}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
            <span className="text-xs text-slate-400">Content Version {candidate.current_version}</span>
            <span className={clsx('flex items-center gap-1.5 text-sm font-semibold', selected ? 'text-brand-600' : 'text-slate-400')}>
              {selected && <Check className="h-4 w-4" />}
              {selected ? '已选择' : '点击选择'}
            </span>
          </div>
        </div>
      </div>
    </Card>
  )
}

export function RunDetailPage() {
  const { runId = '' } = useParams()
  const { principal } = useAuth()
  const queryClient = useQueryClient()
  const runQuery = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRun(runId),
    refetchInterval: (query) => (['queued', 'running', 'waiting_human'].includes(query.state.data?.status || '') ? 2500 : false),
  })
  const contentReady = !!runQuery.data && ['waiting_human', 'ready_for_manual_publish', 'rejected'].includes(runQuery.data.status)
  const contextsQuery = useQuery({
    queryKey: ['run', runId, 'contexts'],
    queryFn: () => api.getRunContexts(runId),
    enabled: !!runQuery.data && !['queued', 'failed'].includes(runQuery.data.status),
    refetchInterval: runQuery.data?.status === 'running' ? 2500 : false,
  })
  const coverageQuery = useQuery({
    queryKey: ['run', runId, 'claim-coverage'],
    queryFn: () => api.getRunClaimCoverage(runId),
    enabled: !!runQuery.data,
  })
  const candidatesQuery = useQuery({
    queryKey: ['run', runId, 'candidates'],
    queryFn: () => api.getCandidates(runId),
    enabled: contentReady,
  })
  const complianceQuery = useQuery({
    queryKey: ['run', runId, 'compliance'],
    queryFn: () => api.getCompliance(runId),
    enabled: contentReady,
  })
  const scoresQuery = useQuery({
    queryKey: ['run', runId, 'scores'],
    queryFn: () => api.getScores(runId),
    enabled: contentReady,
  })
  const strategyQuery = useQuery({
    queryKey: ['run', runId, 'strategy'],
    queryFn: () => api.getStrategy(runId),
    enabled: contentReady,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [changeRequest, setChangeRequest] = useState('')
  const [editedBody, setEditedBody] = useState('')
  const [reviewMode, setReviewMode] = useState<'none' | 'changes' | 'edit'>('none')
  const [reviewError, setReviewError] = useState('')
  const candidates = useMemo(() => candidatesQuery.data || [], [candidatesQuery.data])
  const productContext = contextsQuery.data?.find((context) => context.context_type === 'product')
  const knowledgeWarnings = Array.isArray(productContext?.payload.missing_information)
    ? (productContext.payload.missing_information as string[])
    : []
  const provisionalFacts = Array.isArray(productContext?.payload.provisional_facts)
    ? (productContext.payload.provisional_facts as Array<{ revision_id: string; statement: string }>)
    : []
  const allowedClaims = Array.isArray(productContext?.payload.allowed_claims)
    ? productContext.payload.allowed_claims
    : []
  useEffect(() => {
    if (!selectedId && runQuery.data && candidates.length) setSelectedId(runQuery.data.recommended_candidate_id || candidates[0].id)
  }, [candidates, runQuery.data, selectedId])
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedId)
  const complianceMap = new Map((complianceQuery.data || []).map((report) => [report.content_version_id, report]))
  const scoreMap = new Map((scoresQuery.data || []).map((report) => [report.content_version_id, report]))
  const canReview = runQuery.data?.status === 'waiting_human' && (principal?.role === 'reviewer' || principal?.role === 'admin')
  const reviewMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.submitReview(runId, payload),
    onSuccess: async () => {
      setReviewMode('none')
      await queryClient.invalidateQueries({ queryKey: ['run', runId] })
    },
    onError: (reason) => setReviewError(reason instanceof Error ? reason.message : '审核提交失败'),
  })
  if (runQuery.isLoading) return <LoadingBlock label="正在读取运行详情" />
  const run = runQuery.data
  if (!run)
    return (
      <Callout title="找不到该运行" tone="warning">
        请返回运行列表重新选择。
      </Callout>
    )

  const submitDecision = (decision: string) => {
    setReviewError('')
    const payload: Record<string, unknown> = { decision }
    if (decision !== 'rejected') payload.selected_candidate_id = selectedId
    if (decision === 'request_changes') payload.change_request = changeRequest
    if (decision === 'approved_with_edit' && selectedCandidate)
      payload.edited_content = {
        ...selectedCandidate.payload,
        body: editedBody,
      }
    reviewMutation.mutate(payload)
  }

  return (
    <div className="animate-fade-up">
      <div className="mb-5 flex items-center justify-between">
        <Link to="/runs" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-brand-600">
          <ArrowLeft className="h-4 w-4" />
          返回运行列表
        </Link>
        <div className="flex items-center gap-2">
          <PageHelpButton title="运行详情" />
          <Button variant="secondary" onClick={() => runQuery.refetch()} loading={runQuery.isFetching}>
            <RefreshCw className="h-4 w-4" />
            刷新
          </Button>
        </div>
      </div>
      <Card className="overflow-hidden">
        <div className="flex flex-col justify-between gap-5 bg-gradient-to-r from-brand-900 to-brand-700 px-6 py-6 text-white md:flex-row md:items-center">
          <div>
            <div className="flex items-center gap-3">
              <StatusBadge status={run.status} />
              <span className="text-xs uppercase tracking-wider text-blue-200">本地正式流程</span>
            </div>
            <h1 className="mt-4 text-2xl font-bold">内容运行 {run.id.slice(0, 8)}</h1>
            <p className="mt-2 text-sm text-blue-100">
              冻结 {run.registry_revision_ids.length} 个 Registry Revision · Thread {run.thread_id.slice(0, 8)}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-2xl bg-white/10 px-4 py-3">
              <p className="text-xl font-bold">3</p>
              <p className="text-[11px] text-blue-100">目标候选</p>
            </div>
            <div className="rounded-2xl bg-white/10 px-4 py-3">
              <p className="text-xl font-bold">2</p>
              <p className="text-[11px] text-blue-100">最多返工</p>
            </div>
            <div className="rounded-2xl bg-white/10 px-4 py-3">
              <p className="text-xl font-bold">6</p>
              <p className="text-[11px] text-blue-100">评分维度</p>
            </div>
          </div>
        </div>
      </Card>
      {coverageQuery.data && (
        <Card className="mt-5 p-5">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div><p className="text-sm font-bold text-graphite">本次 Run 冻结的 Claim / 证据覆盖</p><p className="mt-1 text-xs text-slate-500">只计算启动时冻结的产品和 Claim，避免被后续知识修改误导。</p></div>
            <div className="flex gap-5 text-right"><div><p className="text-xl font-bold text-brand-800">{coverageQuery.data.product_claim_coverage_percent}%</p><p className="text-[11px] text-slate-500">产品有 Claim</p></div><div><p className="text-xl font-bold text-emerald-800">{coverageQuery.data.claim_evidence_coverage_percent}%</p><p className="text-[11px] text-slate-500">Claim 证据完整</p></div></div>
          </div>
          {coverageQuery.data.products.some((product) => product.status !== 'covered') && <div className="mt-3 rounded-xl bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">本次运行存在 Claim 或证据缺口。内容仍可生成，但人工审核必须避免把基础产品描述扩写为未经证实的效果声明。</div>}
        </Card>
      )}
      {knowledgeWarnings.length > 0 && (
        <div className="mt-6">
          <Callout title="产品事实与证据提醒" tone="warning">
            <ul className="list-disc space-y-1 pl-5">
              {knowledgeWarnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
            <p className="mt-2">这些缺失项不阻止内容生成，但候选稿不得自行补充未证实参数、功效或健康结论。</p>
          </Callout>
        </div>
      )}
      {productContext && (provisionalFacts.length > 0 || allowedClaims.length === 0) && (
        <div className="mt-4">
          <Callout title="事实治理状态" tone="warning">
            当前上下文包含 {provisionalFacts.length} 条待验证产品事实，允许使用的已证实 Claim 为 {allowedClaims.length} 条。审核通过只表示内容流程完成，不代表这些产品事实已经获得外部证据验证。
            {provisionalFacts.length > 0 && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer font-semibold">查看待验证事实原文</summary>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {provisionalFacts.map((fact, index) => <li key={`${fact.revision_id}-${index}`}>{fact.statement}</li>)}
                </ul>
              </details>
            )}
          </Callout>
        </div>
      )}
      {['queued', 'running'].includes(run.status) && (
        <Card className="mt-6">
          <div className="flex min-h-64 flex-col items-center justify-center text-center">
            <div className="relative">
              <div className="absolute inset-0 animate-ping rounded-full bg-brand-100" />
              <div className="relative rounded-full bg-brand-50 p-5 text-brand-600">
                <LoaderCircle className="h-8 w-8 animate-spin" />
              </div>
            </div>
            <h2 className="mt-6 text-lg font-bold">Agent 正在协作生成</h2>
            <p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">产品上下文、策略、三稿、合规和评分会依次持久化。页面每 2.5 秒自动更新，无需重复启动。</p>
          </div>
        </Card>
      )}
      {run.status === 'waiting_knowledge_review' && (
        <div className="mt-6">
          <Callout title="平台知识需要先复核" tone="warning">
            Critical 平台规则已经过期或缺失。请由 Reviewer 更新规则后再恢复流程。
          </Callout>
        </div>
      )}
      {run.status === 'failed' && (
        <div className="mt-6">
          <Callout title="运行失败" tone="warning">
            {JSON.stringify(run.error)}
          </Callout>
        </div>
      )}
      {contentReady && strategyQuery.data?.payload.marketing_support && (
        <Card className="mt-6 p-5">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-violet-50 p-3 text-violet-600">
              <Megaphone className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-bold">小红书营销支持建议</h2>
                <span className={clsx('rounded-full px-2 py-1 text-[11px] font-bold', strategyQuery.data.payload.marketing_support.recommended ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-600')}>{strategyQuery.data.payload.marketing_support.recommended ? '建议评估申请' : '当前不建议申请'}</span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">{strategyQuery.data.payload.marketing_support.rationale.join('；') || 'Strategy 未提供额外理由。'}</p>
              {strategyQuery.data.payload.marketing_support.program_names.length > 0 && (
                <p className="mt-2 text-xs text-violet-700">
                  候选方案：
                  {strategyQuery.data.payload.marketing_support.program_names.join('、')}
                </p>
              )}
              {strategyQuery.data.payload.marketing_support.application_checklist.length > 0 && (
                <details className="mt-3 text-xs text-slate-600">
                  <summary className="cursor-pointer font-semibold">查看人工申请清单</summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {strategyQuery.data.payload.marketing_support.application_checklist.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </details>
              )}
              <p className="mt-3 text-[11px] text-slate-400">这是内部决策建议，不会自动提交申请、投放或承诺效果。</p>
            </div>
          </div>
        </Card>
      )}
      {contentReady && (
        <>
          <div className="mt-7 flex items-end justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-brand-600">Candidate Comparison</p>
              <h2 className="mt-2 text-2xl font-bold">比较三个候选</h2>
              <p className="mt-1 text-sm text-slate-500">选择稿件不会立即提交，只有底部审核动作才会写入系统。</p>
            </div>
          </div>
          {candidatesQuery.isLoading ? (
            <LoadingBlock label="正在聚合候选、合规和评分" />
          ) : (
            <div className="mt-5 grid items-start gap-5 xl:grid-cols-3">
              {candidates.map((candidate) => (
                <CandidateCard
                  key={candidate.id}
                  candidate={candidate}
                  compliance={complianceMap.get(candidate.content_version_id)}
                  score={scoreMap.get(candidate.content_version_id)}
                  selected={candidate.id === selectedId}
                  recommended={candidate.id === run.recommended_candidate_id}
                  finalized={run.status === 'ready_for_manual_publish' && candidate.id === run.selected_candidate_id}
                  onSelect={() => {
                    setSelectedId(candidate.id)
                    setEditedBody(candidate.payload.body)
                  }}
                />
              ))}
            </div>
          )}
        </>
      )}
      {canReview && (
        <Card className="sticky bottom-4 z-20 mt-6 border-brand-100 p-5 shadow-lift">
          <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
            <div>
              <p className="flex items-center gap-2 font-bold text-graphite">
                <MessageSquareText className="h-5 w-5 text-brand-600" />
                人工审核决策
              </p>
              <p className="mt-1 text-xs text-slate-500">
                当前选择：
                {selectedCandidate?.payload.recommended_title || '请选择候选'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="danger" onClick={() => submitDecision('rejected')} loading={reviewMutation.isPending}>
                <XCircle className="h-4 w-4" />
                全部拒绝
              </Button>
              <Button variant="secondary" onClick={() => setReviewMode('changes')}>
                <RotateCcw className="h-4 w-4" />
                要求修改
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setReviewMode('edit')
                  setEditedBody(selectedCandidate?.payload.body || '')
                }}
              >
                <Sparkles className="h-4 w-4" />
                编辑后批准
              </Button>
              <Button disabled={!selectedId || complianceMap.get(selectedCandidate?.content_version_id || '')?.has_blockers} onClick={() => submitDecision('approved')} loading={reviewMutation.isPending}>
                <CheckCircle2 className="h-4 w-4" />
                批准选中稿
              </Button>
            </div>
          </div>
          {reviewMode === 'changes' && (
            <div className="mt-5 border-t border-slate-100 pt-5">
              <TextAreaField label="定向修改要求" example="保留科技美学角度，但开头更直接；不要增加任何新的健康功能描述。" value={changeRequest} onChange={(event) => setChangeRequest(event.target.value)} />
              <div className="mt-3 flex justify-end">
                <Button disabled={!changeRequest.trim()} loading={reviewMutation.isPending} onClick={() => submitDecision('request_changes')}>
                  提交修改要求
                </Button>
              </div>
            </div>
          )}
          {reviewMode === 'edit' && (
            <div className="mt-5 border-t border-slate-100 pt-5">
              <Callout title="人工编辑也会重新检查">系统会创建新的 Content Version，并重新执行 Compliance 和 Scoring，不会覆盖原稿。</Callout>
              <div className="mt-4">
                <TextAreaField label="编辑正文" example="保留事实边界，用更自然的品牌口吻调整正文。" value={editedBody} onChange={(event) => setEditedBody(event.target.value)} />
              </div>
              <div className="mt-3 flex justify-end">
                <Button disabled={!editedBody.trim()} loading={reviewMutation.isPending} onClick={() => submitDecision('approved_with_edit')}>
                  保存新版本并重新检查
                </Button>
              </div>
            </div>
          )}
          {reviewError && (
            <div className="mt-4 flex gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4" />
              {reviewError}
            </div>
          )}
        </Card>
      )}
      {run.status === 'waiting_human' && !canReview && (
        <div className="mt-6">
          <Callout title="等待 Reviewer 操作">你的角色是 {principal?.role}，可以查看候选，但只有 Reviewer 或 Admin 能提交最终决定。</Callout>
        </div>
      )}
      {run.status === 'ready_for_manual_publish' && (
        <div className="mt-6 space-y-3">
          <Callout title="内容已完成审核" tone="success">
            选中稿已经进入 ready_for_manual_publish。系统不会自动发布，请由运营人员手动发布并登记 Publication。
          </Callout>
          <div className="flex justify-end">
            <Link to="/publications" className="inline-flex min-h-11 items-center justify-center rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-brand-600/20 transition hover:-translate-y-0.5 hover:bg-brand-700">
              前往发布登记
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
