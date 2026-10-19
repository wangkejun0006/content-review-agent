import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Plus, ShieldAlert, ShieldCheck, Sparkles, UploadCloud } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal, StatusBadge, TextAreaField } from '../components/ui'
import { api } from '../lib/api'
import type { RegistryItemDetail } from '../types'
import type { PlatformRuleImportDraft } from '../types'

const officialSources = [
  {
    label: '小红书社区公约 2.0',
    url: 'https://pgy.xiaohongshu.com/help/detail?id=1eda0a065dd894063c2e029a49e8f6a1&userType=4',
    note: '真实性、AI 内容和健康内容基础边界',
  },
  {
    label: '蒲公英内容审核规范',
    url: 'https://pgy.xiaohongshu.com/help/detail?id=6495c527d1eedeeb48fb18b1f875650e&userType=4',
    note: '商业内容、夸大宣传与高危词',
  },
  {
    label: '蒲公英医疗医药内容管控',
    url: 'https://pgy.xiaohongshu.com/help/detail?id=6f23bc23acfe5edf82c060b3f72bb773&userType=4',
    note: '医疗器械、推荐证明与合作限制',
  },
]

type RulePlatform = 'xhs' | 'douyin'

function RuleModal({ platform, onClose }: { platform: RulePlatform; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    stableKey: '',
    category: 'health_claim',
    severity: 'blocker',
    ruleText: '',
    sourceUrl: '',
    verifiedAt: new Date().toISOString().slice(0, 16),
  })
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () =>
      api.createRegistryItem('platform_rule', {
        stable_key: form.stableKey,
        payload: {
          platform,
          category: form.category,
          rule_text: form.ruleText,
          severity: form.severity,
          source_url: form.sourceUrl,
          effective_from: null,
          verified_at: new Date(form.verifiedAt).toISOString(),
        },
        search_text: form.ruleText,
        source_uri: form.sourceUrl,
        verification_status: 'verified',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['registry', 'platform_rule'],
      })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '规则保存失败'),
  })
  return (
    <Modal title="录入平台规则" description="只录入已阅读和理解的规则，保存后仍是待 Reviewer 激活的草稿。" onClose={onClose}>
      <div className="space-y-5">
        <Callout title="不要把搜索摘要直接当成规则">请打开官方页面核对原文、适用范围和更新时间。规则应当是可执行判断，而不是模糊总结。</Callout>
        <Field label="适用平台" value={platform === 'xhs' ? '小红书' : '抖音'} disabled readOnly />
        <Field
          label="规则 Key"
          example="xhs-non-medical-no-treatment-claims"
          value={form.stableKey}
          onChange={(event) =>
            setForm({
              ...form,
              stableKey: event.target.value.toLowerCase().replace(/\s+/g, '-'),
            })
          }
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-2">
            <span className="text-sm font-semibold">规则类别</span>
            <select className="field-control" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>
              <option value="health_claim">健康宣传限制</option>
              <option value="content_compliance">内容合规</option>
              <option value="ai_content">AI 内容风险</option>
              <option value="recommendation">推荐与分发因素</option>
            </select>
            <span className="block text-xs text-slate-500">示例：非医疗设备效果宣传选择“健康宣传限制”</span>
          </label>
          <label className="space-y-2">
            <span className="text-sm font-semibold">严重程度</span>
            <select className="field-control" value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value })}>
              <option value="blocker">Blocker：必须阻断</option>
              <option value="warning">Warning：警告</option>
              <option value="information">Information：提示</option>
            </select>
            <span className="block text-xs text-slate-500">示例：疾病治疗宣称应为 Blocker</span>
          </label>
        </div>
        <TextAreaField label="可执行规则" example="消费级非医疗设备不得明示或暗示具有疾病治疗、诊断或保健功效。" hint="写清楚适用对象、禁止或允许的行为，不要只粘贴一串高危词。" value={form.ruleText} onChange={(event) => setForm({ ...form, ruleText: event.target.value })} />
        <Field label="官方来源 URL" example="https://pgy.xiaohongshu.com/help/detail?..." type="url" value={form.sourceUrl} onChange={(event) => setForm({ ...form, sourceUrl: event.target.value })} />
        <Field label="人工核验时间" example="今天打开官方页面核验的时间" type="datetime-local" value={form.verifiedAt} onChange={(event) => setForm({ ...form, verifiedAt: event.target.value })} />
        {error && <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        <div className="flex justify-end">
          <Button disabled={!form.stableKey || !form.ruleText || !form.sourceUrl} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            保存规则草稿
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function RuleAIImportModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [sourceUrl, setSourceUrl] = useState('')
  const [verifiedAt, setVerifiedAt] = useState(new Date().toISOString().slice(0, 16))
  const [pastedText, setPastedText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [draft, setDraft] = useState<PlatformRuleImportDraft | null>(null)
  const [error, setError] = useState('')
  const [duplicateReason, setDuplicateReason] = useState('')
  const ai = useMutation({
    mutationFn: () => api.platformRuleAiDraft(sourceUrl, verifiedAt, pastedText, file),
    onSuccess: setDraft,
    onError: (reason) => setError(reason instanceof Error ? reason.message : 'AI 整理失败'),
  })
  const save = useMutation({
    mutationFn: async () => {
      const currentDraft = draft!
      const currentDedup = currentDraft.dedup
      const revisionPayload = {
        payload: currentDraft.payload,
        search_text: currentDraft.search_text,
        source_uri: currentDraft.payload.source_url,
        verification_status: 'verified',
      }
      const target = currentDedup?.matches.find((match) => match.item_id)
      if (currentDedup?.recommended_action === 'new_revision' && target?.item_id) {
        const revision = await api.createRegistryRevision('platform_rule', target.item_id, revisionPayload)
        await api.resolveIngestion(currentDedup.ingestion_id, {
          decision: 'new_revision',
          resulting_item_id: target.item_id,
          resulting_revision_id: revision.id,
        })
        return revision
      }
      const item = await api.createRegistryItem('platform_rule', {
        stable_key: currentDraft.stable_key,
        ...revisionPayload,
      })
      if (currentDedup)
        await api.resolveIngestion(currentDedup.ingestion_id, {
          decision: currentDedup.duplicate_status === 'none' ? 'new_item' : 'independent',
          decision_reason: duplicateReason,
          resulting_item_id: item.id,
          resulting_revision_id: item.revisions[0]?.id,
        })
      return item
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['registry', 'platform_rule'],
      })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '规则保存失败'),
  })
  return (
    <Modal title="AI 整理平台规则" description="提供你已经打开并阅读的官方原文，AI 只把它整理成一条可编辑规则。" onClose={onClose} wide>
      {!draft ? (
        <div className="space-y-5">
          <Callout title="AI 不负责抓取或确认最新规则">请先打开官方页面，把与本产品和内容相关的一段原文粘贴或上传。URL 和核验时间由你确认，AI 不会替换。</Callout>
          <div className="grid gap-5 md:grid-cols-2">
            <Field label="官方来源 URL" example="https://pgy.xiaohongshu.com/help/detail?..." type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
            <Field label="你核验原文的时间" example="今天打开页面阅读的时间" type="datetime-local" value={verifiedAt} onChange={(event) => setVerifiedAt(event.target.value)} />
          </div>
          <TextAreaField label="粘贴一段规则原文" example="粘贴包含适用对象、禁止行为、例外条件的完整段落，不要只粘贴一个违规词。" hint="一次整理一条可执行规则更容易核验；长文可以分段处理。" value={pastedText} onChange={(event) => setPastedText(event.target.value)} />
          <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-dashed border-brand-200 bg-brand-50/50 p-4 text-sm text-brand-700">
            <UploadCloud className="h-5 w-5" />
            <span>{file ? file.name : '也可以上传 TXT、Markdown、PDF、Word 或 Excel'}</span>
            <input className="sr-only" type="file" accept=".txt,.md,.pdf,.docx,.xlsx" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end">
            <Button
              disabled={!sourceUrl || (!pastedText.trim() && !file)}
              loading={ai.isPending}
              onClick={() => {
                setError('')
                ai.mutate()
              }}
            >
              <Sparkles className="h-4 w-4" />
              生成可编辑规则
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          {draft.warnings.length > 0 && (
            <Callout title="AI 整理提醒" tone="warning">
              {draft.warnings.join('；')}
            </Callout>
          )}
          {draft.dedup?.duplicate_status !== 'none' && (
            <Callout title="发现已有相近平台规则" tone="warning">
              <p>{draft.dedup.message}</p>
              <p className="mt-1">{draft.dedup.matches.map((match) => match.label).join('、')}</p>
              {draft.dedup.recommended_action === 'review' && (
                <div className="mt-3">
                  <TextAreaField label="仍作为独立规则保存的原因" example="同一官方页面中的不同条款，适用范围和阻断条件不同。" value={duplicateReason} onChange={(event) => setDuplicateReason(event.target.value)} />
                </div>
              )}
            </Callout>
          )}
          <div className="rounded-2xl bg-slate-50 p-4 text-xs leading-5 text-slate-600">
            <strong>原文依据：</strong>
            {draft.source_excerpt}
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <Field
              label="规则 Key"
              example="xhs-health-no-treatment-claim"
              value={draft.stable_key}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  stable_key: event.target.value.toLowerCase().replace(/\s+/g, '-'),
                })
              }
            />
            <label className="block space-y-2">
              <span className="text-sm font-semibold">分类</span>
              <select
                className="field-control"
                value={draft.payload.category}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    payload: {
                      ...draft.payload,
                      category: event.target.value as PlatformRuleImportDraft['payload']['category'],
                    },
                  })
                }
              >
                <option value="health_claim">健康宣传限制</option>
                <option value="content_compliance">内容合规</option>
                <option value="ai_content">AI 内容风险</option>
                <option value="recommendation">推荐因素</option>
              </select>
            </label>
            <label className="block space-y-2">
              <span className="text-sm font-semibold">严重程度</span>
              <select
                className="field-control"
                value={draft.payload.severity}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    payload: {
                      ...draft.payload,
                      severity: event.target.value as PlatformRuleImportDraft['payload']['severity'],
                    },
                  })
                }
              >
                <option value="blocker">Blocker</option>
                <option value="warning">Warning</option>
                <option value="information">Information</option>
              </select>
            </label>
            <div className="rounded-2xl bg-brand-50 p-4 text-sm text-brand-800">
              AI 置信度：{Math.round(draft.confidence * 100)}%<p className="mt-1 text-xs">置信度不等于规则真实性，仍需人工对照原文。</p>
            </div>
          </div>
          <TextAreaField
            label="可执行规则"
            example="写清适用对象和禁止或允许的行为。"
            value={draft.payload.rule_text}
            onChange={(event) =>
              setDraft({
                ...draft,
                payload: { ...draft.payload, rule_text: event.target.value },
                search_text: event.target.value,
              })
            }
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-between">
            <Button variant="secondary" onClick={() => setDraft(null)}>
              返回原文
            </Button>
            <Button disabled={draft.dedup?.recommended_action === 'review' && !duplicateReason.trim()} loading={save.isPending} onClick={() => save.mutate()}>
              保存为待激活草稿
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

