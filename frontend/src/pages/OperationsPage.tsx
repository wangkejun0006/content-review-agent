import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Clock3, Database, RefreshCw, RotateCcw, Server, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, LoadingBlock, StatusBadge } from '../components/ui'
import { api } from '../lib/api'
import type { OperationsStatus } from '../types'

const queueLabels: Array<[keyof OperationsStatus['queue'], string]> = [
  ['queued', '排队中'],
  ['running', '执行中'],
  ['waiting_human', '等待人工'],
  ['succeeded', '已完成'],
  ['failed', '失败'],
]

function errorText(error: Record<string, unknown> | null) {
  if (!error) return '未记录错误详情'
  const message = error.message
  return typeof message === 'string' ? message : JSON.stringify(error)
}

export function OperationsOverview({ data }: { data: OperationsStatus }) {
  return (
    <>
      {!data.worker.online && (
        <Callout title="后台 Worker 当前离线" tone="warning">
          新任务会继续留在队列中，但不会开始生成。请在项目根目录运行
          <code className="mx-1 rounded bg-red-100 px-1">uv run smart-growth-admin runtime-restart</code>
          后再刷新本页。
        </Callout>
      )}
      <div className="mt-5 grid gap-4 lg:grid-cols-[1.2fr_2fr]">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-semibold text-slate-600">
              <Server className="h-5 w-5 text-brand-600" />后台 Worker
            </span>
            <span className={`rounded-full px-3 py-1 text-xs font-bold ${data.worker.online ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
              {data.worker.online ? '在线' : '离线'}
            </span>
          </div>
          <p className="mt-4 text-sm font-semibold text-graphite">{data.worker.worker_id || '尚无心跳记录'}</p>
          <dl className="mt-4 space-y-2 text-xs text-slate-500">
            <div className="flex justify-between gap-4"><dt>主机 / PID</dt><dd>{data.worker.hostname || '—'} / {data.worker.process_id || '—'}</dd></div>
            <div className="flex justify-between gap-4"><dt>最后心跳</dt><dd>{data.worker.last_seen_at ? new Date(data.worker.last_seen_at).toLocaleString('zh-CN') : '—'}</dd></div>
            <div className="flex justify-between gap-4"><dt>当前任务</dt><dd className="truncate font-mono">{data.worker.current_job_id?.slice(0, 8) || '空闲'}</dd></div>
          </dl>
        </Card>
        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-600"><Database className="h-5 w-5 text-brand-600" />任务队列累计状态</div>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {queueLabels.map(([key, label]) => (
              <div key={key} className="rounded-2xl bg-slate-50 p-4 text-center">
                <p className={`text-2xl font-bold ${key === 'failed' && data.queue[key] ? 'text-red-700' : 'text-graphite'}`}>{data.queue[key]}</p>
                <p className="mt-1 text-xs text-slate-500">{label}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  )
}

export function OperationsPage() {
  const { principal } = useAuth()
  const canRetry = principal?.role === 'admin' || principal?.role === 'editor'
  const [actionError, setActionError] = useState('')
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['operations-status'],
    queryFn: api.getOperationsStatus,
    refetchInterval: 5000,
  })
  const retryMutation = useMutation({
    mutationFn: api.retryFailedJob,
    onSuccess: () => {
      setActionError('')
      queryClient.invalidateQueries({ queryKey: ['operations-status'] })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      queryClient.invalidateQueries({ queryKey: ['feedback-runs'] })
    },
    onError: (reason) => setActionError(reason instanceof Error ? reason.message : '任务重新执行失败'),
  })

  if (query.isLoading) return <LoadingBlock label="正在检查服务与任务队列" />
  if (!query.data) return <Callout title="无法读取运行状态" tone="warning">{query.error instanceof Error ? query.error.message : '请确认 API 服务可访问。'}</Callout>

  const data = query.data
  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Operations"
        title="系统运行"
        description="集中查看 Worker 心跳、任务积压与失败原因。任务重试是人工动作，不会形成无限循环。"
        actions={<Button variant="secondary" loading={query.isFetching} onClick={() => query.refetch()}><RefreshCw className="h-4 w-4" />刷新</Button>}
      />
      <OperationsOverview data={data} />
      {actionError && <div className="mt-5"><Callout title="操作未完成" tone="warning">{actionError}</Callout></div>}
      <Card className="mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div><h2 className="font-bold text-graphite">失败任务</h2><p className="mt-1 text-xs text-slate-500">最近 20 条；应先处理错误原因，再重新执行。</p></div>
          <TriangleAlert className="h-5 w-5 text-red-600" />
        </div>
        {data.failed_jobs.length === 0 ? (
          <EmptyState icon={<Activity className="h-6 w-6" />} title="没有失败任务" description="当前队列中没有需要人工处理的失败记录。" />
        ) : data.failed_jobs.map((job) => (
          <div key={job.id} className="grid gap-4 border-t border-slate-100 px-5 py-4 first:border-t-0 lg:grid-cols-[1fr_2fr_auto] lg:items-center">
            <div><StatusBadge status={job.status} /><p className="mt-2 text-sm font-semibold text-graphite">{job.job_type === 'growth_run' ? '内容生成任务' : '反馈分析任务'}</p><p className="mt-1 font-mono text-[11px] text-slate-400">{job.id.slice(0, 8)}</p></div>
            <div><p className="text-sm text-red-700">{errorText(job.last_error)}</p><p className="mt-2 flex items-center gap-2 text-xs text-slate-500"><Clock3 className="h-3.5 w-3.5" />{new Date(job.updated_at).toLocaleString('zh-CN')} · 自动尝试 {job.attempts}/{job.max_attempts} · 人工重试 {job.manual_retries}</p></div>
            <div className="flex gap-2">
              {job.related_resource_id && <Link className="inline-flex min-h-11 items-center rounded-xl px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50" to={job.job_type === 'growth_run' ? `/runs/${job.related_resource_id}` : '/feedback'}>查看详情</Link>}
              {canRetry && <Button loading={retryMutation.isPending && retryMutation.variables === job.id} onClick={() => retryMutation.mutate(job.id)}><RotateCcw className="h-4 w-4" />重新执行</Button>}
            </div>
          </div>
        ))}
      </Card>
    </div>
  )
}
