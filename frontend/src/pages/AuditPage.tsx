import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Download, Filter, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock } from '../components/ui'
import { api } from '../lib/api'
import type { AuditEvent } from '../types'

const PAGE_SIZE = 50

const actionLabels: Record<string, string> = {
  'brief.created': '创建 Brief',
  'growth_run.created': '启动内容运行',
  'registry.revision_activated': '激活知识版本',
  'evidence.verified': '核验证据',
  'growth_run.review_submitted': '提交人工审核',
  'job.manually_retried': '重新执行失败任务',
  'llm.provider_created': '添加模型服务',
  'llm.provider_updated': '更新模型服务',
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export function AuditEventRows({ events }: { events: AuditEvent[] }) {
  return <div>{events.map((event) => (
    <div key={event.id} className="grid gap-3 border-t border-slate-100 px-5 py-4 first:border-t-0 lg:grid-cols-[1.1fr_1fr_1.2fr]">
      <div><p className="text-sm font-semibold text-graphite">{actionLabels[event.action] || event.action}</p><p className="mt-1 font-mono text-[11px] text-slate-400">{event.action}</p></div>
      <div><p className="text-sm text-slate-700">{event.actor_display_name || '系统任务'}</p><p className="mt-1 text-xs text-slate-500">{event.actor_email || '无账号'}</p></div>
      <div><p className="text-xs text-slate-500">{new Date(event.created_at).toLocaleString('zh-CN')} · {event.resource_type}</p><p className="mt-1 truncate font-mono text-[11px] text-slate-400">{event.resource_id || '—'}</p><details className="mt-2 text-xs text-slate-600"><summary className="cursor-pointer font-semibold text-brand-700">查看详情</summary><pre className="scroll-soft mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-3 font-mono text-[11px]">{JSON.stringify(event.details, null, 2)}</pre></details></div>
    </div>
  ))}</div>
}

export function AuditPage() {
  const [filters, setFilters] = useState({ actorId: '', action: '', resourceType: '', createdFrom: '', createdTo: '' })
  const [applied, setApplied] = useState(filters)
  const [offset, setOffset] = useState(0)
  const users = useQuery({ queryKey: ['users'], queryFn: api.listUsers })
  const params = {
    ...applied,
    createdFrom: applied.createdFrom ? new Date(applied.createdFrom).toISOString() : '',
    createdTo: applied.createdTo ? new Date(applied.createdTo).toISOString() : '',
  }
  const events = useQuery({
    queryKey: ['audit-events', params, offset],
    queryFn: () => api.listAuditEvents({ ...params, limit: PAGE_SIZE, offset }),
  })
  const [exporting, setExporting] = useState(false)

  const exportCsv = async () => {
    setExporting(true)
    try {
      const result = await api.listAuditEvents({ ...params, limit: 500, offset: 0 })
      const lines = [
        ['时间', '操作人', '邮箱', '动作', '资源类型', '资源 ID', '详情'].map(csvCell).join(','),
        ...result.items.map((event) => [event.created_at, event.actor_display_name, event.actor_email, event.action, event.resource_type, event.resource_id, JSON.stringify(event.details)].map(csvCell).join(',')),
      ]
      const blob = new Blob([`\ufeff${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `audit-events-${new Date().toISOString().slice(0, 10)}.csv`
      link.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  if (events.isLoading || users.isLoading) return <LoadingBlock label="正在读取审计记录" />
  return <div className="animate-fade-up">
    <PageHeader eyebrow="Governance" title="审计记录" description="追溯当前品牌工作区内的关键业务操作。记录由后端写入，前端只能查询和导出。" actions={<Button variant="secondary" onClick={exportCsv} loading={exporting}><Download className="h-4 w-4" />导出当前筛选</Button>} />
    <Card className="p-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <label className="block space-y-2"><span className="text-sm font-semibold">操作人</span><select className="field-control" value={filters.actorId} onChange={(event) => setFilters({ ...filters, actorId: event.target.value })}><option value="">全部账号</option>{users.data?.map((user) => <option key={user.id} value={user.id}>{user.display_name} · {user.email}</option>)}</select></label>
        <Field label="动作关键词" example="brief 或 evidence" value={filters.action} onChange={(event) => setFilters({ ...filters, action: event.target.value })} />
        <Field label="资源类型" example="campaign_brief" value={filters.resourceType} onChange={(event) => setFilters({ ...filters, resourceType: event.target.value })} />
        <Field label="开始时间" type="datetime-local" value={filters.createdFrom} onChange={(event) => setFilters({ ...filters, createdFrom: event.target.value })} />
        <Field label="结束时间" type="datetime-local" value={filters.createdTo} onChange={(event) => setFilters({ ...filters, createdTo: event.target.value })} />
      </div>
      <div className="mt-4 flex justify-end"><Button onClick={() => { setApplied(filters); setOffset(0) }}><Filter className="h-4 w-4" />应用筛选</Button></div>
    </Card>
    {events.error && <div className="mt-5"><Callout title="审计记录读取失败" tone="warning">{events.error instanceof Error ? events.error.message : '请刷新重试'}</Callout></div>}
    <Card className="mt-6 overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div><h2 className="font-bold text-graphite">操作流水</h2><p className="mt-1 text-xs text-slate-500">共 {events.data?.total || 0} 条，当前显示第 {offset + 1}–{Math.min(offset + PAGE_SIZE, events.data?.total || 0)} 条</p></div><Button variant="ghost" loading={events.isFetching} onClick={() => events.refetch()}><RefreshCw className="h-4 w-4" />刷新</Button></div>
      {events.data?.items.length ? <AuditEventRows events={events.data.items} /> : <EmptyState icon={<ClipboardList className="h-6 w-6" />} title="没有匹配记录" description="调整筛选条件后再试。" />}
      {!!events.data?.total && <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4"><Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>上一页</Button><Button variant="secondary" disabled={offset + PAGE_SIZE >= events.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>下一页</Button></div>}
    </Card>
  </div>
}
