import clsx from 'clsx'
import { AlertCircle, CheckCircle2, LoaderCircle, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  PropsWithChildren,
  ReactNode,
  TextareaHTMLAttributes,
} from 'react'

export function Card({ children, className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={clsx('glass-panel rounded-[20px]', className)} {...props}>{children}</section>
}

export function Button({
  className,
  variant = 'primary',
  loading,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  loading?: boolean
}) {
  return (
    <button
      className={clsx(
        'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition duration-200 focus:outline-none focus:ring-4 disabled:cursor-not-allowed disabled:opacity-50',
        variant === 'primary' &&
          'bg-brand-600 text-white shadow-lg shadow-brand-600/20 hover:-translate-y-0.5 hover:bg-brand-700 hover:shadow-lift focus:ring-brand-100',
        variant === 'secondary' &&
          'border border-brand-100 bg-brand-50 text-brand-700 hover:border-brand-500 hover:bg-white focus:ring-brand-100',
        variant === 'danger' &&
          'bg-red-50 text-red-700 hover:bg-red-100 focus:ring-red-100',
        variant === 'ghost' && 'text-slate-600 hover:bg-slate-100 focus:ring-slate-100',
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

export function Field({
  label,
  example,
  hint,
  error,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string
  example?: string
  hint?: string
  error?: string
}) {
  return (
    <label className={clsx('block space-y-2', className)}>
      <span className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-graphite">{label}</span>
        {example && <span className="text-xs text-slate-400">示例：{example}</span>}
      </span>
      <input
        className={clsx('field-control', error && 'border-red-300')}
        aria-label={props['aria-label'] || label}
        {...props}
      />
      {(hint || error) && (
        <span className={clsx('block text-xs', error ? 'text-red-600' : 'text-slate-500')}>
          {error || hint}
        </span>
      )}
    </label>
  )
}

export function TextAreaField({
  label,
  example,
  hint,
  error,
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string
  example?: string
  hint?: string
  error?: string
}) {
  return (
    <label className={clsx('block space-y-2', className)}>
      <span className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-graphite">{label}</span>
        {example && <span className="text-xs text-slate-400">示例：{example}</span>}
      </span>
      <textarea
        className={clsx('field-control min-h-28 resize-y', error && 'border-red-300')}
        aria-label={props['aria-label'] || label}
        {...props}
      />
      {(hint || error) && (
        <span className={clsx('block text-xs', error ? 'text-red-600' : 'text-slate-500')}>
          {error || hint}
        </span>
      )}
    </label>
  )
}

const statusStyles: Record<string, string> = {
  active: 'bg-emerald-50 text-emerald-700 ring-emerald-600/15',
  draft: 'bg-amber-50 text-amber-700 ring-amber-600/15',
  provisional: 'bg-violet-50 text-violet-700 ring-violet-600/15',
  retired: 'bg-slate-100 text-slate-600 ring-slate-500/10',
  queued: 'bg-blue-50 text-blue-700 ring-blue-600/15',
  running: 'bg-violet-50 text-violet-700 ring-violet-600/15',
  succeeded: 'bg-emerald-50 text-emerald-700 ring-emerald-600/15',
  waiting_human: 'bg-amber-50 text-amber-700 ring-amber-600/15',
  waiting_knowledge_review: 'bg-red-50 text-red-700 ring-red-600/15',
  ready_for_manual_publish: 'bg-emerald-50 text-emerald-700 ring-emerald-600/15',
  rejected: 'bg-slate-100 text-slate-700 ring-slate-500/10',
  failed: 'bg-red-50 text-red-700 ring-red-600/15',
}

const statusLabels: Record<string, string> = {
  active: '已生效',
  draft: '草稿',
  provisional: '待复核',
  retired: '已停用',
  queued: '排队中',
  running: '生成中',
  succeeded: '已完成',
  waiting_human: '等待人工审核',
  waiting_knowledge_review: '规则待复核',
  content_draft_ready: '草稿已完成',
  ready_for_manual_publish: '可手动发布',
  rejected: '已拒绝',
  failed: '运行失败',
  phase1_ready: '基础流程完成',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset',
        statusStyles[status] || 'bg-slate-100 text-slate-600 ring-slate-500/10',
      )}
    >
      {statusLabels[status] || status}
    </span>
  )
}

export function Callout({
  title,
  children,
  tone = 'info',
}: PropsWithChildren<{ title: string; tone?: 'info' | 'warning' | 'success' }>) {
  const Icon = tone === 'success' ? CheckCircle2 : AlertCircle
  return (
    <div
      className={clsx(
        'flex gap-3 rounded-2xl border px-4 py-3 text-sm',
        tone === 'info' && 'border-blue-100 bg-blue-50/70 text-blue-900',
        tone === 'warning' && 'border-red-100 bg-red-50/70 text-red-900',
        tone === 'success' && 'border-emerald-100 bg-emerald-50/70 text-emerald-900',
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p className="font-semibold">{title}</p>
        <div className="mt-1 text-xs leading-5 opacity-80">{children}</div>
      </div>
    </div>
  )
}

export function EmptyState({ icon, title, description, action }: {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-4 rounded-2xl bg-brand-50 p-3 text-brand-600">{icon}</div>
      <h3 className="font-semibold text-graphite">{title}</h3>
      <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Modal({ title, description, onClose, children, wide = false, closeOnBackdrop = false }: PropsWithChildren<{
  title: string
  description?: string
  onClose: () => void
  wide?: boolean
  closeOnBackdrop?: boolean
}>) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    scrollRef.current?.focus({ preventScroll: true })
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [])
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-slate-950/35 p-3 backdrop-blur-sm sm:p-8" role="dialog" aria-modal="true" onMouseDown={(event) => { if (closeOnBackdrop && event.target === event.currentTarget) onCloseRef.current() }}>
      <div className={clsx('modal-panel flex w-full min-h-0 flex-col overflow-hidden rounded-3xl bg-pearl shadow-2xl animate-fade-up', wide ? 'max-w-5xl' : 'max-w-2xl')}>
        <header className="z-10 flex shrink-0 items-start justify-between border-b border-slate-100 bg-white/95 px-6 py-5 backdrop-blur">
          <div>
            <h2 className="text-xl font-bold text-graphite">{title}</h2>
            {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
          </div>
          <Button variant="ghost" className="h-10 w-10 p-0" onClick={() => onCloseRef.current()} aria-label="关闭">
            <X className="h-5 w-5" />
          </Button>
        </header>
        <div ref={scrollRef} data-testid="modal-scroll-area" tabIndex={-1} className="scroll-soft min-h-0 flex-1 overflow-y-auto overscroll-contain p-6 outline-none">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

export function LoadingBlock({ label = '正在加载' }: { label?: string }) {
  return (
    <div className="flex min-h-44 items-center justify-center gap-3 text-sm text-slate-500">
      <LoaderCircle className="h-5 w-5 animate-spin text-brand-600" />
      {label}
    </div>
  )
}
