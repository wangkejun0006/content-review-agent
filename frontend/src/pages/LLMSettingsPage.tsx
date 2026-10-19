import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3,
  Bot,
  CheckCircle2,
  KeyRound,
  Pencil,
  Plus,
  TestTube2,
  WandSparkles,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, Field, LoadingBlock, Modal, StatusBadge } from '../components/ui'
import { api } from '../lib/api'
import type { LLMProviderConfig } from '../types'

const purposeLabels: Record<string, { name: string; hint: string }> = {
  product_registry_import: { name: '产品资料整理', hint: '重视长文档理解和事实抽取' },
  evidence_registry_import: { name: '证据资料整理', hint: '重视原文保真、分类和准确摘录' },
  platform_rule_import: { name: '平台规则整理', hint: '重视严谨抽取和低幻觉' },
  xhs_product_context: { name: 'Product Context Agent', hint: '重视引用一致性和结构化输出' },
  xhs_strategy: { name: 'Strategy Agent', hint: '重视策略推理和创意差异' },
  xhs_writer: { name: 'XHS Writer Agent', hint: '重视中文表达和品牌语气' },
  xhs_compliance_semantic: { name: 'Compliance Agent', hint: '建议使用推理与指令遵循更强的模型' },
  xhs_scoring: { name: 'Scoring Agent', hint: '重视稳定性和一致评分' },
  xhs_feedback: { name: 'Feedback Agent', hint: '重视数据分析与归因边界' },
  configuration_test: { name: '模型连接测试', hint: '手动测试服务连通性产生的少量调用' },
  product: { name: '历史产品整理调用', hint: '早期版本记录的兼容用途名称' },
  xhs_writer_rewrite: { name: '历史内容改写调用', hint: '早期版本记录的兼容用途名称' },
}

const numberFormatter = new Intl.NumberFormat('zh-CN')

export function UsageModal({ onClose }: { onClose: () => void }) {
  const [days, setDays] = useState(30)
  const usage = useQuery({
    queryKey: ['llm-usage', days],
    queryFn: () => api.getLLMUsage(days),
  })
  const totals = usage.data?.totals

  return (
    <Modal title="Token 用量" description="查看当前品牌工作区中模型调用返回的 Token 统计。" onClose={onClose} wide>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">统计范围按 LLM 调用发生时间计算</p>
          <div className="flex flex-wrap gap-2 rounded-2xl bg-slate-100 p-1">
            {[[7, '近 7 天'], [30, '近 30 天'], [90, '近 90 天'], [0, '全部记录']].map(([value, label]) => (
              <button key={value} className={`rounded-xl px-3 py-2 text-xs font-semibold transition ${days === value ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`} onClick={() => setDays(value as number)}>{label}</button>
            ))}
          </div>
        </div>

        {usage.isLoading ? <LoadingBlock label="正在汇总 Token 用量" /> : usage.error ? (
          <Callout title="无法读取用量" tone="warning">{usage.error instanceof Error ? usage.error.message : '请稍后重试'}</Callout>
        ) : totals ? <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Card className="p-5"><p className="text-xs font-bold text-slate-500">总 Token</p><p className="mt-2 text-2xl font-bold text-graphite">{numberFormatter.format(totals.total_tokens)}</p><p className="mt-1 text-xs text-slate-400">输入与输出之和</p></Card>
            <Card className="p-5"><p className="text-xs font-bold text-slate-500">输入 / 输出</p><p className="mt-2 text-lg font-bold text-graphite">{numberFormatter.format(totals.input_tokens)} <span className="text-slate-300">/</span> {numberFormatter.format(totals.output_tokens)}</p><p className="mt-1 text-xs text-slate-400">Prompt / Completion</p></Card>
            <Card className="p-5"><p className="text-xs font-bold text-slate-500">Agent 调用</p><p className="mt-2 text-2xl font-bold text-graphite">{numberFormatter.format(totals.calls)}</p><p className="mt-1 text-xs text-slate-400">成功 {totals.successful_calls} · 失败 {totals.failed_calls}</p></Card>
            <Card className="p-5"><p className="text-xs font-bold text-slate-500">平均等待</p><p className="mt-2 text-2xl font-bold text-graphite">{numberFormatter.format(totals.average_latency_ms)} ms</p><p className="mt-1 text-xs text-slate-400">未报告 Token：{totals.unreported_token_calls} 次</p></Card>
          </div>

          <Callout title="统计口径说明">仅汇总供应商响应中返回的 usage 字段；未返回 Token 的调用会单独计数，不进行猜测。Token 用量不等于人民币费用，费用仍以供应商账单和具体模型价格为准。</Callout>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="overflow-hidden">
              <div className="border-b border-slate-100 px-5 py-4"><h3 className="font-bold text-graphite">按模型服务</h3><p className="mt-1 text-xs text-slate-500">历史名称按调用发生时保存，不受之后改名影响。</p></div>
              <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-5 py-3">服务 / 模型</th><th className="px-5 py-3">调用</th><th className="px-5 py-3">输入</th><th className="px-5 py-3">输出</th><th className="px-5 py-3">合计</th></tr></thead><tbody className="divide-y divide-slate-100">{usage.data?.by_provider.map((row) => <tr key={`${row.provider}-${row.model}`}><td className="px-5 py-4"><p className="font-semibold">{row.provider}</p><p className="mt-1 text-xs text-slate-400">{row.model}</p></td><td className="px-5 py-4">{row.calls}</td><td className="px-5 py-4">{numberFormatter.format(row.input_tokens)}</td><td className="px-5 py-4">{numberFormatter.format(row.output_tokens)}</td><td className="px-5 py-4 font-semibold text-brand-700">{numberFormatter.format(row.total_tokens)}</td></tr>)}</tbody></table></div>
            </Card>
            <Card className="overflow-hidden">
              <div className="border-b border-slate-100 px-5 py-4"><h3 className="font-bold text-graphite">按 Agent 用途</h3><p className="mt-1 text-xs text-slate-500">帮助判断哪些环节消耗最多 Token。</p></div>
              <div className="divide-y divide-slate-100">{usage.data?.by_purpose.map((row) => <div key={row.purpose} className="flex items-center justify-between gap-4 px-5 py-4"><div className="min-w-0"><p className="truncate text-sm font-semibold">{purposeLabels[row.purpose]?.name || row.purpose}</p><p className="mt-1 text-xs text-slate-400">{row.calls} 次调用 · 平均 {numberFormatter.format(row.average_latency_ms)} ms</p></div><div className="text-right"><p className="font-bold text-brand-700">{numberFormatter.format(row.total_tokens)}</p><p className="mt-1 text-[11px] text-slate-400">Token</p></div></div>)}</div>
            </Card>
          </div>
        </> : null}
      </div>
    </Modal>
  )
}

