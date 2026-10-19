import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Archive, Boxes, Check, ChevronRight, FileSpreadsheet, ImagePlus, Pencil, Plus, RotateCcw, ShieldCheck, Sparkles, UploadCloud } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/PageHeader'
import { Button, Callout, Card, EmptyState, Field, LoadingBlock, Modal, StatusBadge, TextAreaField } from '../components/ui'
import { api } from '../lib/api'
import { productImportHasUnsavedChanges } from '../lib/productImport'
import type { ProductImportDraft, ProductMedia, ProductPayload, RegistryItemDetail } from '../types'

const emptyProduct: ProductImportDraft = {
  stable_key: '',
  payload: {
    name: '',
    sku: '',
    product_type: 'stationery',
    description: '',
    features: [],
    materials: [],
    non_medical_disclaimer: '消费级电子产品，不属于医疗设备。',
  },
  search_text: '',
  field_confidence: {},
  missing_fields: [],
  warnings: [],
  source_summaries: [],
}

const note01Image = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480"><rect width="640" height="480" fill="#f3f0e9"/><rect x="205" y="55" width="230" height="340" rx="12" fill="#9eb6ce" stroke="#3e5368" stroke-width="4"/><path d="M235 55V395" stroke="#3e5368" stroke-width="3"/><text x="260" y="210" fill="#18334f" font-size="18">PAPER ORBIT</text><text x="260" y="245" fill="#18334f">NOTE01</text><text x="100" y="450" fill="#18334f">FICTIONAL DIAGRAM - NOT A REAL PRODUCT</text></svg>',
)
const MIB = 1024 * 1024
const productUploadLimits: Record<string, number> = {
  txt: 1 * MIB,
  md: 1 * MIB,
  pdf: 15 * MIB,
  docx: 15 * MIB,
  xlsx: 8 * MIB,
}

function productFileKind(file: File) {
  const suffix = file.name.split('.').pop()?.toLowerCase() || ''
  const labels: Record<string, string> = {
    txt: 'TXT',
    md: 'Markdown',
    pdf: 'PDF',
    docx: 'Word',
    xlsx: 'Excel',
  }
  return labels[suffix] || '产品资料'
}

function validateProductFiles(files: File[]) {
  if (files.length > 8) return '单次最多上传 8 个文件，请分批整理。'
  let total = 0
  for (const file of files) {
    const suffix = file.name.split('.').pop()?.toLowerCase() || ''
    const limit = productUploadLimits[suffix]
    if (!limit) return `不支持 ${file.name}；请使用 TXT、Markdown、PDF、DOCX 或 XLSX。旧版 XLS 请先另存为 XLSX。`
    if (file.size > limit) return `${file.name} 超过 ${limit / MIB} MB，请压缩或拆分后上传。`
    total += file.size
  }
  if (total > 25 * MIB) return '本次文件总大小超过 25 MB，请分批整理。'
  return ''
}

function confidenceLabel(value?: number) {
  if (value === undefined) return null
  if (value >= 0.75) return { label: '较高置信', className: 'text-emerald-700 bg-emerald-50' }
  if (value >= 0.45) return { label: '需要核对', className: 'text-amber-700 bg-amber-50' }
  return { label: '信息不足', className: 'text-red-700 bg-red-50' }
}

