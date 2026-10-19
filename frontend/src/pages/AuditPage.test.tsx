import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AuditEventRows } from './AuditPage'

describe('audit event rows', () => {
  it('renders actor, localized action and structured details', () => {
    render(<AuditEventRows events={[{
      id: 'event-1', actor_id: 'user-1', actor_email: 'admin@example.com', actor_display_name: '管理员',
      action: 'job.manually_retried', resource_type: 'growth_run', resource_id: 'run-1',
      details: { manual_retries: 1 }, created_at: '2026-07-20T12:00:00Z',
    }]} />)
    expect(screen.getByText('重新执行失败任务')).toBeInTheDocument()
    expect(screen.getByText('admin@example.com')).toBeInTheDocument()
    expect(screen.getByText(/manual_retries/)).toBeInTheDocument()
  })
})
