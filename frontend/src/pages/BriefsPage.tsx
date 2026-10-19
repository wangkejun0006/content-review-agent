import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArrowRight, Eye, FilePlus2, PenTool, Pencil, Play, Plus, RotateCcw, Sparkles } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal, StatusBadge, TextAreaField } from '../components/ui'
import { api } from '../lib/api'
import type { CampaignBrief, ProductPayload, RegistryItemDetail } from '../types'

const briefSchema = z.object({
  name: z.string().min(2, '请填写任务名称'),
  objective: z.string().min(5, '请具体描述内容目标'),
  productId: z.string().uuid('请选择已激活产品'),
  keyMessage: z.string().min(2, '请填写希望用户记住的信息'),
  scenario: z.string().min(2, '请填写使用场景'),
  requiredPoints: z.string(),
  forbiddenPoints: z.string(),
  tone: z.string().min(2),
  ctaType: z.enum(['discussion', 'save', 'learn_more']),
  bodyLength: z.coerce.number().min(100).max(2000),
  marketingSupportPolicy: z.enum(['organic_only', 'evaluate', 'required']),
  marketingObjective: z.enum(['awareness', 'content_validation', 'creator_seeding', 'amplification', 'conversion']),
  marketingBudgetMin: z.string(),
  marketingBudgetMax: z.string(),
})
type BriefForm = z.infer<typeof briefSchema>

const ctaLabels: Record<string, string> = {
  discussion: '邀请讨论',
  save: '引导收藏',
  learn_more: '了解更多',
}

const marketingPolicyLabels: Record<string, string> = {
  organic_only: '仅自然流量',
  evaluate: '由 Strategy 评估',
  required: '必须给出支持方案',
}

const marketingObjectiveLabels: Record<string, string> = {
  awareness: '品牌/产品认知',
  content_validation: '内容验证',
  creator_seeding: '达人种草',
  amplification: '放大优质内容',
  conversion: '购买转化',
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-100 bg-white p-4">
      <h3 className="text-xs font-bold uppercase tracking-wide text-brand-700">{title}</h3>
      <div className="mt-2 text-sm leading-6 text-slate-600">{children}</div>
    </section>
  )
}