function ProductEditor({ draft, onChange, onSave, saving, duplicateReason, onDuplicateReasonChange, editing = false }: { draft: ProductImportDraft; onChange: (draft: ProductImportDraft) => void; onSave: () => void; saving: boolean; duplicateReason?: string; onDuplicateReasonChange?: (value: string) => void; editing?: boolean }) {
  const saveReady = /^[a-z0-9][a-z0-9_-]{1,199}$/.test(draft.stable_key) && draft.payload.name.trim().length > 0 && draft.payload.description.trim().length > 0 && draft.payload.features.length > 0 && (draft.dedup?.recommended_action !== 'review' || !!duplicateReason?.trim())
  const updatePayload = <K extends keyof ProductPayload>(key: K, value: ProductPayload[K]) => onChange({ ...draft, payload: { ...draft.payload, [key]: value } })
  const confidence = (field: string) => {
    const item = confidenceLabel(draft.field_confidence[field])
    return item ? <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${item.className}`}>{item.label}</span> : null
  }

  return (
    <div className="space-y-6">
      {(draft.warnings.length > 0 || draft.missing_fields.length > 0) && (
        <div className="grid gap-3 md:grid-cols-2">
          {draft.warnings.length > 0 && (
            <Callout title="AI 风险提醒" tone="warning">
              <ul className="list-disc pl-4">
                {draft.warnings.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Callout>
          )}
          {draft.missing_fields.length > 0 && (
            <Callout title="仍需补充的信息">
              <ul className="list-disc pl-4">
                {draft.missing_fields.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Callout>
          )}
        </div>
      )}
      {draft.dedup && draft.dedup.duplicate_status !== 'none' && (
        <Callout title="发现已有相近资产" tone="warning">
          <p>{draft.dedup.message}</p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            {draft.dedup.matches.map((match) => (
              <li key={`${match.item_id}-${match.revision_id}`}>
                {match.label}（{Math.round(match.similarity * 100)}%）
              </li>
            ))}
          </ul>
          {draft.dedup.recommended_action === 'new_revision' ? (
            <p className="mt-2 font-semibold">保存时将默认追加到同一产品的 Revision 历史，不会创建重复 SKU。</p>
          ) : (
            <div className="mt-3">
              <TextAreaField label="仍作为独立产品保存的原因" example="名称相近但属于不同硬件型号，SKU 和规格均独立。" value={duplicateReason || ''} onChange={(event) => onDuplicateReasonChange?.(event.target.value)} />
            </div>
          )}
        </Callout>
      )}
      <div className="grid gap-5 md:grid-cols-2">
        <Field
          label="Registry Key"
          example="paper-orbit-note01"
          hint="用于系统稳定引用，只能使用小写英文、数字、短横线或下划线。"
          value={draft.stable_key}
          disabled={editing}
          onChange={(event) =>
            onChange({
              ...draft,
              stable_key: event.target.value.toLowerCase().replace(/\s+/g, '-'),
            })
          }
        />
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">产品类型</span>
            {confidence('product_type')}
          </div>
          <select className="field-control" value={draft.payload.product_type} onChange={(event) => updatePayload('product_type', event.target.value as ProductPayload['product_type'])}>
            <option value="stationery">点阵笔记本</option>
            <option value="desk_accessory">智能桌面收纳夹</option>
          </select>
          <p className="mt-2 text-xs text-slate-500">示例：NOTE01 选择“点阵笔记本”</p>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">产品名称</span>
            {confidence('name')}
          </div>
          <Field label="" aria-label="产品名称" example="Paper Orbit NOTE01 点阵笔记本" value={draft.payload.name} onChange={(event) => updatePayload('name', event.target.value)} />
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">SKU / 型号</span>
            {confidence('sku')}
          </div>
          <Field label="" aria-label="SKU" example="NOTE01" value={draft.payload.sku || ''} onChange={(event) => updatePayload('sku', event.target.value || null)} />
        </div>
      </div>
      <TextAreaField label="产品客观描述" example="采用模块化设计的消费级点阵笔记本，具体功能以已确认规格为准。" hint="描述“它是什么”，不要在这里写疗效、用户体验或没有证据的材料结论。" value={draft.payload.description} onChange={(event) => updatePayload('description', event.target.value)} />
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">功能事实</span>
            {confidence('features')}
          </div>
          <TextAreaField
            label=""
            aria-label="功能事实"
            example={'可连接配套移动应用\n支持磁吸充电'}
            hint="每行一项；暂不确定的内容请标注“待确认”。"
            value={draft.payload.features.join('\n')}
            onChange={(event) =>
              updatePayload(
                'features',
                event.target.value
                  .split('\n')
                  .map((item) => item.trim())
                  .filter(Boolean),
              )
            }
          />
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">材料事实</span>
            {confidence('materials')}
          </div>
          <TextAreaField
            label=""
            aria-label="材料事实"
            example={'虎眼石（需规格或采购证明）\n不锈钢组件'}
            hint="每行一项；没有权威资料时保持为空。"
            value={draft.payload.materials.join('\n')}
            onChange={(event) =>
              updatePayload(
                'materials',
                event.target.value
                  .split('\n')
                  .map((item) => item.trim())
                  .filter(Boolean),
              )
            }
          />
        </div>
      </div>
      <TextAreaField label="非医疗设备声明" example="消费级电子产品，不属于医疗设备，不能用于疾病诊断或治疗。" value={draft.payload.non_medical_disclaimer} onChange={(event) => updatePayload('non_medical_disclaimer', event.target.value)} />
      <Field label="检索摘要" example="Paper Orbit NOTE01 点阵笔记本 创意文具" hint="帮助后续 Agent 检索，不作为对外宣传文案。" value={draft.search_text} onChange={(event) => onChange({ ...draft, search_text: event.target.value })} />
      <div className="flex items-center justify-between border-t border-slate-200 pt-5">
        <p className="max-w-lg text-xs leading-5 text-slate-500">{saveReady ? (editing ? '保存后生成新的产品 Revision 草稿；激活后只影响未来 Run，历史运行仍使用旧版本。' : '保存后只会创建 Registry 草稿。Reviewer 激活之前，不会进入任何正式 Growth Run。') : '请至少填写合法 Registry Key、产品名称、客观描述和一项功能事实。'}</p>
        <Button disabled={!saveReady} onClick={onSave} loading={saving}>
          <Check className="h-4 w-4" />
          {editing ? '保存修改草稿' : '保存为产品草稿'}
        </Button>
      </div>
    </div>
  )
}

function ImportProductModal({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<'ai' | 'manual'>('ai')
  const [pastedText, setPastedText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [draft, setDraft] = useState<ProductImportDraft | null>(null)
  const [error, setError] = useState('')
  const [duplicateReason, setDuplicateReason] = useState('')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const queryClient = useQueryClient()
  const aiMutation = useMutation({
    mutationFn: () => api.productAiDraft(pastedText, files),
    onSuccess: setDraft,
    onError: (reason) => setError(reason instanceof Error ? reason.message : 'AI 整理失败'),
  })
  useEffect(() => {
    if (!aiMutation.isPending) {
      setElapsedSeconds(0)
      return
    }
    const startedAt = Date.now()
    const timer = window.setInterval(
      () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [aiMutation.isPending])
  const sourceLabel = useMemo(() => {
    if (files.length === 0) return '粘贴文本'
    const kinds = Array.from(new Set(files.map(productFileKind)))
    return kinds.length === 1 ? `${kinds[0]} 文件` : `${kinds.join('、')} 文件`
  }, [files])
  const progress = useMemo(() => {
    if (elapsedSeconds < 4) return { label: `正在接收${sourceLabel}`, detail: `系统正在读取${sourceLabel}，并检查能否提取文字。`, percent: 18 }
    if (elapsedSeconds < 12) return { label: '正在解析产品资料', detail: `正在整理${sourceLabel}中的文字、表格和来源位置。`, percent: 42 }
    if (elapsedSeconds < 45) return { label: '模型正在生成结构化草稿', detail: 'MiniMax 等推理模型可能需要几十秒完成长文档整理。', percent: 68 }
    return { label: '正在校验并修正字段', detail: '系统会用产品 Schema 校验结果；较长资料请继续等待。', percent: Math.min(90, 78 + Math.floor(elapsedSeconds / 15)) }
  }, [elapsedSeconds, sourceLabel])
  const saveMutation = useMutation({
    mutationFn: async () => {
      const revisionPayload = {
        payload: draft!.payload,
        search_text: draft!.search_text,
        source_uri: 'ui://product-import',
        verification_status: 'provisional',
      }
      const target = draft!.dedup?.matches.find((match) => match.item_id)
      if (draft!.dedup?.recommended_action === 'new_revision' && target?.item_id) {
        const revision = await api.createRegistryRevision('product', target.item_id, revisionPayload)
        await api.resolveIngestion(draft!.dedup.ingestion_id, {
          decision: 'new_revision',
          resulting_item_id: target.item_id,
          resulting_revision_id: revision.id,
        })
        return revision
      }
      const item = await api.createRegistryItem('product', {
        stable_key: draft!.stable_key,
        ...revisionPayload,
      })
      if (draft!.dedup)
        await api.resolveIngestion(draft!.dedup.ingestion_id, {
          decision: draft!.dedup.duplicate_status === 'none' ? 'new_item' : 'independent',
          decision_reason: duplicateReason,
          resulting_item_id: item.id,
          resulting_revision_id: item.revisions[0]?.id,
        })
      return item
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['registry', 'product'],
      })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '保存失败'),
  })

  const hasUnsavedChanges = productImportHasUnsavedChanges({
    pastedText,
    fileCount: files.length,
    draft,
    duplicateReason,
    pending: aiMutation.isPending || saveMutation.isPending,
  })
  useEffect(() => {
    if (!hasUnsavedChanges) return
    const guardNavigation = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', guardNavigation)
    return () => window.removeEventListener('beforeunload', guardNavigation)
  }, [hasUnsavedChanges])

  const requestClose = () => {
    if (
      hasUnsavedChanges
      && !window.confirm('还有未保存的产品资料。确定关闭并放弃本次填写内容吗？')
    ) return
    onClose()
  }

  const switchMode = (nextMode: 'ai' | 'manual') => {
    if (nextMode === mode) return
    if (
      hasUnsavedChanges
      && !window.confirm('切换录入方式会清空当前未保存内容，确定继续吗？')
    ) return
    setMode(nextMode)
    setDraft(nextMode === 'manual' ? structuredClone(emptyProduct) : null)
    setError('')
  }
  return (
    <Modal title="录入产品知识" description="先让 AI 整理资料，再由运营人员确认每个字段。点击窗口外不会关闭；有未保存内容时，关闭前会再次确认。" onClose={requestClose} wide>
      <div className="mb-6 flex rounded-2xl bg-slate-100 p-1">
        <button disabled={aiMutation.isPending} className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${mode === 'ai' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => switchMode('ai')}>
          <Sparkles className="mr-2 inline h-4 w-4" />
          AI 整理资料
        </button>
        <button disabled={aiMutation.isPending} className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${mode === 'manual' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => switchMode('manual')}>
          <FileSpreadsheet className="mr-2 inline h-4 w-4" />
          手动填写
        </button>
      </div>
      {mode === 'ai' && !draft ? (
        <div className="space-y-5">
          <Callout title="AI 只负责整理，不负责证明">上传内容中的“精准监测、疗愈、改善睡眠”等表达不会自动成为 Product Claim，仍需证据和 Reviewer 确认。</Callout>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
              <p className="text-xs font-bold text-emerald-800">优先上传</p>
              <p className="mt-2 text-xs leading-5 text-emerald-700">产品规格表、说明书、材料清单、功能确认表、型号信息。</p>
            </div>
            <div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4">
              <p className="text-xs font-bold text-blue-800">可以补充</p>
              <p className="mt-2 text-xs leading-5 text-blue-700">品牌定位、目标用户、设计故事，以及哪些信息仍是测试版本。</p>
            </div>
            <div className="rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
              <p className="text-xs font-bold text-amber-800">请明确标注</p>
              <p className="mt-2 text-xs leading-5 text-amber-700">未经确认的功能、供应商宣传、健康功效和图片上的营销用语。</p>
            </div>
          </div>
          <label className="block cursor-pointer rounded-3xl border-2 border-dashed border-brand-100 bg-brand-50/50 p-8 text-center transition hover:border-brand-500 hover:bg-brand-50">
            <UploadCloud className="mx-auto h-8 w-8 text-brand-600" />
            <p className="mt-3 text-sm font-bold text-brand-900">上传产品资料</p>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              支持 TXT/Markdown（每个 1MB）、PDF/Word（每个 15MB）、Excel XLSX（每个 8MB）；
              最多 8 个，总计不超过 25MB。
              <br />
              Excel 最多 20 个工作表、10 万个待扫描单元格；旧版 XLS 请先另存为 XLSX。
            </p>
            <input
              disabled={aiMutation.isPending}
              className="sr-only"
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx,.xlsx"
              onChange={(event) => {
                const selected = Array.from(event.target.files || [])
                const issue = validateProductFiles(selected)
                if (issue) {
                  setFiles([])
                  setError(issue)
                  event.currentTarget.value = ''
                  return
                }
                setError('')
                setFiles(selected)
              }}
            />
          </label>
          {files.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {files.map((file) => (
                <span key={`${file.name}-${file.size}`} className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700">
                  {file.name}
                </span>
              ))}
            </div>
          )}
          <TextAreaField disabled={aiMutation.isPending} label="告诉 AI 这批资料是什么" example={'产品：Paper Orbit NOTE01 点阵笔记本\n资料状态：测试版，功能尚待最终确认\n希望提取：型号、客观描述、功能、材料\n特别注意：健康和疗愈表述不可作为已证实事实'} hint="不需要写 Prompt。按“产品、资料状态、希望提取、特别注意”四项说明即可；也可以直接粘贴规格表文字。" value={pastedText} onChange={(event) => setPastedText(event.target.value)} />
          {aiMutation.isPending && (
            <div className="rounded-2xl border border-brand-100 bg-brand-50/70 p-4" aria-live="polite">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-bold text-brand-900">{progress.label}</p>
                  <p className="mt-1 text-xs leading-5 text-brand-800/75">{progress.detail}</p>
                </div>
                <span className="shrink-0 rounded-full bg-white px-3 py-1 text-xs font-semibold text-brand-700 shadow-sm">
                  {elapsedSeconds} 秒
                </span>
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-white">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-brand-500 to-blue-400 transition-all duration-700"
                  style={{ width: `${progress.percent}%` }}
                />
              </div>
              <p className="mt-2 text-[11px] text-slate-500">阶段为界面估算；请求完成后会自动显示可编辑草稿，请勿重复点击。</p>
            </div>
          )}
          {error && <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
          <div className="flex justify-end">
            <Button
              loading={aiMutation.isPending}
              disabled={!pastedText.trim() && files.length === 0}
              onClick={() => {
                setError('')
                aiMutation.mutate()
              }}
            >
              <Sparkles className="h-4 w-4" />
              生成可编辑草稿
            </Button>
          </div>
        </div>
      ) : draft ? (
        <ProductEditor
          draft={draft}
          onChange={setDraft}
          duplicateReason={duplicateReason}
          onDuplicateReasonChange={setDuplicateReason}
          saving={saveMutation.isPending}
          onSave={() => {
            setError('')
            saveMutation.mutate()
          }}
        />
      ) : null}
      {draft && error && <div className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
    </Modal>
  )
}

function EditProductModal({ product, onClose }: { product: RegistryItemDetail; onClose: () => void }) {
  const queryClient = useQueryClient()
  const current = product.revisions.find((revision) => revision.id === product.current_revision_id)
  const latest = [...product.revisions].sort((a, b) => b.version - a.version)[0]
  const existingDraft = product.revisions.find((revision) => revision.status === 'draft')
  const source = existingDraft || current || latest
  const [draft, setDraft] = useState<ProductImportDraft>({
    ...structuredClone(emptyProduct),
    stable_key: product.stable_key,
    payload: source?.payload as unknown as ProductPayload,
    search_text: source?.search_text || '',
  })
  const [error, setError] = useState('')
  const save = useMutation({
    mutationFn: () => {
      const revisionPayload = {
        payload: draft.payload,
        search_text: draft.search_text,
        source_uri: 'ui://product-edit',
        verification_status: 'provisional',
      }
      return existingDraft
        ? api.updateRegistryRevision('product', product.id, existingDraft.id, revisionPayload)
        : api.createRegistryRevision('product', product.id, revisionPayload)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['registry', 'product'] })
      onClose()
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '产品修改保存失败'),
  })
  return (
    <Modal title="编辑产品知识" description="修改会保存为新 Revision 草稿，不覆盖历史版本。" onClose={onClose} wide>
      <ProductEditor
        draft={draft}
        onChange={setDraft}
        saving={save.isPending}
        editing
        onSave={() => {
          setError('')
          save.mutate()
        }}
      />
      {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    </Modal>
  )
}

function ProductDetailModal({ product, media, canWrite, canDelete, onClose, onEdit, onArchive, onRestore, onDelete, actionBusy }: { product: RegistryItemDetail; media: ProductMedia[]; canWrite: boolean; canDelete: boolean; onClose: () => void; onEdit: () => void; onArchive: () => void; onRestore: () => void; onDelete: () => void; actionBusy: boolean }) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [altText, setAltText] = useState('')
  const [mediaError, setMediaError] = useState('')
  const upload = useMutation({
    mutationFn: () => api.uploadProductMedia(product.id, altText, file!, media.length === 0),
    onSuccess: async () => {
      setFile(null)
      setAltText('')
      await queryClient.invalidateQueries({ queryKey: ['product-media'] })
    },
    onError: (reason) => setMediaError(reason instanceof Error ? reason.message : '图片上传失败'),
  })
  const makePrimary = useMutation({
    mutationFn: api.makeProductMediaPrimary,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['product-media'] }),
    onError: (reason) => setMediaError(reason instanceof Error ? reason.message : '主图设置失败'),
  })
  const current = product.revisions.find((revision) => revision.id === product.current_revision_id)
  const latest = [...product.revisions].sort((a, b) => b.version - a.version)[0]
  const revision = current || latest
  const payload = revision?.payload as unknown as ProductPayload | undefined
  const primary = media.find((item) => item.is_primary) || media[0]
  return (
    <Modal title={payload?.name || '产品详情'} description={`Registry Key：${product.stable_key}`} onClose={onClose} wide>
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <div>
          <div className="overflow-hidden rounded-3xl bg-slate-100">
            {primary ? (
              <img src={primary.url} alt={primary.alt_text} className="aspect-square w-full object-cover" />
            ) : payload?.sku === 'NOTE01' ? (
              <img src={note01Image} alt={payload.name} className="aspect-square w-full object-cover" />
            ) : (
              <div className="flex aspect-square items-center justify-center">
                <Boxes className="h-14 w-14 text-brand-200" />
              </div>
            )}
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {media.map((item) => (
              <button key={item.id} className={`relative overflow-hidden rounded-xl border-2 ${item.is_primary ? 'border-brand-500' : 'border-transparent'}`} onClick={() => !item.is_primary && makePrimary.mutate(item.id)}>
                <img src={item.url} alt={item.alt_text} className="aspect-square w-full object-cover" />
                {item.is_primary && <span className="absolute bottom-1 left-1 rounded bg-brand-600 px-1.5 py-0.5 text-[9px] text-white">主图</span>}
              </button>
            ))}
          </div>
          {canWrite && (
            <div className="mt-4 space-y-3 rounded-2xl border border-dashed border-brand-200 bg-brand-50/50 p-3">
              <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-brand-700">
                <ImagePlus className="h-4 w-4" />
                {file ? file.name : '选择产品图片'}
                <input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] || null)} />
              </label>
              <input className="field-control py-2 text-xs" aria-label="图片说明" placeholder="图片说明，例如：NOTE01 蓝色款正面白底图" value={altText} onChange={(event) => setAltText(event.target.value)} />
              <Button
                className="w-full"
                variant="secondary"
                disabled={!file || !altText.trim()}
                loading={upload.isPending}
                onClick={() => {
                  setMediaError('')
                  upload.mutate()
                }}
              >
                上传到产品媒体库
              </Button>
              {mediaError && <p className="text-xs text-red-600">{mediaError}</p>}
            </div>
          )}
          <div className="mt-4 flex items-center justify-between">
            <StatusBadge status={current ? 'active' : 'draft'} />
            <span className="text-xs text-slate-500">当前展示 v{revision?.version || 1}</span>
          </div>
        </div>
        <div className="space-y-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-brand-600">客观描述</p>
            <p className="mt-2 text-sm leading-7 text-slate-600">{payload?.description || '尚未填写'}</p>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <div>
              <p className="text-xs font-bold text-slate-500">功能事实</p>
              <ul className="mt-2 space-y-2 text-sm text-slate-600">
                {payload?.features.map((item) => (
                  <li key={item} className="rounded-xl bg-brand-50 px-3 py-2">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-bold text-slate-500">材料事实</p>
              {payload?.materials.length ? (
                <ul className="mt-2 space-y-2 text-sm text-slate-600">
                  {payload.materials.map((item) => (
                    <li key={item} className="rounded-xl bg-slate-50 px-3 py-2">
                      {item}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-amber-700">尚无已整理材料信息</p>
              )}
            </div>
          </div>
          <Callout title="非医疗设备边界">{payload?.non_medical_disclaimer || '尚未填写'}</Callout>
          <div>
            <p className="text-xs font-bold text-slate-500">Revision 历史</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {[...product.revisions]
                .sort((a, b) => b.version - a.version)
                .map((item) => (
                  <span key={item.id} className="rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-600">
                    v{item.version} · {item.status}
                  </span>
                ))}
            </div>
          </div>
          <Callout title="Product Claim 单独治理">产品事实不等于宣传声明。与该产品关联的效果声明和证据将在“声明与证据”模块单独创建、核验和激活。</Callout>
          {canWrite && (
            <div className="flex flex-wrap justify-end gap-3 border-t border-slate-100 pt-5">
              {product.archived_at ? (
                <>
                  <Button variant="secondary" loading={actionBusy} onClick={onRestore}>
                    <RotateCcw className="h-4 w-4" />
                    恢复产品
                  </Button>
                  {canDelete && (
                    <Button variant="danger" loading={actionBusy} onClick={onDelete}>
                      永久删除
                    </Button>
                  )}
                </>
              ) : (
                <>
                  <Button variant="secondary" onClick={onEdit}>
                    <Pencil className="h-4 w-4" />
                    编辑并创建新版本
                  </Button>
                  <Button variant="danger" loading={actionBusy} onClick={onArchive}>
                    <Archive className="h-4 w-4" />
                    移入回收站
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

export function ProductsPage() {
  const [showImport, setShowImport] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<RegistryItemDetail | null>(null)
  const [editingProduct, setEditingProduct] = useState<RegistryItemDetail | null>(null)
  const { principal } = useAuth()
  const canWrite = principal?.role === 'admin' || principal?.role === 'editor'
  const canDelete = principal?.role === 'admin'
  const queryClient = useQueryClient()
  const itemsQuery = useQuery({
    queryKey: ['registry', 'product', 'all'],
    queryFn: () => api.listRegistry('product', true),
  })
  const mediaQuery = useQuery({
    queryKey: ['product-media'],
    queryFn: () => api.listProductMedia(),
  })
  const detailsQuery = useQuery({
    queryKey: ['registry', 'product', 'details', itemsQuery.data?.map((item) => item.updated_at).join(',')],
    queryFn: () => Promise.all((itemsQuery.data || []).map((item) => api.getRegistryItem('product', item.id))),
    enabled: !!itemsQuery.data,
  })
  const [activationError, setActivationError] = useState('')
  const activateMutation = useMutation({
    mutationFn: ({ itemId, revisionId }: { itemId: string; revisionId: string }) => api.activateRevision('product', itemId, revisionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['registry', 'product'] }),
    onError: (reason) => setActivationError(reason instanceof Error ? reason.message : '激活失败'),
  })
  const archiveMutation = useMutation({
    mutationFn: api.archiveRegistryItem.bind(null, 'product'),
    onSuccess: async () => {
      setSelectedProduct(null)
      await queryClient.invalidateQueries({ queryKey: ['registry', 'product'] })
    },
    onError: (reason) => setActivationError(reason instanceof Error ? reason.message : '产品删除失败'),
  })
  const restoreMutation = useMutation({
    mutationFn: api.restoreRegistryItem.bind(null, 'product'),
    onSuccess: async () => {
      setSelectedProduct(null)
      await queryClient.invalidateQueries({ queryKey: ['registry', 'product'] })
    },
    onError: (reason) => setActivationError(reason instanceof Error ? reason.message : '产品恢复失败'),
  })
  const deleteMutation = useMutation({
    mutationFn: api.permanentlyDeleteRegistryItem.bind(null, 'product'),
    onSuccess: async () => {
      setSelectedProduct(null)
      await queryClient.invalidateQueries({ queryKey: ['registry', 'product'] })
    },
    onError: (reason) => setActivationError(reason instanceof Error ? reason.message : '产品永久删除失败'),
  })
  const allProducts = useMemo(() => detailsQuery.data || [], [detailsQuery.data])
  const products = allProducts.filter((product) => (showArchived ? !!product.archived_at : !product.archived_at))
  if (itemsQuery.isLoading || detailsQuery.isLoading || mediaQuery.isLoading) return <LoadingBlock label="正在读取产品 Registry" />

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Product Registry"
        title="产品知识"
        description="把原始资料整理成可追溯、可审核的产品事实，避免未经确认的信息直接进入内容生成。"
        actions={
          canWrite ? (
            <Button onClick={() => setShowImport(true)}>
              <Plus className="h-4 w-4" />
              录入新产品
            </Button>
          ) : undefined
        }
      />
      <div className="mb-5 flex gap-2 rounded-2xl bg-slate-100 p-1">
        <button className={`rounded-xl px-4 py-2 text-sm font-semibold ${!showArchived ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => setShowArchived(false)}>
          当前产品（{allProducts.filter((item) => !item.archived_at).length}）
        </button>
        <button className={`rounded-xl px-4 py-2 text-sm font-semibold ${showArchived ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`} onClick={() => setShowArchived(true)}>
          回收站（{allProducts.filter((item) => !!item.archived_at).length}）
        </button>
      </div>
      {activationError && <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{activationError}</div>}
      {!products.length ? (
        <Card>
          <EmptyState
            icon={<Boxes className="h-6 w-6" />}
            title="还没有产品知识"
            description="上传产品规格书或粘贴资料，AI 会生成可编辑草稿；你也可以完全手动填写。"
            action={
              canWrite ? (
                <Button onClick={() => setShowImport(true)}>
                  <Sparkles className="h-4 w-4" />
                  创建第一个产品
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
          {products.map((product: RegistryItemDetail) => {
            const current = product.revisions.find((revision) => revision.id === product.current_revision_id)
            const latest = [...product.revisions].sort((a, b) => b.version - a.version)[0]
            const payload = (current || latest)?.payload as unknown as ProductPayload | undefined
            const primaryMedia = (mediaQuery.data || []).find((item) => item.product_item_id === product.id && item.is_primary)
            const draft = product.revisions.find((revision) => revision.status === 'draft')
            return (
              <Card
                key={product.id}
                className="group cursor-pointer overflow-hidden transition duration-200 hover:-translate-y-1 hover:shadow-lift"
                role="button"
                tabIndex={0}
                onClick={() => setSelectedProduct(product)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') setSelectedProduct(product)
                }}
              >
                <div className="relative h-48 overflow-hidden bg-gradient-to-br from-blue-50 to-slate-100">
                  {primaryMedia ? (
                    <img src={primaryMedia.url} alt={primaryMedia.alt_text} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
                  ) : payload?.sku === 'NOTE01' ? (
                    <img src={note01Image} alt="虚构文具示意图，不是商品实拍" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
                  ) : (
                    <div className="flex h-full items-center justify-center">
                      <Boxes className="h-12 w-12 text-brand-200" />
                    </div>
                  )}
                  <div className="absolute left-4 top-4">
                    <StatusBadge status={product.archived_at ? 'retired' : current ? 'active' : 'draft'} />
                  </div>
                  <div className="absolute bottom-3 right-3 rounded-full bg-white/90 px-3 py-1 text-xs font-bold text-brand-900 shadow">v{latest?.version || 1}</div>
                </div>
                <div className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-brand-600">{payload?.sku || product.stable_key}</p>
                      <h2 className="mt-1 text-lg font-bold text-graphite">{payload?.name || '未命名产品'}</h2>
                    </div>
                    <ChevronRight className="mt-1 h-5 w-5 text-slate-300" />
                  </div>
                  <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-500">{payload?.description}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {payload?.features.slice(0, 3).map((feature) => (
                      <span key={feature} className="rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-700">
                        {feature}
                      </span>
                    ))}
                  </div>
                  <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
                    <span className="flex items-center gap-1.5 text-xs text-slate-400">
                      <ShieldCheck className="h-4 w-4" />
                      {product.archived_at ? '已移出新 Brief 与 Run' : current ? '可进入新 Run 快照' : '尚未进入 Agent 上下文'}
                    </span>
                    {draft && (principal?.role === 'admin' || principal?.role === 'reviewer') && (
                      <Button
                        variant="secondary"
                        loading={activateMutation.isPending}
                        onClick={(event) => {
                          event.stopPropagation()
                          activateMutation.mutate({
                            itemId: product.id,
                            revisionId: draft.id,
                          })
                        }}
                      >
                        激活草稿
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
      <div className="mt-6 flex gap-3 rounded-2xl border border-amber-100 bg-amber-50/70 px-5 py-4 text-sm text-amber-900">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-semibold">Product 与 Product Claim 是不同资产</p>
          <p className="mt-1 text-xs leading-5 text-amber-800">“支持睡眠数据记录”可以是待核对功能事实；“改善睡眠”属于效果声明，需要证据和独立 Claim Revision。</p>
        </div>
      </div>
      {showImport && canWrite && <ImportProductModal onClose={() => setShowImport(false)} />}
      {editingProduct && <EditProductModal product={editingProduct} onClose={() => setEditingProduct(null)} />}
      {selectedProduct && !editingProduct && <ProductDetailModal product={selectedProduct} media={(mediaQuery.data || []).filter((item) => item.product_item_id === selectedProduct.id)} canWrite={!!canWrite} canDelete={!!canDelete} onClose={() => setSelectedProduct(null)} onEdit={() => setEditingProduct(selectedProduct)} onArchive={() => {
        if (window.confirm('产品会移入回收站，不再出现在新 Brief 中；历史 Run 与 Revision 会保留。是否继续？')) archiveMutation.mutate(selectedProduct.id)
      }} onRestore={() => restoreMutation.mutate(selectedProduct.id)} onDelete={() => {
        const payload = (selectedProduct.revisions.find((item) => item.id === selectedProduct.current_revision_id) || selectedProduct.revisions[0])?.payload as unknown as ProductPayload
        const confirmation = window.prompt(`永久删除不可恢复。请输入产品名称“${payload?.name || selectedProduct.stable_key}”确认：`)
        if (confirmation === (payload?.name || selectedProduct.stable_key)) deleteMutation.mutate(selectedProduct.id)
      }} actionBusy={archiveMutation.isPending || restoreMutation.isPending || deleteMutation.isPending} />}
    </div>
  )
}
