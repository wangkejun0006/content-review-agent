import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Megaphone, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal, StatusBadge, TextAreaField } from '../components/ui'
import { api } from '../lib/api'
import type { RegistryItemDetail } from '../types'

const programTypes = [
  ['creator_custom', '蒲公英定制合作'],
  ['creator_batch', '蒲公英批量合作'],
  ['product_trial', '蒲公英众测'],
  ['live_buyer', '蒲公英直播 / 买手合作'],
  ['content_boost', '笔记加热'],
  ['official_consulting', '官方营销顾问 / 全案咨询'],
] as const

const objectiveOptions = [
  ['awareness', '品牌/产品认知'],
  ['content_validation', '内容验证'],
  ['creator_seeding', '达人种草'],
  ['amplification', '放大传播'],
  ['conversion', '购买转化'],
] as const

function lines(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function ProgramModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    stableKey: '',
    name: '',
    programType: 'creator_custom',
    objectives: ['awareness'],
    description: '',
    eligibility: '',
    assets: '',
    steps: '',
    budget: '',
    measurement: '',
    sourceUrl: 'https://pgy.xiaohongshu.com/',
    verifiedAt: new Date().toISOString().slice(0, 16),
  })
  const mutation = useMutation({
    mutationFn: () =>
      api.createRegistryItem('platform_marketing_program', {
        stable_key: form.stableKey,
        payload: {
          platform: 'xhs',
          name: form.name,
          program_type: form.programType,
          objectives: form.objectives,
          description: form.description,
          eligibility_requirements: lines(form.eligibility),
          required_assets: lines(form.assets),
          application_steps: lines(form.steps),
          budget_guidance: form.budget || '需由运营人员向平台确认',
          measurement_signals: lines(form.measurement),
          source_url: form.sourceUrl,
          verified_at: new Date(form.verifiedAt).toISOString(),
        },
        search_text: `${form.name} ${form.description} ${form.objectives.join(' ')}`,
        source_uri: form.sourceUrl,
        verification_status: 'provisional',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['registry', 'platform_marketing_program'],
      })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '方案保存失败'),
  })
  const toggleObjective = (value: string) =>
    setForm({
      ...form,
      objectives: form.objectives.includes(value) ? form.objectives.filter((item) => item !== value) : [...form.objectives, value],
    })
  return (
    <Modal title="录入小红书营销支持方案" description="把官方方案整理成 Strategy 可引用的受治理资料；保存后仍需 Reviewer 激活。" onClose={onClose} wide>
      <div className="space-y-5">
        <Callout title="只记录官方可核验信息">预算门槛、准入条件和申请步骤可能变化。请打开官方页面核对并填写核验时间；不确定的预算请写“向平台确认”。</Callout>
        <div className="grid gap-5 md:grid-cols-2">
          <Field
            label="方案 Key"
            example="xhs-pgy-product-trial"
            value={form.stableKey}
            onChange={(event) =>
              setForm({
                ...form,
                stableKey: event.target.value.toLowerCase().replace(/\s+/g, '-'),
              })
            }
          />
          <Field label="方案名称" example="蒲公英产品众测" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          <label className="space-y-2">
            <span className="text-sm font-semibold">方案类型</span>
            <select className="field-control" value={form.programType} onChange={(event) => setForm({ ...form, programType: event.target.value })}>
              {programTypes.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <Field label="官方来源 URL" example="https://pgy.xiaohongshu.com/help/..." type="url" value={form.sourceUrl} onChange={(event) => setForm({ ...form, sourceUrl: event.target.value })} />
        </div>
        <div>
          <p className="text-sm font-semibold">适用营销目标</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {objectiveOptions.map(([value, label]) => (
              <button key={value} type="button" className={`rounded-full px-3 py-2 text-xs font-semibold ${form.objectives.includes(value) ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'}`} onClick={() => toggleObjective(value)}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <TextAreaField label="方案说明" example="适合新品体验内容验证，由符合条件的创作者参与并产出真实、合规的体验内容。" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
        <div className="grid gap-5 md:grid-cols-2">
          <TextAreaField label="准入与前置条件" example={'品牌/产品类目满足平台准入\n准备真实产品与可用 Claim'} hint="每行一项" value={form.eligibility} onChange={(event) => setForm({ ...form, eligibility: event.target.value })} />
          <TextAreaField label="需要准备的材料" example={'产品资料与合规声明\n目标人群与内容 Brief'} hint="每行一项" value={form.assets} onChange={(event) => setForm({ ...form, assets: event.target.value })} />
          <TextAreaField label="人工申请步骤" example={'登录官方营销平台\n选择方案并提交审核\n确认预算与排期'} hint="系统只展示清单，不会代为提交" value={form.steps} onChange={(event) => setForm({ ...form, steps: event.target.value })} />
          <TextAreaField label="衡量信号" example={'合规笔记产出数\n收藏率与评论质量\n可追踪访问或订单'} hint="每行一项，不写流量保证" value={form.measurement} onChange={(event) => setForm({ ...form, measurement: event.target.value })} />
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          <Field label="预算说明" example="具体门槛与报价需向平台确认" value={form.budget} onChange={(event) => setForm({ ...form, budget: event.target.value })} />
          <Field label="人工核验时间" example="本次打开官方页面核验的时间" type="datetime-local" value={form.verifiedAt} onChange={(event) => setForm({ ...form, verifiedAt: event.target.value })} />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end">
          <Button disabled={!form.stableKey || !form.name || !form.description || !form.sourceUrl || !form.objectives.length} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            保存方案草稿
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function MarketingProgramsPage() {
  const { principal } = useAuth()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [error, setError] = useState('')
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const canActivate = principal?.role === 'admin' || principal?.role === 'reviewer'
  const items = useQuery({
    queryKey: ['registry', 'platform_marketing_program'],
    queryFn: () => api.listRegistry('platform_marketing_program'),
  })
  const details = useQuery({
    queryKey: ['registry', 'platform_marketing_program', 'details', items.data?.map((item) => item.updated_at).join(',')],
    queryFn: () => Promise.all((items.data || []).map((item) => api.getRegistryItem('platform_marketing_program', item.id))),
    enabled: !!items.data,
  })
  const programs = useMemo(() => details.data || [], [details.data])
  const activation = useMutation({
    mutationFn: ({ itemId, revisionId }: { itemId: string; revisionId: string }) => api.activateRevision('platform_marketing_program', itemId, revisionId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ['registry', 'platform_marketing_program'],
      }),
    onError: (reason) => setError(reason instanceof Error ? reason.message : '激活失败'),
  })
  if (items.isLoading || details.isLoading) return <LoadingBlock label="正在读取营销支持方案" />
  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Platform Marketing Registry"
        title="营销支持方案"
        description="维护小红书官方营销能力、申请条件和衡量方式，供 Strategy 在每个 Brief 中评估。"
        actions={
          canWrite ? (
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" />
              录入方案
            </Button>
          ) : undefined
        }
      />
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
      <Callout title="方案建议不等于自动投放">本系统不会代为申请蒲公英合作或内容加热，也不会承诺曝光和转化。只有 active Revision 会进入新 Run。</Callout>
      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        {programs.map((program: RegistryItemDetail) => {
          const current = program.revisions.find((revision) => revision.id === program.current_revision_id)
          const draft = program.revisions.find((revision) => revision.status === 'draft')
          const latest = [...program.revisions].sort((a, b) => b.version - a.version)[0]
          const payload = (current || latest)?.payload as Record<string, unknown>
          return (
            <Card key={program.id} className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <StatusBadge status={current ? 'active' : 'draft'} />
                  <h2 className="mt-3 font-bold">{String(payload.name || program.stable_key)}</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{String(payload.description || '')}</p>
                  <p className="mt-3 text-xs text-brand-700">目标：{((payload.objectives as string[]) || []).join('、')}</p>
                  <a className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-600" href={String(payload.source_url)} target="_blank" rel="noreferrer">
                    查看官方来源 <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                {draft && canActivate && (
                  <Button
                    variant="secondary"
                    loading={activation.isPending}
                    onClick={() =>
                      activation.mutate({
                        itemId: program.id,
                        revisionId: draft.id,
                      })
                    }
                  >
                    激活 Revision
                  </Button>
                )}
              </div>
            </Card>
          )
        })}
      </div>
      {!programs.length && (
        <Card className="mt-5">
          <EmptyState icon={<Megaphone className="h-6 w-6" />} title="还没有营销支持方案" description="先录入并激活至少一项官方方案；否则 Strategy 会明确表示没有可引用方案。" />
        </Card>
      )}
      {showCreate && <ProgramModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}