export function PlatformRulesPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [showAIImport, setShowAIImport] = useState(false)
  const [selectedPlatform, setSelectedPlatform] = useState<RulePlatform>('xhs')
  const { principal } = useAuth()
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const queryClient = useQueryClient()
  const itemsQuery = useQuery({
    queryKey: ['registry', 'platform_rule'],
    queryFn: () => api.listRegistry('platform_rule'),
  })
  const detailsQuery = useQuery({
    queryKey: ['registry', 'platform_rule', 'details', itemsQuery.data?.map((item) => item.updated_at).join(',')],
    queryFn: () => Promise.all((itemsQuery.data || []).map((item) => api.getRegistryItem('platform_rule', item.id))),
    enabled: !!itemsQuery.data,
  })
  const allRules = useMemo(() => detailsQuery.data || [], [detailsQuery.data])
  const rules = useMemo(
    () =>
      allRules.filter((rule) => {
        const latest = [...rule.revisions].sort((a, b) => b.version - a.version)[0]
        return String(latest?.payload.platform || 'xhs') === selectedPlatform
      }),
    [allRules, selectedPlatform],
  )
  const activeRevisions = rules.flatMap((rule) => rule.revisions.filter((revision) => revision.id === rule.current_revision_id))
  const staleActiveCount = activeRevisions.filter((revision) => {
    const verifiedAt = String((revision.payload as Record<string, unknown>).verified_at || '')
    const verifiedTime = Date.parse(verifiedAt)
    return !Number.isFinite(verifiedTime) || Date.now() - verifiedTime > 90 * 24 * 60 * 60 * 1000
  }).length
  const [error, setError] = useState('')
  const activation = useMutation({
    mutationFn: ({ itemId, revisionId }: { itemId: string; revisionId: string }) => api.activateRevision('platform_rule', itemId, revisionId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ['registry', 'platform_rule'],
      }),
    onError: (reason) => setError(reason instanceof Error ? reason.message : '激活失败'),
  })
  if (itemsQuery.isLoading || detailsQuery.isLoading) return <LoadingBlock label="正在审计平台规则" />

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Platform Knowledge"
        title="平台规则"
        description="按内容平台维护独立规则集合；当前小红书规则已可用于内容生成与合规审查，抖音仅预留入口。"
        actions={
          canWrite && selectedPlatform === 'xhs' ? (
            <>
              <Button variant="secondary" onClick={() => setShowCreate(true)}>
                <Plus className="h-4 w-4" />
                手动录入
              </Button>
              <Button onClick={() => setShowAIImport(true)}>
                <Sparkles className="h-4 w-4" />
                AI 整理规则
              </Button>
            </>
          ) : undefined
        }
      />
      <div className="mb-5 max-w-xs">
        <label className="block space-y-2">
          <span className="text-sm font-semibold">选择内容平台</span>
          <select
            className="field-control"
            value={selectedPlatform}
            onChange={(event) => setSelectedPlatform(event.target.value as RulePlatform)}
          >
            <option value="xhs">小红书</option>
            <option value="douyin">抖音（预留）</option>
          </select>
          <span className="block text-xs text-slate-500">不同平台使用独立规则集合，Run 只读取 Brief 对应平台的规则。</span>
        </label>
      </div>
      {selectedPlatform === 'douyin' && (
        <Callout title="抖音规则入口已预留" tone="warning">
          当前版本尚未建立抖音规则和内容 Agent 流程，因此这里只展示入口，不允许录入或用于 Run。后续接入时会复用同一 Registry Revision 机制。
        </Callout>
      )}
      {selectedPlatform === 'xhs' && (
        <>
          <Callout title="规则库保持少而精">
            首批只需覆盖医疗化、无证据宣称、虚假体验、绝对化、导流和 AI 内容等关键边界。模型负责语义理解，最终结论仍由人工审核；不必把帮助中心逐段复制成大量重复规则。
          </Callout>
          {!activeRevisions.length && (
            <div className="mt-4">
              <Callout title="当前已生效规则覆盖为 0，不能用于正式合规结论" tone="warning">
                数据库没有已激活的小红书 Platform Rule，请先建立并激活规则。
              </Callout>
            </div>
          )}
          {!!staleActiveCount && (
            <div className="mt-4">
              <Callout title={`${staleActiveCount} 条生效规则超过 90 天未核验`} tone="warning">
                请在方便时打开来源重新核对；规则仍可参与内容生成，结果会保留新鲜度提醒。
              </Callout>
            </div>
          )}
          <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_.72fr]">
            <div>
              {rules.length ? (
                <div className="space-y-4">
                  {rules.map((rule: RegistryItemDetail) => {
                    const current = rule.revisions.find((revision) => revision.id === rule.current_revision_id)
                    const latest = [...rule.revisions].sort((a, b) => b.version - a.version)[0]
                    const payload = (current || latest)?.payload as Record<string, string>
                    const draft = rule.revisions.find((revision) => revision.status === 'draft')
                    return (
                      <Card key={rule.id} className="p-5">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <div className="flex items-center gap-2">
                              <StatusBadge status={current ? 'active' : 'draft'} />
                              <span className="text-xs font-semibold uppercase text-slate-400">{payload.category}</span>
                            </div>
                            <h2 className="mt-3 font-bold text-graphite">{rule.stable_key}</h2>
                            <p className="mt-2 text-sm leading-6 text-slate-600">{payload.rule_text}</p>
                            <a className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-600" href={payload.source_url} target="_blank" rel="noreferrer">
                              查看来源 <ExternalLink className="h-3 w-3" />
                            </a>
                          </div>
                          <div className="shrink-0 text-right">
                            <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${payload.severity === 'blocker' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>{payload.severity}</span>
                            {draft && (principal?.role === 'reviewer' || principal?.role === 'admin') && (
                              <div className="mt-4">
                                <Button
                                  variant="secondary"
                                  loading={activation.isPending}
                                  onClick={() =>
                                    activation.mutate({
                                      itemId: rule.id,
                                      revisionId: draft.id,
                                    })
                                  }
                                >
                                  激活 Revision
                                </Button>
                              </div>
                            )}
                          </div>
                        </div>
                      </Card>
                    )
                  })}
                </div>
              ) : (
                <Card>
                  <EmptyState icon={<ShieldAlert className="h-6 w-6" />} title="规则库尚未开始建设" description="从官方公开来源建立少量可执行规则，并通过 Revision 激活后使用。" action={canWrite ? <Button onClick={() => setShowCreate(true)}>录入第一条规则</Button> : undefined} />
                </Card>
              )}
              {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            </div>
            <Card className="h-fit p-5">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-brand-600" />
                <h2 className="font-bold">建议优先核对的官方来源</h2>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">以下只是入口，不会自动写入 Registry。页面内容可能变化，录入时必须填写人工核验时间。</p>
              <div className="mt-4 space-y-3">
                {officialSources.map((source) => (
                  <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-3 rounded-2xl border border-slate-100 p-4 transition hover:border-brand-100 hover:bg-brand-50/50">
                    <div>
                      <p className="text-sm font-semibold text-graphite">{source.label}</p>
                      <p className="mt-1 text-xs text-slate-500">{source.note}</p>
                    </div>
                    <ExternalLink className="h-4 w-4 shrink-0 text-brand-600" />
                  </a>
                ))}
              </div>
              <div className="mt-5 rounded-2xl bg-slate-50 p-4 text-xs leading-5 text-slate-600">
                <strong>建议首批覆盖：</strong>
                商业内容真实性、承诺保证、医疗/保健功效、非医疗产品混淆、虚假体验、标题党、盗图、绝对化用语、导流与 AI 内容风险。
              </div>
            </Card>
          </div>
        </>
      )}
      {showCreate && canWrite && selectedPlatform === 'xhs' && <RuleModal platform={selectedPlatform} onClose={() => setShowCreate(false)} />}
      {showAIImport && canWrite && selectedPlatform === 'xhs' && <RuleAIImportModal onClose={() => setShowAIImport(false)} />}
    </div>
  )
}
