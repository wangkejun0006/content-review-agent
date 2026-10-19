import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, ExternalLink, Plus, Send } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal } from '../components/ui'
import { api } from '../lib/api'
import type { ContentCandidate, GrowthRun, Publication } from '../types'

interface PublishableOption { run: GrowthRun; candidate: ContentCandidate }

function PublicationMetricsSummary({ publicationId }: { publicationId: string }) {
  const query = useQuery({ queryKey: ['publication-metrics', publicationId], queryFn: () => api.listMetricSnapshots(publicationId) })
  const latest = query.data?.[query.data.length - 1]
  if (query.isLoading) return <p className="mt-4 text-xs text-slate-400">正在读取指标…</p>
  if (!latest) return <p className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">尚未录入指标快照</p>
  return <div className="mt-4 grid grid-cols-3 gap-2 rounded-2xl bg-slate-50 p-3 text-center"><div><p className="text-sm font-bold">{latest.views ?? '—'}</p><p className="text-[10px] text-slate-500">阅读</p></div><div><p className="text-sm font-bold">{latest.likes ?? '—'}</p><p className="text-[10px] text-slate-500">点赞</p></div><div><p className="text-sm font-bold">{latest.collections ?? '—'}</p><p className="text-[10px] text-slate-500">收藏</p></div><p className="col-span-3 mt-1 text-[10px] text-slate-400">截至 {new Date(latest.captured_at).toLocaleString('zh-CN')}</p></div>
}

function PublicationModal({ options, onClose }: { options: PublishableOption[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [contentVersionId, setContentVersionId] = useState(options[0]?.candidate.content_version_id || '')
  const [platformContentId, setPlatformContentId] = useState('')
  const [url, setUrl] = useState('')
  const [publishedAt, setPublishedAt] = useState(new Date().toISOString().slice(0, 16))
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () => api.createPublication({ content_version_id: contentVersionId, platform: 'xhs', platform_content_id: platformContentId, url, published_at: new Date(publishedAt).toISOString() }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['publications'] }); onClose() },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '登记失败'),
  })
  return <Modal title="登记小红书发布" description="系统不自动发布；请在发布后把平台记录关联到最终内容版本。" onClose={onClose}>
    <div className="space-y-5"><Callout title="为什么必须关联内容版本">后续指标和 Feedback 必须知道实际发布的是哪一版稿件，不能只记录一条链接。</Callout><label className="block space-y-2"><span className="text-sm font-semibold">已审核内容</span><select className="field-control" value={contentVersionId} onChange={(event) => setContentVersionId(event.target.value)}>{options.map(({ run, candidate }) => <option key={candidate.content_version_id} value={candidate.content_version_id}>{candidate.payload.recommended_title} · Run {run.id.slice(0, 8)}</option>)}</select></label><Field label="小红书笔记 ID" example="平台页面或导出数据中的笔记 ID" value={platformContentId} onChange={(event) => setPlatformContentId(event.target.value)} /><Field label="笔记 URL" example="https://www.xiaohongshu.com/explore/..." type="url" value={url} onChange={(event) => setUrl(event.target.value)} /><Field label="发布时间" example="实际公开发布时间" type="datetime-local" value={publishedAt} onChange={(event) => setPublishedAt(event.target.value)} />{error && <p className="text-sm text-red-600">{error}</p>}<div className="flex justify-end"><Button disabled={!contentVersionId || !platformContentId || !url} loading={mutation.isPending} onClick={() => mutation.mutate()}>确认登记</Button></div></div>
  </Modal>
}