export function BriefDetailModal({ brief, products, onClose }: { brief: CampaignBrief; products: RegistryItemDetail[]; onClose: () => void }) {
  const constraints = (brief.constraints || {}) as Record<string, unknown>
  const product = products.find((item) => brief.product_item_ids.includes(item.id))
  const productPayload = product?.revisions.find((revision) => revision.id === product.current_revision_id)?.payload as unknown as ProductPayload | undefined
  const requiredPoints = Array.isArray(constraints.required_points) ? constraints.required_points.map(String) : []
  const forbiddenPoints = Array.isArray(constraints.forbidden_points) ? constraints.forbidden_points.map(String) : []
  const tones = Array.isArray(constraints.tone) ? constraints.tone.map(String) : []
  const budgetMin = constraints.marketing_budget_min
  const budgetMax = constraints.marketing_budget_max
  const budget = budgetMin == null && budgetMax == null ? '未设置' : `${budgetMin ?? 0}–${budgetMax ?? '不限'} 元`

  return (
    <Modal title={brief.name} description="只读查看这份 Brief 的运营目标和生成约束；编辑后只影响未来启动的新 Run。" onClose={onClose} wide>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-brand-50 px-4 py-3">
          <div>
            <p className="text-xs font-bold text-brand-700">关联产品</p>
            <p className="mt-1 font-semibold text-brand-950">{productPayload?.name || brief.product_item_ids[0] || '未找到产品'}</p>
          </div>
          <StatusBadge status={brief.archived_at ? 'retired' : 'active'} />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <DetailSection title="内容目标"><p className="whitespace-pre-wrap">{brief.objective}</p></DetailSection>
          <DetailSection title="核心信息"><p className="whitespace-pre-wrap">{String(constraints.key_message || '未填写')}</p></DetailSection>
          <DetailSection title="使用场景"><p className="whitespace-pre-wrap">{String(constraints.scenario || '未填写')}</p></DetailSection>
          <DetailSection title="内容形式">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
              <dt className="text-slate-400">平台</dt><dd className="text-right">小红书</dd>
              <dt className="text-slate-400">内容身份</dt><dd className="text-right">品牌自有内容</dd>
              <dt className="text-slate-400">CTA</dt><dd className="text-right">{ctaLabels[String(constraints.cta_type)] || '未设置'}</dd>
              <dt className="text-slate-400">目标字数</dt><dd className="text-right">{String(constraints.body_length || 600)} 字</dd>
              <dt className="text-slate-400">候选数量</dt><dd className="text-right">{String(constraints.candidate_count || 3)} 个</dd>
            </dl>
          </DetailSection>
          <DetailSection title="必须提到">
            {requiredPoints.length ? <ul className="list-disc space-y-1 pl-5">{requiredPoints.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="text-slate-400">未设置</p>}
          </DetailSection>
          <DetailSection title="禁止内容">
            {forbiddenPoints.length ? <ul className="list-disc space-y-1 pl-5">{forbiddenPoints.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="text-slate-400">未设置</p>}
          </DetailSection>
        </div>
        <DetailSection title="语气与营销支持">
          <div className="flex flex-wrap gap-2">{tones.length ? tones.map((tone) => <span key={tone} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{tone}</span>) : <span className="text-slate-400">未设置语气</span>}</div>
          <dl className="mt-4 grid gap-2 sm:grid-cols-3">
            <div><dt className="text-xs text-slate-400">支持策略</dt><dd className="mt-1 font-semibold">{marketingPolicyLabels[String(constraints.marketing_support_policy)] || '未设置'}</dd></div>
            <div><dt className="text-xs text-slate-400">营销目标</dt><dd className="mt-1 font-semibold">{marketingObjectiveLabels[String(constraints.marketing_objective)] || '未设置'}</dd></div>
            <div><dt className="text-xs text-slate-400">预算范围</dt><dd className="mt-1 font-semibold">{budget}</dd></div>
          </dl>
        </DetailSection>
        <p className="text-xs text-slate-400">创建于 {new Date(brief.created_at).toLocaleString('zh-CN')} · 最近更新 {new Date(brief.updated_at).toLocaleString('zh-CN')}</p>
      </div>
    </Modal>
  )
}

function BriefModal({ products, brief, onClose }: { products: RegistryItemDetail[]; brief?: CampaignBrief; onClose: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [submitError, setSubmitError] = useState('')
  const [createdBriefId, setCreatedBriefId] = useState<string | null>(null)
  const existingConstraints = (brief?.constraints || {}) as Record<string, unknown>
  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm<BriefForm>({
    resolver: zodResolver(briefSchema),
    defaultValues: {
      name: brief?.name || '',
      objective: brief?.objective || '',
      tone: Array.isArray(existingConstraints.tone) ? existingConstraints.tone.join(', ') : '克制, 生活化, 科技美学',
      ctaType: (existingConstraints.cta_type as BriefForm['ctaType']) || 'discussion',
      bodyLength: Number(existingConstraints.body_length || 600),
      productId: brief?.product_item_ids[0] || products[0]?.id || '',
      keyMessage: String(existingConstraints.key_message || ''),
      scenario: String(existingConstraints.scenario || ''),
      requiredPoints: Array.isArray(existingConstraints.required_points) ? existingConstraints.required_points.join('\n') : '',
      forbiddenPoints: Array.isArray(existingConstraints.forbidden_points) ? existingConstraints.forbidden_points.join('\n') : '',
      marketingSupportPolicy: (existingConstraints.marketing_support_policy as BriefForm['marketingSupportPolicy']) || 'evaluate',
      marketingObjective: (existingConstraints.marketing_objective as BriefForm['marketingObjective']) || 'awareness',
      marketingBudgetMin: existingConstraints.marketing_budget_min == null ? '' : String(existingConstraints.marketing_budget_min),
      marketingBudgetMax: existingConstraints.marketing_budget_max == null ? '' : String(existingConstraints.marketing_budget_max),
    },
  })
  const selected = products.find((item) => item.id === watch('productId'))
  const selectedPayload = selected?.revisions.find((revision) => revision.id === selected.current_revision_id)?.payload as unknown as ProductPayload | undefined
  const saveMutation = useMutation({
    mutationFn: (data: BriefForm) =>
      (brief ? api.updateBrief(brief.id, {
        name: data.name,
        objective: data.objective,
        product_item_ids: [data.productId],
        audience_item_ids: [],
        constraints: {
          platform: 'xhs',
          content_identity: 'brand_owned',
          key_message: data.keyMessage,
          required_points: data.requiredPoints
            .split('\n')
            .map((item) => item.trim())
            .filter(Boolean),
          forbidden_points: data.forbiddenPoints
            .split('\n')
            .map((item) => item.trim())
            .filter(Boolean),
          tone: data.tone
            .split(/[,，]/)
            .map((item) => item.trim())
            .filter(Boolean),
          scenario: data.scenario,
          cta_type: data.ctaType,
          body_length: data.bodyLength,
          candidate_count: 3,
          marketing_support_policy: data.marketingSupportPolicy,
          marketing_objective: data.marketingObjective,
          marketing_budget_min: data.marketingBudgetMin ? Number(data.marketingBudgetMin) : null,
          marketing_budget_max: data.marketingBudgetMax ? Number(data.marketingBudgetMax) : null,
        },
      }) : api.createBrief({
        name: data.name,
        objective: data.objective,
        product_item_ids: [data.productId],
        audience_item_ids: [],
        constraints: {
          platform: 'xhs',
          content_identity: 'brand_owned',
          key_message: data.keyMessage,
          required_points: data.requiredPoints.split('\n').map((item) => item.trim()).filter(Boolean),
          forbidden_points: data.forbiddenPoints.split('\n').map((item) => item.trim()).filter(Boolean),
          tone: data.tone.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
          scenario: data.scenario,
          cta_type: data.ctaType,
          body_length: data.bodyLength,
          candidate_count: 3,
          marketing_support_policy: data.marketingSupportPolicy,
          marketing_objective: data.marketingObjective,
          marketing_budget_min: data.marketingBudgetMin ? Number(data.marketingBudgetMin) : null,
          marketing_budget_max: data.marketingBudgetMax ? Number(data.marketingBudgetMax) : null,
        },
      })),
    onSuccess: async (savedBrief) => {
      await queryClient.invalidateQueries({ queryKey: ['briefs'] })
      if (brief) onClose()
      else setCreatedBriefId(savedBrief.id)
    },
    onError: (reason) => setSubmitError(reason instanceof Error ? reason.message : 'Brief 保存失败'),
  })
  const runMutation = useMutation({
    mutationFn: () => api.createRun(createdBriefId!),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      navigate(`/runs/${run.id}`)
    },
    onError: (reason) => setSubmitError(reason instanceof Error ? reason.message : '任务启动失败'),
  })

  if (createdBriefId)
    return (
      <Modal title="Brief 已创建" description="现在可以启动 LangGraph 内容任务。" onClose={onClose}>
        <div className="py-5 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-emerald-50 text-emerald-600">
            <Sparkles className="h-7 w-7" />
          </div>
          <h3 className="mt-5 text-xl font-bold">信息已保存为受治理 Brief</h3>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">启动后会冻结当前 active Registry Revision，并由 Worker 生成三个候选。</p>
          <div className="mt-7 flex justify-center gap-3">
            <Button variant="secondary" onClick={onClose}>
              稍后启动
            </Button>
            <Button loading={runMutation.isPending} onClick={() => runMutation.mutate()}>
              <Play className="h-4 w-4" />
              立即启动任务
            </Button>
          </div>
          {submitError && <p className="mt-4 text-sm text-red-600">{submitError}</p>}
        </div>
      </Modal>
    )

  return (
    <Modal title={brief ? '编辑内容 Brief' : '创建小红书内容 Brief'} description={brief ? '修改只影响之后启动的新 Run，历史运行保持原有知识快照。' : '用运营语言描述任务，系统会转换为严格的后端结构。'} onClose={onClose} wide>
      <form
        className="space-y-7"
        onSubmit={handleSubmit((data) => {
          setSubmitError('')
          saveMutation.mutate(data)
        })}
      >
        <Callout title="单一正式运行流程">
          系统会冻结当前已激活的知识资产并使用当前配置的模型模式（本地演示为确定性离线响应）。产品缺少 Claim 或证据时不会阻止生成，但结果会明确提示事实边界；内容仍需人工审核和手动发布。
        </Callout>
        <div className="grid gap-5 md:grid-cols-2">
          <Field label="任务名称" example="NOTE01 通勤创意文具种草" placeholder="方便团队识别的内部名称" error={errors.name?.message} {...register('name')} />
          <label className="block space-y-2">
            <span className="flex items-baseline justify-between">
              <span className="text-sm font-semibold">选择产品</span>
              <span className="text-xs text-slate-400">仅显示已激活产品</span>
            </span>
            <select className="field-control" {...register('productId')}>
              {products.map((product) => {
                const payload = product.revisions.find((revision) => revision.id === product.current_revision_id)?.payload as unknown as ProductPayload
                return (
                  <option key={product.id} value={product.id}>
                    {payload?.name || product.stable_key}
                  </option>
                )
              })}
            </select>
            {errors.productId && <p className="text-xs text-red-600">{errors.productId.message}</p>}
          </label>
        </div>
        {selectedPayload && (
          <div className="rounded-2xl border border-brand-100 bg-brand-50/60 px-4 py-3">
            <p className="text-xs font-bold text-brand-700">本次内容使用的产品</p>
            <p className="mt-1 text-sm font-semibold text-brand-900">{selectedPayload.name}</p>
            <p className="mt-1 text-xs text-brand-700">Run 创建时会固化该产品当前 Revision，不会跟随后续修改漂移。</p>
          </div>
        )}
        <TextAreaField label="内容目标" example="让关注书桌布置和消费电子的城市女性认识 NOTE01 的创意文具定位，建立收藏和讨论意愿。" error={errors.objective?.message} {...register('objective')} />
        <div className="grid gap-5 md:grid-cols-2">
          <TextAreaField label="希望用户记住的一句话" example="点阵布局让纸笔记录更清晰。" error={errors.keyMessage?.message} {...register('keyMessage')} />
          <TextAreaField label="核心使用场景" example="工作日通勤书桌布置、出门前搭配首饰。" error={errors.scenario?.message} {...register('scenario')} />
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          <TextAreaField label="必须提到" example={'消费级电子产品\n科技美学与日常搭配'} hint="每行一项；仍需受 Product Context 事实约束。" {...register('requiredPoints')} />
          <TextAreaField label="绝对不要提" example={'治疗、改善睡眠等医疗效果\n虚构第一人称使用体验'} hint="每行一项；Compliance 仍会独立检查。" {...register('forbiddenPoints')} />
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          <Field label="内容语气" example="克制, 生活化, 科技美学" {...register('tone')} />
          <label className="block space-y-2">
            <span className="text-sm font-semibold">CTA 类型</span>
            <select className="field-control" {...register('ctaType')}>
              <option value="discussion">邀请讨论</option>
              <option value="save">引导收藏</option>
              <option value="learn_more">了解更多</option>
            </select>
            <span className="block text-xs text-slate-500">示例：邀请用户分享搭配偏好</span>
          </label>
          <Field label="正文目标字数" example="600" type="number" min={100} max={2000} error={errors.bodyLength?.message} {...register('bodyLength')} />
        </div>
        <div className="rounded-3xl border border-brand-100 bg-brand-50/40 p-5">
          <div className="mb-4">
            <p className="text-sm font-bold text-brand-900">小红书官方营销支持评估</p>
            <p className="mt-1 text-xs leading-5 text-brand-700">Strategy 会结合已激活的蒲公英合作或内容加热方案给出建议和申请清单；系统不会自动申请或投放。</p>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <label className="block space-y-2">
              <span className="text-sm font-semibold">支持方案策略</span>
              <select className="field-control" {...register('marketingSupportPolicy')}>
                <option value="organic_only">本次仅自然流量</option>
                <option value="evaluate">由 Strategy 评估是否需要</option>
                <option value="required">必须给出支持方案</option>
              </select>
              <span className="block text-xs text-slate-500">示例：新品首发可选“评估”；日常内容可选“仅自然流量”。</span>
            </label>
            <label className="block space-y-2">
              <span className="text-sm font-semibold">本次营销目标</span>
              <select className="field-control" {...register('marketingObjective')}>
                <option value="awareness">品牌/产品认知</option>
                <option value="content_validation">内容验证</option>
                <option value="creator_seeding">达人种草</option>
                <option value="amplification">放大优质内容</option>
                <option value="conversion">购买转化</option>
              </select>
              <span className="block text-xs text-slate-500">该目标只用于匹配方案，不代表平台效果保证。</span>
            </label>
          </div>
          <div className="mt-5 grid gap-5 md:grid-cols-2">
            <Field label="预算下限（元，可空）" example="5000" type="number" min={0} {...register('marketingBudgetMin')} />
            <Field label="预算上限（元，可空）" example="20000" type="number" min={0} {...register('marketingBudgetMax')} />
          </div>
        </div>
        {submitError && <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{submitError}</div>}
        <div className="flex items-center justify-between border-t border-slate-200 pt-5">
          <p className="text-xs text-slate-500">每次固定生成 3 个候选，角度可以相同但表达方式必须有差异。</p>
          <Button type="submit" loading={saveMutation.isPending}>
            <FilePlus2 className="h-4 w-4" />
            {brief ? '保存修改' : '保存 Brief'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export function BriefsPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [editingBrief, setEditingBrief] = useState<CampaignBrief | null>(null)
  const [viewingBrief, setViewingBrief] = useState<CampaignBrief | null>(null)
  const { principal } = useAuth()
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const canDelete = principal?.role === 'admin'
  const queryClient = useQueryClient()
  const briefsQuery = useQuery({
    queryKey: ['briefs', 'all'],
    queryFn: () => api.listBriefs(true),
  })
  const itemsQuery = useQuery({
    queryKey: ['registry', 'product'],
    queryFn: () => api.listRegistry('product'),
  })
  const productsQuery = useQuery({
    queryKey: ['registry', 'product', 'active-details', itemsQuery.data?.map((item) => item.updated_at).join(',')],
    queryFn: async () => await Promise.all((itemsQuery.data || []).filter((item) => item.current_revision_id).map((item) => api.getRegistryItem('product', item.id))),
    enabled: !!itemsQuery.data,
  })
  const activeProducts = useMemo(() => productsQuery.data || [], [productsQuery.data])
  const archiveMutation = useMutation({
    mutationFn: api.archiveBrief,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['briefs'] }),
  })
  const restoreMutation = useMutation({
    mutationFn: api.restoreBrief,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['briefs'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: api.permanentlyDeleteBrief,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['briefs'] }),
  })
  if (briefsQuery.isLoading || productsQuery.isLoading) return <LoadingBlock label="正在读取内容任务" />
  const allBriefs = briefsQuery.data || []
  const briefs = allBriefs.filter((brief) => (showArchived ? !!brief.archived_at : !brief.archived_at))

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Campaign Brief"
        title="内容任务"
        description="先把运营目标讲清楚，再交给 Agent 生成；不需要填写 JSON。"
        actions={
          canWrite ? (
            <Button disabled={!activeProducts.length} onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" />
              新建 Brief
            </Button>
          ) : undefined
        }
      />
      <div className="mb-5 flex gap-2 rounded-2xl bg-slate-100 p-1">
        <button className={`rounded-xl px-4 py-2 text-sm font-semibold ${!showArchived ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => setShowArchived(false)}>
          当前 Brief（{allBriefs.filter((item) => !item.archived_at).length}）
        </button>
        <button className={`rounded-xl px-4 py-2 text-sm font-semibold ${showArchived ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => setShowArchived(true)}>
          回收站（{allBriefs.filter((item) => !!item.archived_at).length}）
        </button>
      </div>
      {!activeProducts.length && (
        <Callout title="需要先激活至少一个产品" tone="warning">
          产品草稿不会进入 Brief。请在“产品知识”中由 Reviewer 或 Admin 激活确认后的 Revision。
        </Callout>
      )}
      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        {briefs.map((brief) => (
          <Card key={brief.id} className="p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
            <div className="flex items-start justify-between gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-violet-50 text-violet-600">
                <PenTool className="h-5 w-5" />
              </div>
              <StatusBadge status={brief.archived_at ? 'retired' : 'active'} />
            </div>
            <button className="group mt-4 block w-full rounded-xl text-left outline-none focus:ring-4 focus:ring-brand-100" onClick={() => setViewingBrief(brief)} aria-label={`查看 Brief 详情：${brief.name}`}>
              <h2 className="text-lg font-bold text-graphite transition group-hover:text-brand-700">{brief.name}</h2>
              <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-500">{brief.objective}</p>
            </button>
            <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
              <span className="text-xs text-slate-400">{new Date(brief.created_at).toLocaleString('zh-CN')}</span>
              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="ghost" onClick={() => setViewingBrief(brief)}>
                  <Eye className="h-4 w-4" />查看详情
                </Button>
                {canWrite && <>
                {brief.archived_at ? (
                  <>
                    <Button variant="secondary" loading={restoreMutation.isPending} onClick={() => restoreMutation.mutate(brief.id)}>
                      <RotateCcw className="h-4 w-4" />恢复
                    </Button>
                    {canDelete && (
                      <Button variant="danger" loading={deleteMutation.isPending} onClick={() => {
                        const confirmation = window.prompt(`永久删除不可恢复。请输入 Brief 名称“${brief.name}”确认：`)
                        if (confirmation === brief.name) deleteMutation.mutate(brief.id)
                      }}>
                        永久删除
                      </Button>
                    )}
                  </>
                ) : (
                  <>
                    <Button variant="ghost" onClick={() => setEditingBrief(brief)}>
                      <Pencil className="h-4 w-4" />编辑
                    </Button>
                    <Button variant="danger" loading={archiveMutation.isPending} onClick={() => {
                      if (window.confirm('删除后 Brief 会移出默认列表，已有 Run 和审核记录不会被删除。是否继续？')) archiveMutation.mutate(brief.id)
                    }}>
                      <Archive className="h-4 w-4" />移入回收站
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        const run = await api.createRun(brief.id)
                        window.location.href = `/runs/${run.id}`
                      }}
                    >
                      <Play className="h-4 w-4" />
                      启动新 Run
                    </Button>
                  </>
                )}
                </>}
              </div>
            </div>
          </Card>
        ))}
      </div>
      {!briefs.length && (
        <Card className="mt-5">
          <EmptyState
            icon={<PenTool className="h-6 w-6" />}
            title="还没有内容 Brief"
            description="选择已激活产品，用业务语言描述目标、场景、必提信息和禁区。"
            action={
              canWrite && activeProducts.length ? (
                <Button onClick={() => setShowCreate(true)}>
                  创建第一份 Brief <ArrowRight className="h-4 w-4" />
                </Button>
              ) : undefined
            }
          />
        </Card>
      )}
      {showCreate && canWrite && <BriefModal products={activeProducts} onClose={() => setShowCreate(false)} />}
      {editingBrief && canWrite && <BriefModal products={activeProducts} brief={editingBrief} onClose={() => setEditingBrief(null)} />}
      {viewingBrief && <BriefDetailModal brief={viewingBrief} products={activeProducts} onClose={() => setViewingBrief(null)} />}
    </div>
  )
}
