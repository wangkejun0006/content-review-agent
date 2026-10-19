import { CircleHelp } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button, Modal } from './ui'

type PageHelp = {
  purpose: string
  steps: string[]
  terms?: Array<{ term: string; meaning: string }>
  caution?: string
}

const pageHelp: Record<string, PageHelp> = {
  '今天从哪一步开始？': {
    purpose: '从这里判断知识、内容、审核和反馈各处于什么阶段，再进入对应模块处理。',
    steps: ['先确认产品与声明资料是否完整', '创建 Brief 并启动 Run', '人工审核后登记发布与指标', '积累数据后运行 Feedback 分析'],
    terms: [{ term: 'Registry', meaning: '可版本化、可审核的品牌知识资产库。' }, { term: 'Run', meaning: '一次冻结知识版本后执行的内容生成流程。' }],
  },
  '产品知识': {
    purpose: '把规格书、说明文档和图片整理成 Agent 可引用的产品事实。',
    steps: ['上传或粘贴原始资料', '检查 AI 整理结果与缺失项', '保存草稿', '由 Reviewer 核实后激活 Revision'],
    terms: [{ term: 'Revision', meaning: '同一产品的一版不可变历史记录。' }, { term: 'Active', meaning: '当前可被后续 Run 读取的版本。' }],
    caution: 'AI 只负责整理，不会把未确认资料变成权威事实。',
  },
  '声明与证据': {
    purpose: '建立“原始证据 → 可说的 Claim → 禁止说法”的宣传边界。',
    steps: ['录入证据原文及来源', 'Reviewer 核验证据', '创建并关联 Product Claim', '审核并激活 Claim Revision'],
    terms: [{ term: 'Claim', meaning: '有证据支持、允许用于内容的产品声明。' }, { term: 'NFC', meaning: '近场通信（Near Field Communication）。' }],
    caution: 'AI 摘要不能替代证据原文，健康效果声明尤其需要可核验依据。',
  },
  '内容任务': {
    purpose: '用运营语言定义本次小红书内容目标，系统会冻结当前已激活的知识资产并启动正式内容流程。',
    steps: ['选择已激活产品', '填写目标、场景与核心信息', '保存 Brief', '启动 Run 生成候选'],
    terms: [{ term: 'Brief', meaning: '一次内容任务的目标、受众、场景和限制条件。' }, { term: 'CTA', meaning: '行动引导（Call to Action），如讨论、收藏或了解更多。' }, { term: 'Revision Snapshot', meaning: 'Run 启动时冻结的知识版本集合，保证后续可以追溯。' }],
  },
  '运行与审核': {
    purpose: '跟踪 Agent 流程状态，并进入运行详情比较、修改或批准候选内容。',
    steps: ['等待 Worker 完成生成', '查看候选的合规与评分', '由 Reviewer 作出人工决定', '批准后前往发布登记'],
    terms: [{ term: 'HITL', meaning: '人在回路（Human-in-the-loop），关键决策必须人工确认。' }, { term: 'Worker', meaning: '后台领取并执行长任务的进程。' }],
  },
  '运行详情': {
    purpose: '比较同一次 Run 的候选稿、合规报告和六维评分，并完成最终人工决策。',
    steps: ['确认运行状态和被冻结的 Registry 数量', '逐稿查看正文、视觉建议、Claim、合规与评分', '选择候选并批准、编辑、要求修改或拒绝', '批准后前往发布与数据'],
    terms: [{ term: 'Candidate', meaning: '同一 Brief 生成的一份候选内容包。' }, { term: 'Hook', meaning: '开头吸引力评分。' }, { term: 'SaveValue', meaning: '内容值得收藏的价值评分。' }, { term: 'Content Version', meaning: '每次自动或人工改写产生的不可覆盖版本。' }],
  },
  '发布与数据': {
    purpose: '把人工发布的小红书笔记关联到确定的内容版本，并持续录入累计指标。',
    steps: ['完成小红书人工发布', '登记平台内容 ID、链接和时间', '按时间点录入累计指标', '在增长反馈中使用这些快照'],
    terms: [{ term: 'Publication', meaning: '一次外部平台发布与内部内容版本的关联记录。' }, { term: 'Snapshot', meaning: '某个采集时刻的一组累计数据。' }],
  },
  '增长反馈': {
    purpose: '结合小红书表现、京东数据和归因证据，形成待审核的策略建议。',
    steps: ['录入京东累计快照', '建立可选归因证据', '选择发布记录运行 Feedback', 'Reviewer 激活有价值的 Strategy Insight'],
    terms: [{ term: 'GMV', meaning: '商品交易总额（Gross Merchandise Value）。' }, { term: 'SKU', meaning: '库存量单位，用于标识具体商品规格。' }, { term: 'Feedback', meaning: '基于已冻结指标生成的观察、假设与优化动作。' }],
    caution: '没有直接归因证据时，只能描述辅助归因或同期相关性。',
  },
  '平台规则': {
    purpose: '按平台维护 Compliance 使用的规则来源、适用范围和新鲜度。',
    steps: ['打开并阅读可信规则原文', '手动录入或由 AI 整理', '核对来源 URL 与验证时间', 'Reviewer 激活后供 Run 使用'],
    terms: [{ term: 'XHS', meaning: '小红书（Xiaohongshu）的项目内缩写。' }, { term: 'Compliance', meaning: '内容合规检查，包括确定性规则与语义审查。' }],
  },
  '模型设置': {
    purpose: '添加模型服务，并按不同 Agent 的能力需要绑定模型。',
    steps: ['添加 OpenAI-compatible 服务', '测试连通性', '为各 Agent 用途建立绑定', '通过 Token 用量检查实际消耗', '再启动真实 LLM 任务'],
    terms: [{ term: 'LLM', meaning: '大语言模型（Large Language Model）。' }, { term: 'Token', meaning: '模型处理文本的计量单位，分为输入和输出；不直接等同人民币费用。' }, { term: 'Base URL', meaning: '兼容接口的 API 根地址，通常以 /v1 结尾。' }, { term: 'API Key', meaning: '服务访问密钥，只在提交时发送并由后端加密保存。' }],
  },
  '系统运行': {
    purpose: '查看后台 Worker 与任务队列是否健康，并在确认问题已经排除后重新执行失败任务。',
    steps: ['确认 Worker 显示在线', '查看排队中和运行中的任务数量', '展开失败原因并先处理模型或资料问题', '由 Admin 或 Editor 点击重新执行'],
    terms: [{ term: 'Worker', meaning: '在后台领取并执行 LangGraph 长任务的独立进程。' }, { term: 'Heartbeat', meaning: 'Worker 定期写入数据库的在线信号；长时间未更新会判定离线。' }, { term: 'Retry', meaning: '从原任务入口重新排队，不会新建一条内容运行。' }],
    caution: '不要在故障尚未排除时反复重试；系统不会无限自动重试。',
  },
  '审计记录': {
    purpose: '让管理员追溯谁在什么时间修改、激活、审核或重试了关键资产。',
    steps: ['按操作人、动作或资源筛选', '展开记录查看结构化详情', '需要留档时导出当前筛选结果', '结合具体资源 ID 复核异常操作'],
    terms: [{ term: 'Audit Event', meaning: '业务操作成功时写入的不可直接编辑记录。' }, { term: 'Actor', meaning: '触发该操作的账号；系统任务可能没有操作人。' }],
    caution: '审计记录含内部资源标识与错误上下文，仅 Admin 可查看和导出。',
  },
  '用户管理': {
    purpose: '由系统管理员为获准使用当前品牌工作区的同事创建邀请制账号并分配角色。',
    steps: ['确认同事已获准访问服务网络', '填写姓名、工作邮箱和角色', '生成或设置独立初始密码', '创建后通过安全渠道转交一次性显示的登录信息'],
    terms: [{ term: 'Brand ID', meaning: '品牌工作区的唯一标识，用于隔离不同品牌的数据。单品牌模式下登录页会自动识别。' }, { term: 'Role', meaning: '账号角色，决定可调用的 API 和可执行的操作。' }],
    caution: 'Tailscale 网络访问权限与本系统账号是两层独立权限；同事需要同时具备两者。',
  },
}

