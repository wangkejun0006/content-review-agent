import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, KeyRound, Plus, RefreshCw, ShieldCheck, UserRound, UsersRound } from 'lucide-react'
import { useMemo, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal } from '../components/ui'
import { api } from '../lib/api'
import { generateSecurePassword } from '../lib/password'
import { roleMeta } from '../lib/roles'
import type { ManagedUser, Role } from '../types'

const roles: Role[] = ['admin', 'editor', 'reviewer']

function UserCard({ user }: { user: ManagedUser }) {
  const role = roleMeta[user.role]
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-700">
            <UserRound className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate font-bold text-graphite">{user.display_name}</p>
            <p className="mt-1 truncate text-sm text-slate-500">{user.email}</p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${role.tone}`}>{role.label}</span>
      </div>
      <div className="mt-4 rounded-xl bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500">{role.short}</div>
    </Card>
  )
}

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState<Role>('editor')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [created, setCreated] = useState<ManagedUser | null>(null)
  const [copied, setCopied] = useState(false)

  const mutation = useMutation({
    mutationFn: () => api.createUser({ email, display_name: displayName, password, role }),
    onSuccess: async (user) => {
      setCreated(user)
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const passwordError = confirmation && password !== confirmation ? '两次输入的密码不一致' : ''
  const canSubmit = email && displayName && password.length >= 12 && confirmation && !passwordError
  const credentials = created ? `登录邮箱：${created.email}\n初始密码：${password}` : ''

  const fillGeneratedPassword = () => {
    const generated = generateSecurePassword()
    setPassword(generated)
    setConfirmation(generated)
  }

  const copyCredentials = async () => {
    await navigator.clipboard.writeText(credentials)
    setCopied(true)
  }

  if (created) {
    return (
      <Modal title="账号创建成功" description="登录信息只在当前窗口展示，请现在安全转交给同事。" onClose={onClose}>
        <div className="space-y-5">
          <Callout title="请妥善保存" tone="success">关闭窗口后，系统不会再次显示该密码。不要通过公开群聊转发。</Callout>
          <div className="rounded-2xl border border-brand-100 bg-white p-5">
            <dl className="space-y-4 text-sm">
              <div><dt className="text-xs font-semibold text-slate-400">姓名</dt><dd className="mt-1 font-semibold">{created.display_name}</dd></div>
              <div><dt className="text-xs font-semibold text-slate-400">登录邮箱</dt><dd className="mt-1 break-all font-mono">{created.email}</dd></div>
              <div><dt className="text-xs font-semibold text-slate-400">初始密码</dt><dd className="mt-1 break-all font-mono">{password}</dd></div>
              <div><dt className="text-xs font-semibold text-slate-400">角色</dt><dd className="mt-1">{roleMeta[created.role].label}</dd></div>
            </dl>
          </div>
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="secondary" onClick={copyCredentials}>{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied ? '已复制' : '复制登录信息'}</Button>
            <Button onClick={onClose}>完成</Button>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title="创建同事账号" description="账号会自动加入当前品牌工作区，不开放公共自助注册。" onClose={onClose}>
      <div className="space-y-5">
        <Field label="姓名" example="xiaotian" value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="off" />
        <Field label="工作邮箱" example="name@paper-orbit.com" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="off" />
        <label className="block space-y-2">
          <span className="flex items-baseline justify-between gap-3"><span className="text-sm font-semibold text-graphite">角色</span><span className="text-xs text-slate-400">决定账号可执行的操作</span></span>
          <select aria-label="角色" className="field-control" value={role} onChange={(event) => setRole(event.target.value as Role)}>
            {roles.map((value) => <option key={value} value={value}>{roleMeta[value].label} · {roleMeta[value].short}</option>)}
          </select>
        </label>
        <div className="rounded-2xl border border-slate-100 bg-white p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-sm font-semibold text-graphite">初始密码</p><p className="mt-1 text-xs text-slate-500">至少 12 位，并为每位同事使用不同密码。</p></div>
            <Button type="button" variant="secondary" onClick={fillGeneratedPassword}><RefreshCw className="h-4 w-4" />生成安全密码</Button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="密码" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" hint={password && password.length < 12 ? '还需要至少 12 个字符' : undefined} />
            <Field label="再次输入" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" error={passwordError} />
          </div>
        </div>
        {mutation.error && <Callout title="账号创建失败" tone="warning">{mutation.error instanceof Error ? mutation.error.message : '请稍后重试'}</Callout>}
        <div className="flex justify-end">
          <Button disabled={!canSubmit} loading={mutation.isPending} onClick={() => mutation.mutate()}><KeyRound className="h-4 w-4" />创建账号</Button>
        </div>
      </div>
    </Modal>
  )
}

export function UsersPage() {
  const [creating, setCreating] = useState(false)
  const users = useQuery({ queryKey: ['users'], queryFn: api.listUsers })
  const counts = useMemo(() => Object.fromEntries(roles.map((role) => [role, (users.data || []).filter((user) => user.role === role).length])) as Record<Role, number>, [users.data])

  if (users.isLoading) return <LoadingBlock label="正在读取用户账号" />

  return (
    <div className="animate-fade-up">
      <PageHeader eyebrow="Access Control" title="用户管理" description="为已获准使用当前品牌工作区的同事创建账号，并按职责分配权限。" actions={<Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />创建账号</Button>} />
      <Callout title="两层访问控制">同事需要先加入你的 Tailscale 网络并能打开服务地址，然后再使用这里创建的项目账号登录。Brand ID 在当前单品牌模式下由登录页自动识别。</Callout>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5"><UsersRound className="h-5 w-5 text-brand-600" /><p className="mt-3 text-2xl font-bold">{users.data?.length || 0}</p><p className="mt-1 text-xs text-slate-500">全部账号</p></Card>
        {roles.map((role) => <Card key={role} className="p-5"><ShieldCheck className="h-5 w-5 text-brand-600" /><p className="mt-3 text-2xl font-bold">{counts[role]}</p><p className="mt-1 text-xs text-slate-500">{roleMeta[role].label}</p></Card>)}
      </div>

      <div className="mt-6">
        <div className="mb-3"><h2 className="font-bold text-graphite">当前品牌账号</h2><p className="mt-1 text-xs text-slate-500">账号列表按工作邮箱排序；权限由角色统一决定。</p></div>
        {users.error ? <Callout title="无法读取账号" tone="warning">{users.error instanceof Error ? users.error.message : '请刷新重试'}</Callout> : users.data?.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{users.data.map((user) => <UserCard key={user.id} user={user} />)}</div> : <Card><EmptyState icon={<UsersRound className="h-6 w-6" />} title="还没有同事账号" description="创建第一个邀请制账号后，同事即可使用邮箱和密码登录。" /></Card>}
      </div>
      {creating && <CreateUserModal onClose={() => setCreating(false)} />}
    </div>
  )
}