function MetricsModal({ publication, onClose }: { publication: Publication; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [capturedAt, setCapturedAt] = useState(new Date().toISOString().slice(0, 16))
  const [metrics, setMetrics] = useState<Record<string, string>>({ views: '', likes: '', collections: '', comments: '', shares: '', follows: '' })
  const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: () => api.createMetricSnapshot(publication.id, { captured_at: new Date(capturedAt).toISOString(), ...Object.fromEntries(Object.entries(metrics).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])) }), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['publication-metrics', publication.id] }); onClose() }, onError: (reason) => setError(reason instanceof Error ? reason.message : '指标保存失败') })
  return <Modal title="录入累计指标" description="请输入截至采集时刻的平台累计值；普通快照不能低于上一条。" onClose={onClose}><div className="space-y-5"><Field label="采集时间" example="打开创作中心查看数据的时间" type="datetime-local" value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} /><div className="grid grid-cols-2 gap-4">{[['views', '阅读'], ['likes', '点赞'], ['collections', '收藏'], ['comments', '评论'], ['shares', '分享'], ['follows', '新增关注']].map(([key, label]) => <Field key={key} label={label} example="累计数量" type="number" min={0} value={metrics[key]} onChange={(event) => setMetrics({ ...metrics, [key]: event.target.value })} />)}</div>{error && <p className="text-sm text-red-600">{error}</p>}<div className="flex justify-end"><Button disabled={!Object.values(metrics).some(Boolean)} loading={mutation.isPending} onClick={() => mutation.mutate()}>保存指标快照</Button></div></div></Modal>
}

export function PublicationsPage() {
  const { principal } = useAuth()
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const [showCreate, setShowCreate] = useState(false)
  const [metricsFor, setMetricsFor] = useState<Publication | null>(null)
  const publications = useQuery({ queryKey: ['publications'], queryFn: api.listPublications })
  const runs = useQuery({ queryKey: ['runs'], queryFn: () => api.listRuns() })
  const readyRuns = useMemo(() => (runs.data || []).filter((run) => run.status === 'ready_for_manual_publish' && run.selected_candidate_id), [runs.data])
  const candidates = useQuery({ queryKey: ['publishable-candidates', readyRuns.map((run) => run.id).join(',')], queryFn: () => Promise.all(readyRuns.map(async (run) => ({ run, rows: await api.getCandidates(run.id) }))), enabled: !!runs.data })
  const publishedVersionIds = useMemo(() => new Set((publications.data || []).map((item) => item.content_version_id)), [publications.data])
  const options = useMemo(() => (candidates.data || []).flatMap(({ run, rows }) => rows.filter((candidate) => candidate.id === run.selected_candidate_id && !publishedVersionIds.has(candidate.content_version_id)).map((candidate) => ({ run, candidate }))), [candidates.data, publishedVersionIds])
  if (publications.isLoading || runs.isLoading || candidates.isLoading) return <LoadingBlock label="正在读取发布记录" />
  return <div className="animate-fade-up"><PageHeader eyebrow="Publication & Metrics" title="发布与数据" description="手动发布后登记实际内容版本，再持续录入小红书累计指标。" actions={canWrite ? <Button disabled={!options.length} onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" />登记 Publication</Button> : undefined} />
    {!options.length && <Callout title="当前没有待登记的已审核稿件">只有状态为“可手动发布”且已由人工选中的当前 Content Version 才能登记。已登记过的版本再次提交时后端会拒绝重复记录。</Callout>}
    {(publications.data || []).length ? <div className="grid gap-4 xl:grid-cols-2">{publications.data!.map((publication) => <Card key={publication.id} className="p-5"><div className="flex items-start justify-between gap-4"><div><div className="flex items-center gap-2 text-xs font-bold uppercase text-brand-600"><Send className="h-4 w-4" />小红书</div><p className="mt-3 font-semibold text-graphite">笔记 {publication.platform_content_id}</p><p className="mt-1 text-xs text-slate-500">发布于 {new Date(publication.published_at).toLocaleString('zh-CN')}</p></div><a href={publication.url} target="_blank" rel="noreferrer" className="rounded-xl bg-brand-50 p-2 text-brand-600"><ExternalLink className="h-4 w-4" /></a></div><PublicationMetricsSummary publicationId={publication.id} /><div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4"><span className="font-mono text-[11px] text-slate-400">Version {publication.content_version_id.slice(0, 8)}</span>{canWrite && <Button variant="secondary" onClick={() => setMetricsFor(publication)}><BarChart3 className="h-4 w-4" />录入指标</Button>}</div></Card>)}</div> : <Card><EmptyState icon={<Send className="h-6 w-6" />} title="尚未登记发布记录" description="先在运行详情完成 Reviewer 审核，再手动发布到小红书并回到这里登记。" /></Card>}
    {showCreate && <PublicationModal options={options} onClose={() => setShowCreate(false)} />}{metricsFor && <MetricsModal publication={metricsFor} onClose={() => setMetricsFor(null)} />}
  </div>
}
