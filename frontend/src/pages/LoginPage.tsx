import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowRight, CheckCircle2, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/AuthContext'
import { Button, Field } from '../components/ui'
import { api, tokenStore } from '../lib/api'

const schema = z.object({
  brandId: z.string().uuid('请输入正确的 Brand ID'),
  email: z.string().email('请输入正确邮箱'),
  password: z.string().min(8, '密码至少 8 位'),
})
type FormData = z.infer<typeof schema>

export function LoginPage() {
  const { principal, signIn } = useAuth()
  const [serverError, setServerError] = useState(() => tokenStore.getNotice() || '')
  const [brandName, setBrandName] = useState('')
  const [demo, setDemo] = useState<{enabled:boolean;mode:string;model:string|null}|null>(null)
  useEffect(() => {fetch('/v1/auth/demo-context').then(r=>r.ok?r.json():null).then(setDemo).catch(()=>{})},[])
  const demoLogin = async (role:string) => {
    try {
      const response=await fetch('/v1/auth/demo-session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role})})
      if(!response.ok) throw new Error('本地演示入口不可用')
      const data=await response.json(); signIn(data.access_token)
    } catch(error) {setServerError(error instanceof Error?error.message:'演示登录失败')}
  }
  const [requiresBrandId, setRequiresBrandId] = useState(false)
  const { register, handleSubmit, setValue, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { brandId: localStorage.getItem('smart-growth-brand') || '' },
  })
  useEffect(() => {
    tokenStore.clearNotice()
    api.loginContext().then((context) => {
      if (context.brand_id) {
        setValue('brandId', context.brand_id)
        setBrandName(context.brand_name || '当前品牌')
        setRequiresBrandId(false)
      } else {
        setRequiresBrandId(true)
      }
    }).catch(() => setRequiresBrandId(true))
  }, [setValue])
  if (principal) return <Navigate to="/" replace />

  const submit = async (data: FormData) => {
    setServerError('')
    try {
      const token = await api.login(data.email, data.password, data.brandId)
      localStorage.setItem('smart-growth-brand', data.brandId)
      signIn(token.access_token)
    } catch (error) {
      setServerError(error instanceof Error ? error.message : '登录失败，请检查服务状态')
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#eef4ff]">
      <div className="absolute inset-0 subtle-grid opacity-60" />
      <div className="absolute -left-40 -top-40 h-[520px] w-[520px] rounded-full bg-brand-500/20 blur-3xl" />
      <div className="absolute -bottom-48 right-0 h-[520px] w-[520px] rounded-full bg-cyan-300/20 blur-3xl" />
      <div className="relative mx-auto grid min-h-screen max-w-7xl items-center gap-10 px-5 py-10 lg:grid-cols-[1.08fr_.92fr] lg:px-10">
        <section className="hidden animate-fade-up lg:block">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-white/80 px-4 py-2 text-sm font-semibold text-brand-700 shadow-sm">
            <Sparkles className="h-4 w-4" /> AI Growth Operations
          </div>
          <h1 className="mt-7 max-w-2xl text-5xl font-bold leading-[1.12] tracking-tight text-brand-900">
            让产品事实、内容策略与增长反馈，在同一个工作台里闭环。
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600">
            面向智能文具运营团队的 Registry-first AI 工作流。每一条内容都可追溯、可审核、可复现。
          </p>
          <div className="mt-9 grid max-w-xl grid-cols-2 gap-4">
            {['AI 整理产品资料', '三稿并行生成', '合规与评分联审', '发布数据反馈'].map((item) => (
              <div key={item} className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <CheckCircle2 className="h-4 w-4 text-brand-600" />{item}
              </div>
            ))}
          </div>
        </section>
        <section className="glass-panel mx-auto w-full max-w-lg rounded-[28px] p-6 animate-fade-up sm:p-9">
          <div className="flex items-center gap-3 lg:hidden">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-600 text-white"><Sparkles className="h-5 w-5" /></div>
            <div><p className="font-bold text-brand-900">Paper Orbit Growth</p><p className="text-xs text-slate-500">AI 运营工作台</p></div>
          </div>
          <div className="mt-6 lg:mt-0">
            <p className="text-sm font-semibold text-brand-600">欢迎回来</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-graphite">登录运营空间</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">使用管理员初始化时生成的 Brand ID 和账号登录。</p>
          </div>
          {demo?.enabled && <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4"><p className="text-sm font-bold text-amber-900">虚构文具品牌 · 本地角色演示</p><p className="mt-2 text-xs text-amber-800">{demo.mode==='fake'?'确定性离线模式':'真实模型：'+demo.model+'（调用受限）'}。所有业务资料均为虚构，演示令牌不代表生产身份。</p><div className="mt-3 flex flex-wrap gap-2">{[['admin','管理员'],['editor','编辑'],['reviewer','审核员']].map(([role,label])=><button key={role} type="button" className="rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs" onClick={()=>demoLogin(role)}>以{label}进入演示</button>)}</div></div>}
          <form className="mt-8 space-y-5" onSubmit={handleSubmit(submit)}>
            {brandName && !requiresBrandId ? <div className="rounded-2xl border border-brand-100 bg-brand-50 px-4 py-3"><p className="text-xs font-semibold text-brand-600">当前运营空间</p><p className="mt-1 text-sm font-bold text-brand-900">{brandName}</p></div> : <Field label="Brand ID" example="仅多品牌或自动识别失败时填写" placeholder="粘贴品牌 UUID" error={errors.brandId?.message} {...register('brandId')} />}
            <Field label="登录邮箱" example="admin@example.com" type="email" placeholder="你的工作邮箱" error={errors.email?.message} {...register('email')} />
            <Field label="密码" example="初始化时设置的密码" type="password" placeholder="输入密码" error={errors.password?.message} {...register('password')} />
            {serverError && <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{serverError}</div>}
            <Button className="w-full" type="submit" loading={isSubmitting}>进入工作台 <ArrowRight className="h-4 w-4" /></Button>
          </form>
          <p className="mt-6 text-center text-xs leading-5 text-slate-400">密码不会保存在浏览器；访问 Token 仅用于当前运营会话。</p>
        </section>
      </div>
    </div>
  )
}
