import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  RefreshCw,
  RotateCcw,
  TriangleAlert,
  UserRoundCheck,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, LoadingBlock, StatusBadge } from '../components/ui'
import { api } from '../lib/api'
import type { GrowthRun } from '../types'

type ViewMode = 'active' | 'archived'

const activeStatuses = new Set(['queued', 'running', 'waiting_human', 'waiting_knowledge_review'])

function RunRow({
  run,
  archived,
  canWrite,
  canDelete,
  onArchive,
  onRestore,
  onDelete,
  busy,
}: {
  run: GrowthRun
  archived: boolean
  canWrite: boolean
  canDelete: boolean
  onArchive: (run: GrowthRun) => void
  onRestore: (run: GrowthRun) => void
  onDelete: (run: GrowthRun) => void
  busy: boolean
}) {
  return (
    <div className="grid gap-3 border-t border-slate-100 px-5 py-4 md:grid-cols-[1fr_.8fr_.8fr_auto] md:items-center">
      <Link to={`/runs/${run.id}`} className="group min-w-0">
        <div className="flex items-center gap-2">
          <StatusBadge status={run.status} />
          {run.status === 'waiting_human' && (
            <span className="text-xs font-semibold text-amber-700">需要你审核</span>
          )}
        </div>
        <p className="mt-2 truncate font-mono text-[11px] text-slate-400">
          Run {run.id.slice(0, 8)}
        </p>
      </Link>
      <div className="text-xs text-slate-500">
        <p className="font-semibold text-slate-700">{run.registry_revision_ids.length} 个知识版本</p>
        <p className="mt-1">每次运行独立冻结</p>
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Clock3 className="h-4 w-4" />
        {new Date(run.created_at).toLocaleString('zh-CN')}
      </div>
      <div className="flex justify-end gap-2">
        {canWrite &&
          (archived ? (
            <>
              <Button variant="ghost" loading={busy} onClick={() => onRestore(run)}>
                <RotateCcw className="h-4 w-4" />
                恢复
              </Button>
              {canDelete && (
                <Button variant="danger" loading={busy} onClick={() => onDelete(run)}>
                  永久删除
                </Button>
              )}
            </>
          ) : (
            <Button
              variant="ghost"
              disabled={activeStatuses.has(run.status)}
              loading={busy}
              title={activeStatuses.has(run.status) ? '运行进行中，暂不能移入回收站' : '保留全部数据并移入回收站'}
              onClick={() => onArchive(run)}
            >
              <Archive className="h-4 w-4" />
              移入回收站
            </Button>
          ))}
        <Link to={`/runs/${run.id}`} className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50">
          查看 <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  )
}