function ProviderModal({
  provider,
  onClose,
}: {
  provider: LLMProviderConfig | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    name: provider?.name || '',
    baseUrl: provider?.base_url || 'https://api.openai.com/v1',
    apiKey: '',
    model: provider?.default_model || '',
    enabled: provider?.is_enabled ?? true,
  })
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        name: form.name,
        base_url: form.baseUrl,
        default_model: form.model,
      }
      if (form.apiKey) payload.api_key = form.apiKey
      if (provider) {
        payload.is_enabled = form.enabled
        return api.updateLLMProvider(provider.id, payload)
      }
      return api.createLLMProvider({ ...payload, provider_type: 'openai_compatible' })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['llm-providers'] })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '保存失败'),
  })

  return (
    <Modal
      title={provider ? '编辑 LLM 服务' : '添加 LLM 服务'}
      description="填写服务商提供的接口地址、模型 ID 和 API Key。"
      onClose={onClose}
    >
      <div className="space-y-5">
        <Callout title="凭据由系统自动保护">
          API Key 保存后不会重新展示。{provider ? '不需要更换 Key 时保持输入框为空。' : '建议使用设置了额度限制的服务商 Key。'}
        </Callout>
        <Field label="配置名称" example="主力中文模型" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <Field label="Base URL" example="https://api.openai.com/v1" type="url" value={form.baseUrl} onChange={(event) => setForm({ ...form, baseUrl: event.target.value })} />
        <Field label="默认模型" example="服务商文档给出的精确模型 ID" value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} />
        <Field
          label={provider ? '更换 API Key（可选）' : 'API Key'}
          example={provider ? '留空继续使用当前 Key' : '粘贴服务商提供的 Key'}
          type="password"
          autoComplete="new-password"
          value={form.apiKey}
          onChange={(event) => setForm({ ...form, apiKey: event.target.value })}
        />
        {provider && (
          <label className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm">
            <input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />
            <span>
              <span className="block font-semibold">启用此服务</span>
              <span className="mt-1 block text-xs text-slate-500">停用后，绑定到它的 Agent 不会继续调用该服务。</span>
            </span>
          </label>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end">
          <Button disabled={!form.name || !form.baseUrl || (!provider && !form.apiKey) || !form.model} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            <KeyRound className="h-4 w-4" />
            {provider ? '保存修改' : '保存服务'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function LLMSettingsPage() {
  const { principal } = useAuth()
  const canManage = principal?.role === 'admin'
  const queryClient = useQueryClient()
  const [showProvider, setShowProvider] = useState(false)
  const [showUsage, setShowUsage] = useState(false)
  const [editingProvider, setEditingProvider] = useState<LLMProviderConfig | null>(null)
  const [draftBindings, setDraftBindings] = useState<Record<string, { provider: string; model: string }>>({})
  const [message, setMessage] = useState('')
  const status = useQuery({ queryKey: ['llm-status'], queryFn: api.getLLMStatus })
  const providers = useQuery({ queryKey: ['llm-providers'], queryFn: api.listLLMProviders })
  const bindings = useQuery({ queryKey: ['llm-bindings'], queryFn: api.listLLMBindings })
  const existing = useMemo(
    () => new Map((bindings.data || []).map((item) => [item.purpose, item])),
    [bindings.data],
  )
  const test = useMutation({
    mutationFn: api.testLLMProvider,
    onMutate: () => setMessage('正在测试连接；这会产生一次少量模型调用费用……'),
    onSuccess: (result) => setMessage(`连接测试通过：${result.message}`),
    onError: (reason) => setMessage(reason instanceof Error ? reason.message : '连接测试失败'),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['llm-providers'] })
      queryClient.invalidateQueries({ queryKey: ['llm-usage'] })
    },
  })
  const saveBinding = useMutation({
    mutationFn: ({ purpose, provider, model }: { purpose: string; provider: string; model: string }) =>
      api.upsertLLMBinding(purpose, provider, model),
    onSuccess: async () => {
      setMessage('Agent 模型绑定已保存')
      await queryClient.invalidateQueries({ queryKey: ['llm-bindings'] })
    },
    onError: (reason) => setMessage(reason instanceof Error ? reason.message : '绑定保存失败'),
  })
  const bindAll = useMutation({
    mutationFn: (providerId: string) =>
      Promise.all(
        (status.data?.supported_purposes || []).map((purpose) =>
          api.upsertLLMBinding(purpose, providerId, ''),
        ),
      ),
    onSuccess: async () => {
      setDraftBindings({})
      setMessage(`${status.data?.supported_purposes.length || 0} 个 Agent 用途已全部绑定到该服务。`)
      await queryClient.invalidateQueries({ queryKey: ['llm-bindings'] })
    },
    onError: (reason) => setMessage(reason instanceof Error ? reason.message : '批量绑定失败'),
  })

  if (status.isLoading || providers.isLoading || bindings.isLoading)
    return <LoadingBlock label="正在读取模型配置" />

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="LLM Gateway"
        title="模型设置"
        description="添加模型服务，并按 Agent 的任务特点选择默认模型或单独覆盖模型。"
        actions={<>
          <Button variant="secondary" onClick={() => setShowUsage(true)}><BarChart3 className="h-4 w-4" />Token 用量</Button>
          {canManage ? (
            <Button
              disabled={!status.data?.credential_storage_ready}
              onClick={() => {
                setEditingProvider(null)
                setShowProvider(true)
              }}
            >
              <Plus className="h-4 w-4" />
              添加 LLM 服务
            </Button>
          ) : null}
        </>}
      />
      {(!status.data?.credential_storage_ready || status.data?.runtime_mode !== 'managed') && (
        <Callout title="本地模型网关尚未就绪" tone="warning">
          请在项目根目录运行 <span className="font-mono">uv run smart-growth-admin configure-managed-llm</span>，然后刷新页面。该命令不会调用付费模型。
        </Callout>
      )}
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <Card className="p-5"><p className="text-xs font-bold text-slate-500">模型服务</p><p className="mt-2 text-xl font-bold">{providers.data?.length || 0}</p><p className="mt-1 text-xs text-slate-400">可配置多个服务供不同 Agent 使用</p></Card>
        <Card className="p-5"><p className="text-xs font-bold text-slate-500">已绑定 Agent</p><p className="mt-2 text-xl font-bold">{bindings.data?.length || 0} / {status.data?.supported_purposes.length || 0}</p><p className="mt-1 text-xs text-slate-400">全部绑定后即可运行真实内容任务</p></Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[.75fr_1.25fr]">
        <div>
          <h2 className="mb-3 font-bold">LLM 服务</h2>
          <div className="space-y-3">
            {(providers.data || []).map((provider) => (
              <Card key={provider.id} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0"><div className="flex items-center gap-2"><Bot className="h-4 w-4 text-brand-600" /><p className="font-semibold">{provider.name}</p></div><p className="mt-2 text-xs text-slate-500">{provider.default_model}</p><p className="mt-1 truncate text-xs text-slate-400">{provider.base_url}</p></div>
                  {provider.is_enabled ? provider.last_test_status && <StatusBadge status={provider.last_test_status === 'passed' ? 'active' : 'failed'} /> : <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">已停用</span>}
                </div>
                {provider.last_test_message && <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">最近测试：{provider.last_test_message}</p>}
                {canManage && (
                  <div className="mt-4 flex flex-wrap justify-end gap-2">
                    <Button variant="ghost" onClick={() => { setEditingProvider(provider); setShowProvider(true) }}><Pencil className="h-4 w-4" />编辑</Button>
                    <Button variant="secondary" disabled={!provider.is_enabled} loading={bindAll.isPending} onClick={() => bindAll.mutate(provider.id)}><WandSparkles className="h-4 w-4" />绑定全部 Agent</Button>
                    <Button variant="secondary" disabled={!provider.is_enabled} loading={test.isPending} title="会产生一次少量模型调用费用" onClick={() => test.mutate(provider.id)}><TestTube2 className="h-4 w-4" />测试连接</Button>
                  </div>
                )}
              </Card>
            ))}
            {!(providers.data || []).length && <Card className="p-6 text-center text-sm text-slate-500">尚未添加模型服务</Card>}
          </div>
        </div>

        <div>
          <h2 className="mb-3 font-bold">Agent 模型绑定</h2>
          <Card className="divide-y divide-slate-100 overflow-hidden">
            {(status.data?.supported_purposes || []).map((purpose) => {
              const saved = existing.get(purpose)
              const draft = draftBindings[purpose] || {
                provider: saved?.provider_config_id || providers.data?.[0]?.id || '',
                model: saved?.model_override || '',
              }
              return (
                <div key={purpose} className="grid gap-3 p-4 lg:grid-cols-[1fr_.9fr_.8fr_auto] lg:items-center">
                  <div><p className="text-sm font-semibold">{purposeLabels[purpose]?.name || purpose}</p><p className="mt-1 text-xs text-slate-500">{purposeLabels[purpose]?.hint}</p></div>
                  <select aria-label={`${purpose} 模型服务`} className="field-control" value={draft.provider} onChange={(event) => setDraftBindings({ ...draftBindings, [purpose]: { ...draft, provider: event.target.value } })}>
                    <option value="">选择服务</option>
                    {(providers.data || []).filter((provider) => provider.is_enabled).map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
                  </select>
                  <input aria-label={`${purpose} 模型覆盖`} className="field-control" placeholder="留空使用默认模型" value={draft.model} onChange={(event) => setDraftBindings({ ...draftBindings, [purpose]: { ...draft, model: event.target.value } })} />
                  {canManage && <Button variant="secondary" disabled={!draft.provider} loading={saveBinding.isPending} onClick={() => saveBinding.mutate({ purpose, ...draft })}>{saved ? <CheckCircle2 className="h-4 w-4" /> : null}保存</Button>}
                </div>
              )
            })}
          </Card>
        </div>
      </div>

      {message && <div className="fixed bottom-5 right-5 z-[70] flex max-w-md items-start gap-3 rounded-2xl border border-blue-100 bg-white px-4 py-3 text-sm text-blue-900 shadow-2xl" role="status" aria-live="polite"><span className="flex-1 leading-6">{message}</span><button className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" aria-label="关闭模型提示" onClick={() => setMessage('')}><X className="h-4 w-4" /></button></div>}
      {showUsage && <UsageModal onClose={() => setShowUsage(false)} />}
      {showProvider && <ProviderModal provider={editingProvider} onClose={() => setShowProvider(false)} />}
    </div>
  )
}