export function PageHelpButton({ title, help }: { title: string; help?: PageHelp }) {
  const [open, setOpen] = useState(false)
  const content = help || pageHelp[title]
  if (!content) return null
  return <>
    <Button variant="ghost" className="shrink-0" onClick={() => setOpen(true)} aria-label={`查看${title}操作说明`}><CircleHelp className="h-4 w-4" />操作说明</Button>
    {open && <Modal title={`${title} · 操作说明`} description={content.purpose} onClose={() => setOpen(false)}>
      <div className="space-y-6">
        <section><h3 className="text-sm font-bold text-graphite">推荐操作顺序</h3><ol className="mt-3 space-y-3">{content.steps.map((step, index) => <li key={step} className="flex gap-3 text-sm leading-6 text-slate-600"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-700">{index + 1}</span><span>{step}</span></li>)}</ol></section>
        {!!content.terms?.length && <section><h3 className="text-sm font-bold text-graphite">缩写与术语</h3><dl className="mt-3 grid gap-3 sm:grid-cols-2">{content.terms.map(({ term, meaning }) => <div key={term} className="rounded-2xl border border-slate-100 bg-white p-4"><dt className="text-sm font-bold text-brand-700">{term}</dt><dd className="mt-1 text-xs leading-5 text-slate-500">{meaning}</dd></div>)}</dl></section>}
        {content.caution && <div className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">注意：{content.caution}</div>}
      </div>
    </Modal>}
  </>
}

export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow?: string
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <header className="mb-7 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
      <div>
        {eyebrow && <p className="text-xs font-bold uppercase tracking-[.18em] text-brand-600">{eyebrow}</p>}
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-graphite">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">{description}</p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-3"><PageHelpButton title={title} />{actions}</div>
    </header>
  )
}
