import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Button, Field, Modal, StatusBadge } from './ui'

describe('shared UI components', () => {
  it('shows Chinese workflow status labels', () => {
    render(<StatusBadge status="waiting_human" />)
    expect(screen.getByText('等待人工审核')).toBeInTheDocument()
  })

  it('connects field guidance and errors to the visible form control', () => {
    render(<Field label="产品名称" example="Paper Orbit NOTE01" error="请填写产品名称" />)
    expect(screen.getByLabelText('产品名称')).toBeInTheDocument()
    expect(screen.getByText('示例：Paper Orbit NOTE01')).toBeInTheDocument()
    expect(screen.getByText('请填写产品名称')).toBeInTheDocument()
  })

  it('prevents duplicate action while loading', () => {
    render(<Button loading>保存草稿</Button>)
    expect(screen.getByRole('button', { name: '保存草稿' })).toBeDisabled()
  })

  it('uses a cross-browser internal scroll area and ignores accidental backdrop clicks', () => {
    const onClose = vi.fn()
    render(<Modal title="长表单" onClose={onClose}><div>表单正文</div></Modal>)
    const dialog = screen.getByRole('dialog')
    const panel = dialog.firstElementChild
    const scrollArea = screen.getByTestId('modal-scroll-area')
    expect(dialog.parentElement).toBe(document.body)
    expect(dialog).toHaveClass('items-center', 'overflow-hidden')
    expect(panel).toHaveClass('modal-panel', 'flex', 'min-h-0', 'overflow-hidden')
    expect(scrollArea).toHaveClass('min-h-0', 'flex-1', 'overflow-y-auto', 'overscroll-contain')
    fireEvent.mouseDown(dialog)
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('can explicitly opt into backdrop dismissal for non-editing dialogs', () => {
    const onClose = vi.fn()
    render(<Modal title="提示" onClose={onClose} closeOnBackdrop><div>内容</div></Modal>)
    fireEvent.mouseDown(screen.getByRole('dialog'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not steal focus when a controlled text field changes the close callback', () => {
    function ControlledModal() {
      const [value, setValue] = useState('')
      return <Modal title="录入资料" onClose={() => void value}>
        <textarea aria-label="资料说明" value={value} onChange={(event) => setValue(event.target.value)} />
      </Modal>
    }
    render(<ControlledModal />)
    const textarea = screen.getByLabelText('资料说明')
    textarea.focus()
    fireEvent.change(textarea, { target: { value: '产品规格' } })
    expect(textarea).toHaveFocus()
    expect(textarea).toHaveValue('产品规格')
  })
})
