import clsx from 'clsx'
import { Activity, BookOpenCheck, Boxes, BadgeCheck, ChevronRight, ClipboardList, LayoutDashboard, LogOut, Menu, Megaphone, PenTool, Send, ShieldCheck, Settings, Sparkles, TrendingUp, UsersRound, X, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Button } from '../components/ui'
import { roleMeta } from '../lib/roles'
import type { Role } from '../types'

type NavigationItem = { to: string; label: string; icon: LucideIcon; end?: boolean; roles?: Role[] }

const navigation: Array<{ label: string; items: NavigationItem[] }> = [
  {
    label: '工作台',
    items: [{ to: '/', label: '运营概览', icon: LayoutDashboard, end: true }],
  },
  {
    label: '一、知识准备',
    items: [
      { to: '/products', label: '产品知识', icon: Boxes },
      { to: '/claims', label: '声明与证据', icon: BadgeCheck },
      { to: '/platform-rules', label: '平台规则', icon: ShieldCheck },
      { to: '/marketing-programs', label: '营销支持方案', icon: Megaphone },
    ],
  },
  {
    label: '二、内容生产',
    items: [
      { to: '/briefs', label: '内容任务', icon: PenTool },
      { to: '/runs', label: '运行与审核', icon: BookOpenCheck },
    ],
  },
  {
    label: '三、发布复盘',
    items: [
      { to: '/publications', label: '发布与数据', icon: Send },
      { to: '/feedback', label: '增长反馈', icon: TrendingUp },
    ],
  },
  {
    label: '系统',
    items: [
      { to: '/settings/users', label: '用户管理', icon: UsersRound, roles: ['admin'] },
      { to: '/settings/llm', label: '模型设置', icon: Settings },
      { to: '/settings/operations', label: '系统运行', icon: Activity },
      { to: '/settings/audit', label: '审计记录', icon: ClipboardList, roles: ['admin'] },
    ],
  },
]

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { principal, signOut } = useAuth()
  const currentRole = principal ? roleMeta[principal.role] : null

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-20 items-center gap-3 px-6">
        <div className="relative flex h-11 w-11 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-brand-500 to-brand-900 text-white shadow-lg shadow-brand-600/25">
          <Sparkles className="h-5 w-5" />
          <span className="absolute -right-2 -top-2 h-5 w-5 rounded-full bg-white/25" />
        </div>
        <div>
          <div className="font-bold tracking-tight text-white">Paper Orbit Growth</div>
          <div className="text-[11px] font-medium tracking-[.18em] text-blue-200">AI OPERATIONS</div>
        </div>
      </div>
      <nav className="scroll-soft mt-2 flex-1 space-y-5 overflow-y-auto px-4 pb-4">
        {navigation.map((section) => (
          <div key={section.label}>
            <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[.18em] text-blue-300/80">
              {section.label}
            </p>
            <div className="space-y-1.5">
              {section.items.filter((item) => !item.roles || (principal && item.roles.includes(principal.role))).map((item) => {
                const Icon = item.icon
                return (
                <NavLink key={item.to} to={item.to} end={item.end} onClick={() => setMobileOpen(false)} className={({ isActive }) => clsx('group flex items-center justify-between rounded-2xl px-4 py-2.5 text-sm font-medium transition duration-200', isActive ? 'bg-white text-brand-900 shadow-lg shadow-slate-950/10' : 'text-blue-100 hover:bg-white/10 hover:text-white')}>
                  {({ isActive }) => (
                    <>
                      <span className="flex items-center gap-3">
                        <Icon className={clsx('h-4 w-4', isActive ? 'text-brand-600' : '')} />
                        {item.label}
                      </span>
                      <ChevronRight className="h-4 w-4 opacity-0 transition group-hover:opacity-100" />
                    </>
                  )}
                </NavLink>
                )
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="mt-auto p-4">
        <div className="rounded-2xl border border-white/15 bg-white/10 p-4 text-blue-50">
          <p className="text-[10px] font-bold uppercase tracking-[.16em] text-blue-200">当前登录身份</p>
          <div className="mt-2 inline-flex rounded-full bg-white px-3 py-1 text-xs font-bold text-brand-900">
            {currentRole?.label}
          </div>
          <div className="flex items-center gap-3">
            <div className="mt-3 flex h-9 w-9 items-center justify-center rounded-full bg-blue-300/20 text-xs font-bold">{principal?.email.slice(0, 2).toUpperCase()}</div>
            <div className="min-w-0">
              <p className="mt-3 truncate text-sm font-medium">{principal?.email}</p>
              <p className="mt-0.5 text-xs text-blue-200">{currentRole?.short}</p>
            </div>
          </div>
          <button onClick={signOut} className="mt-4 flex w-full items-center gap-2 text-xs text-blue-200 transition hover:text-white">
            <LogOut className="h-4 w-4" />
            退出登录
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-pearl">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 bg-brand-900 lg:block">{sidebar}</aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button aria-label="关闭导航遮罩" className="absolute inset-0 bg-slate-950/35" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-brand-900 shadow-2xl animate-fade-up">
            <Button variant="ghost" className="absolute right-3 top-3 text-white hover:bg-white/10" onClick={() => setMobileOpen(false)}>
              <X className="h-5 w-5" />
            </Button>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center border-b border-slate-200/70 bg-pearl/85 px-4 backdrop-blur-xl lg:hidden">
          <Button variant="ghost" className="h-10 w-10 p-0" onClick={() => setMobileOpen(true)} aria-label="打开导航">
            <Menu className="h-5 w-5" />
          </Button>
          <span className="ml-3 font-bold text-brand-900">Paper Orbit Growth</span>
          {currentRole && <span className={`ml-auto rounded-full px-3 py-1 text-xs font-bold ${currentRole.tone}`}>{currentRole.label}</span>}
        </header>
        <main className="mx-auto min-h-screen max-w-[1500px] p-4 sm:p-6 lg:p-8">
          <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-900">本地脱敏演示 · 品牌、产品、证据和指标均为虚构。内容由 AI 辅助生成，须经人工审核；本系统不自动发布。</div>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