export function RunsPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('active')
  const [expandedBriefs, setExpandedBriefs] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState('')
  const queryClient = useQueryClient()
  const { principal } = useAuth()
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const canDelete = principal?.role === 'admin'
  const runsQuery = useQuery({
    queryKey: ['runs', 'all'],
    queryFn: () => api.listRuns(true),
    refetchInterval: 5000,
  })
  const briefsQuery = useQuery({
    queryKey: ['briefs', 'all'],
    queryFn: () => api.listBriefs(true),
  })
  const archiveMutation = useMutation({
    mutationFn: api.archiveRun,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
    onError: (reason) => setActionError(reason instanceof Error ? reason.message : '运行归档失败'),
  })
  const restoreMutation = useMutation({
    mutationFn: api.restoreRun,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
    onError: (reason) => setActionError(reason instanceof Error ? reason.message : '运行恢复失败'),
  })
  const archiveOldMutation = useMutation({
    mutationFn: (runs: GrowthRun[]) => Promise.all(runs.map((run) => api.archiveRun(run.id))),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
    onError: (reason) => setActionError(reason instanceof Error ? reason.message : '旧运行批量移出失败'),
  })
  const deleteMutation = useMutation({
    mutationFn: api.permanentlyDeleteRun,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
    onError: (reason) => setActionError(reason instanceof Error ? reason.message : '运行永久删除失败'),
  })

  const briefNames = useMemo(
    () => new Map((briefsQuery.data || []).map((brief) => [brief.id, brief.name])),
    [briefsQuery.data],
  )
  const allRuns = runsQuery.data || []
  const activeRuns = allRuns.filter((run) => !run.archived_at)
  const archivedRuns = allRuns.filter((run) => !!run.archived_at)
  const visibleRuns = viewMode === 'active' ? activeRuns : archivedRuns
  const groups = useMemo(() => {
    const grouped = new Map<string, GrowthRun[]>()
    for (const run of visibleRuns) {
      const rows = grouped.get(run.brief_id) || []
      rows.push(run)
      grouped.set(run.brief_id, rows)
    }
    return [...grouped.entries()]
      .map(([briefId, rows]) => ({
        briefId,
        name: briefNames.get(briefId) || `内容任务 ${briefId.slice(0, 8)}`,
        runs: rows.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)),
      }))
      .sort((a, b) => Date.parse(b.runs[0].created_at) - Date.parse(a.runs[0].created_at))
  }, [visibleRuns, briefNames])
  const waitingCount = activeRuns.filter((run) => run.status === 'waiting_human').length
  const inProgressCount = activeRuns.filter((run) => ['queued', 'running'].includes(run.status)).length
  const failedCount = activeRuns.filter((run) => run.status === 'failed').length

  if (runsQuery.isLoading || briefsQuery.isLoading)
    return <LoadingBlock label="正在同步 LangGraph 运行状态" />

  const archive = (run: GrowthRun) => {
    if (!window.confirm('将这次运行移出默认列表？内容、评分、审核和知识快照都会保留，可在“已移出”中恢复。'))
      return
    setActionError('')
    archiveMutation.mutate(run.id)
  }

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Growth Runs"
        title="运行与审核"
        description="按内容 Brief 分组查看生成记录。一个 Brief 可以多次运行，每次都会冻结独立知识快照。"
        actions={
          <Button variant="secondary" onClick={() => runsQuery.refetch()} loading={runsQuery.isFetching}>
            <RefreshCw className="h-4 w-4" />
            刷新状态
          </Button>
        }
      />

      <Callout title="为什么同一任务会有多条运行记录？">
        每次点击“启动新 Run”都会生成一条独立记录，便于比较模型、Prompt 和知识版本。页面默认只展开最近一次，历史运行可以展开或移入回收站。
      </Callout>

      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <Card className="p-5">
          <div className="flex items-center gap-3 text-amber-700">
            <UserRoundCheck className="h-5 w-5" />
            <span className="text-sm font-semibold">等待人工审核</span>
          </div>
          <p className="mt-3 text-3xl font-bold">{waitingCount}</p>
        </Card>
        <Card className="p-5">
          <div className="flex items-center gap-3 text-brand-700">
            <RefreshCw className="h-5 w-5" />
            <span className="text-sm font-semibold">正在生成</span>
          </div>
          <p className="mt-3 text-3xl font-bold">{inProgressCount}</p>
        </Card>
        <Card className="p-5">
          <div className="flex items-center gap-3 text-red-700">
            <TriangleAlert className="h-5 w-5" />
            <span className="text-sm font-semibold">运行失败</span>
          </div>
          <p className="mt-3 text-3xl font-bold">{failedCount}</p>
        </Card>
      </div>

      <div className="mt-6 flex gap-2 rounded-2xl bg-slate-100 p-1">
        <button
          className={`rounded-xl px-4 py-2 text-sm font-semibold ${viewMode === 'active' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`}
          onClick={() => setViewMode('active')}
        >
          当前列表（{activeRuns.length}）
        </button>
        <button
          className={`rounded-xl px-4 py-2 text-sm font-semibold ${viewMode === 'archived' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`}
          onClick={() => setViewMode('archived')}
        >
          回收站（{archivedRuns.length}）
        </button>
      </div>

      {actionError && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{actionError}</p>}

      <div className="mt-5 space-y-5">
        {groups.map((group) => {
          const expanded = expandedBriefs.has(group.briefId)
          const shownRuns = expanded ? group.runs : group.runs.slice(0, 1)
          const archivableHistory = group.runs
            .slice(1)
            .filter((run) => !activeStatuses.has(run.status))
          return (
            <Card key={group.briefId} className="overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50/70 px-5 py-4">
                <div>
                  <p className="font-bold text-graphite">{group.name}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    共 {group.runs.length} 次运行 · 默认展示最近一次
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {viewMode === 'active' && canWrite && archivableHistory.length > 0 && (
                    <Button
                      variant="ghost"
                      loading={archiveOldMutation.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `保留最近一次运行，并将 ${archivableHistory.length} 条已结束的旧运行移出默认列表？所有数据仍可恢复。`,
                          )
                        ) {
                          setActionError('')
                          archiveOldMutation.mutate(archivableHistory)
                        }
                      }}
                    >
                      <Archive className="h-4 w-4" />
                      清理旧运行
                    </Button>
                  )}
                  {group.runs.length > 1 && (
                    <Button
                      variant="ghost"
                      onClick={() =>
                        setExpandedBriefs((current) => {
                          const next = new Set(current)
                          if (next.has(group.briefId)) next.delete(group.briefId)
                          else next.add(group.briefId)
                          return next
                        })
                      }
                    >
                      {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      {expanded ? '收起历史' : `查看另外 ${group.runs.length - 1} 次`}
                    </Button>
                  )}
                </div>
              </div>
              {shownRuns.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  archived={viewMode === 'archived'}
                  canWrite={!!canWrite}
                  canDelete={!!canDelete}
                  onArchive={archive}
                  onRestore={(item) => restoreMutation.mutate(item.id)}
                  onDelete={(item) => {
                    const confirmation = window.prompt(`永久删除不可恢复。请输入 Run 短 ID“${item.id.slice(0, 8)}”确认：`)
                    if (confirmation === item.id.slice(0, 8)) deleteMutation.mutate(item.id)
                  }}
                  busy={
                    (archiveMutation.isPending && archiveMutation.variables === run.id) ||
                    (restoreMutation.isPending && restoreMutation.variables === run.id) ||
                    (deleteMutation.isPending && deleteMutation.variables === run.id)
                  }
                />
              ))}
            </Card>
          )
        })}
      </div>

      {!groups.length && (
        <Card className="mt-5">
          <EmptyState
            icon={
              viewMode === 'active' ? (
                <BookOpenCheck className="h-6 w-6" />
              ) : (
                <CheckCircle2 className="h-6 w-6" />
              )
            }
            title={viewMode === 'active' ? '还没有运行任务' : '回收站为空'}
            description={
              viewMode === 'active'
                ? '在“内容任务”中创建 Brief 并启动 Run，这里会按 Brief 汇总实时进度和审核入口。'
                : '从当前列表移出的历史运行会显示在这里，并可随时恢复。'
            }
          />
        </Card>
      )}
    </div>
  )
}
