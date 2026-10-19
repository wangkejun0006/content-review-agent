import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  BadgeCheck,
  Boxes,
  CircleUserRound,
  ClipboardCheck,
  FileText,
  PenTool,
  Send,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Card, LoadingBlock, StatusBadge } from '../components/ui'
import { api } from '../lib/api'
import { permissionRows, roleMeta } from '../lib/roles'

const workflow = [
  { label: '准备产品知识', description: '确认产品事实、图片与宣传边界', to: '/products', icon: Boxes },
  { label: '创建内容 Brief', description: '说明目标、场景和希望用户记住的信息', to: '/briefs', icon: PenTool },
  { label: '生成并人工审核', description: '比较候选、合规报告和评分', to: '/runs', icon: ClipboardCheck },
  { label: '登记发布与数据', description: '关联实际发布版本并持续录入指标', to: '/publications', icon: Send },
]

export function DashboardPage() {
  const { principal } = useAuth()
  const products = useQuery({
    queryKey: ['registry', 'product'],
    queryFn: () => api.listRegistry('product'),
  })
  const rules = useQuery({
    queryKey: ['registry', 'platform_rule'],
    queryFn: () => api.listRegistry('platform_rule'),
  })
  const briefs = useQuery({ queryKey: ['briefs'], queryFn: () => api.listBriefs() })
  const runs = useQuery({
    queryKey: ['runs'],
    queryFn: () => api.listRuns(),
    refetchInterval: 5000,
  })
  const publications = useQuery({
    queryKey: ['publications'],
    queryFn: api.listPublications,
  })
  if ([products, rules, briefs, runs, publications].some((query) => query.isLoading))
    return <LoadingBlock label="正在汇总运营工作台" />

  const role = principal ? roleMeta[principal.role] : null
  const activeRuleCount = rules.data?.filter((item) => item.current_revision_id).length || 0
  const activeProducts = products.data?.filter((item) => item.current_revision_id).length || 0
  const waitingRuns = (runs.data || []).filter((run) => run.status === 'waiting_human')
  const failedRuns = (runs.data || []).filter((run) => run.status === 'failed')
  const readyRuns = (runs.data || []).filter((run) => run.status === 'ready_for_manual_publish')
  const latestRuns = (runs.data || []).slice(0, 3)

  const nextAction =
    activeProducts === 0
      ? { title: '先完成产品知识', text: '至少激活一个产品后才能创建内容任务。', to: '/products', button: '前往产品知识' }
      : activeRuleCount === 0
        ? { title: '补齐平台规则', text: '小红书规则需要生效后才能进入新的内容运行。', to: '/platform-rules', button: '检查平台规则' }
        : waitingRuns.length
          ? { title: `有 ${waitingRuns.length} 次运行等待审核`, text: '候选稿已经生成，请完成最终人工决策。', to: `/runs/${waitingRuns[0].id}`, button: '立即审核' }
          : (briefs.data || []).length === 0
            ? { title: '可以创建第一份真实 Brief', text: '当前产品与平台知识已经可以支持内容生成。', to: '/briefs', button: '创建内容任务' }
            : readyRuns.length > (publications.data || []).length
              ? { title: '登记已经发布的内容', text: '审核通过后，请把实际小红书笔记关联到确定的内容版本。', to: '/publications', button: '前往发布登记' }
              : { title: '启动下一次内容任务', text: '可复用现有 Brief，也可以编辑后启动新的 Run。', to: '/briefs', button: '查看内容任务' }

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Operations Overview"
        title="运营工作台"
        description="按照知识准备、内容生产、人工审核和发布复盘的顺序完成日常运营。"
      />

      <div className="grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
        <Card className="overflow-hidden bg-gradient-to-br from-brand-900 via-brand-800 to-brand-700 p-6 text-white">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.18em] text-blue-200">推荐下一步</p>
              <h2 className="mt-3 text-2xl font-bold">{nextAction.title}</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-blue-100">{nextAction.text}</p>
            </div>
            <Sparkles className="h-8 w-8 text-blue-200" />
          </div>
          <Link to={nextAction.to} className="mt-6 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-brand-900 transition hover:-translate-y-0.5">
            {nextAction.button} <ArrowRight className="h-4 w-4" />
          </Link>
        </Card>

        <Card className="border-2 border-brand-100 p-6">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-brand-50 p-3 text-brand-700">
              <CircleUserRound className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[.16em] text-brand-600">当前用户身份</p>
              <h2 className="mt-2 text-xl font-bold text-graphite">{role?.label}</h2>
              <p className="mt-1 text-sm text-slate-500">{principal?.email}</p>
              <p className="mt-3 rounded-xl bg-brand-50 px-3 py-2 text-xs leading-5 text-brand-800">{role?.short}</p>
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: '已激活产品', value: activeProducts, icon: Boxes, to: '/products' },
          { label: '内容 Brief', value: briefs.data?.length || 0, icon: PenTool, to: '/briefs' },
          { label: '等待审核', value: waitingRuns.length, icon: BadgeCheck, to: '/runs' },
          { label: '发布记录', value: publications.data?.length || 0, icon: Send, to: '/publications' },
        ].map(({ label, value, icon: Icon, to }) => (
          <Link key={label} to={to}>
            <Card className="h-full p-5 transition hover:-translate-y-1 hover:shadow-lift">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-500">{label}</p>
                  <p className="mt-2 text-3xl font-bold text-graphite">{value}</p>
                </div>
                <div className="rounded-2xl bg-brand-50 p-3 text-brand-600"><Icon className="h-5 w-5" /></div>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      {(failedRuns.length > 0 || waitingRuns.length > 0) && (
        <Card className="mt-6 p-5">
          <h2 className="font-bold text-graphite">待办事项</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {waitingRuns.map((run) => (
              <Link key={run.id} to={`/runs/${run.id}`} className="flex items-center justify-between rounded-2xl border border-amber-100 bg-amber-50 p-4">
                <div><p className="text-sm font-bold text-amber-900">等待人工审核</p><p className="mt-1 text-xs text-amber-700">Run {run.id.slice(0, 8)}</p></div><ArrowRight className="h-4 w-4 text-amber-700" />
              </Link>
            ))}
            {failedRuns.map((run) => (
              <Link key={run.id} to={`/runs/${run.id}`} className="flex items-center justify-between rounded-2xl border border-red-100 bg-red-50 p-4">
                <div><p className="text-sm font-bold text-red-900">运行失败，需要检查</p><p className="mt-1 text-xs text-red-700">Run {run.id.slice(0, 8)}</p></div><ArrowRight className="h-4 w-4 text-red-700" />
              </Link>
            ))}
          </div>
        </Card>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card className="p-6">
          <h2 className="font-bold text-graphite">标准运营流程</h2>
          <div className="mt-5 space-y-3">
            {workflow.map(({ label, description, to, icon: Icon }, index) => (
              <Link key={label} to={to} className="flex items-center gap-4 rounded-2xl border border-slate-100 p-4 transition hover:border-brand-100 hover:bg-brand-50/50">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-900 text-xs font-bold text-white">{index + 1}</span>
                <Icon className="h-5 w-5 text-brand-600" />
                <div className="flex-1"><p className="text-sm font-bold">{label}</p><p className="mt-1 text-xs text-slate-500">{description}</p></div>
                <ArrowRight className="h-4 w-4 text-slate-300" />
              </Link>
            ))}
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
            <div><h2 className="font-bold text-graphite">最近运行</h2><p className="mt-1 text-xs text-slate-500">只显示当前列表中的最近记录</p></div>
            <Link to="/runs" className="text-sm font-semibold text-brand-600">查看全部</Link>
          </div>
          {latestRuns.length ? (
            <div className="divide-y divide-slate-100">
              {latestRuns.map((run) => (
                <Link key={run.id} to={`/runs/${run.id}`} className="flex items-center justify-between gap-4 px-6 py-4 transition hover:bg-brand-50/50">
                  <div className="min-w-0"><div className="flex items-center gap-2"><FileText className="h-4 w-4 text-brand-600" /><p className="truncate text-sm font-semibold">Run {run.id.slice(0, 8)}</p></div><p className="mt-1 text-xs text-slate-400">{new Date(run.created_at).toLocaleString('zh-CN')}</p></div>
                  <StatusBadge status={run.status} />
                </Link>
              ))}
            </div>
          ) : (
            <div className="px-6 py-14 text-center">
              <ShieldAlert className="mx-auto h-7 w-7 text-brand-300" />
              <p className="mt-3 text-sm font-semibold">还没有真实内容运行</p>
              <p className="mt-1 text-xs text-slate-500">测试记录已清理，可以从第一份真实 Brief 开始。</p>
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-6 overflow-hidden">
        <div className="border-b border-slate-100 px-6 py-5">
          <h2 className="font-bold text-graphite">用户角色与权限</h2>
          <p className="mt-1 text-xs text-slate-500">当前身份为“{role?.label}”。权限由角色决定，不以资产创建者决定。</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr><th className="px-6 py-3">功能</th><th className="px-6 py-3">系统管理员</th><th className="px-6 py-3">内容运营</th><th className="px-6 py-3">审核人员</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {permissionRows.map((row) => (
                <tr key={row.capability}>
                  <th className="px-6 py-4 font-semibold text-graphite">{row.capability}</th>
                  <td className={`px-6 py-4 ${principal?.role === 'admin' ? 'bg-blue-50 font-semibold text-blue-800' : 'text-slate-600'}`}>{row.admin}</td>
                  <td className={`px-6 py-4 ${principal?.role === 'editor' ? 'bg-violet-50 font-semibold text-violet-800' : 'text-slate-600'}`}>{row.editor}</td>
                  <td className={`px-6 py-4 ${principal?.role === 'reviewer' ? 'bg-emerald-50 font-semibold text-emerald-800' : 'text-slate-600'}`}>{row.reviewer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
