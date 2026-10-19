import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { OperationsStatus } from '../types'
import { OperationsOverview } from './OperationsPage'

const status: OperationsStatus = {
  checked_at: '2026-07-20T12:00:00Z',
  worker: {
    online: false,
    worker_id: 'worker-one',
    hostname: 'test-host',
    process_id: 123,
    status: 'idle',
    current_job_id: null,
    started_at: '2026-07-20T10:00:00Z',
    last_seen_at: '2026-07-20T11:00:00Z',
    stale_after_seconds: 20,
  },
  queue: { queued: 2, running: 1, waiting_human: 3, succeeded: 5, failed: 1 },
  failed_jobs: [],
}

describe('operations overview', () => {
  it('shows an actionable warning when the worker heartbeat is stale', () => {
    render(<OperationsOverview data={status} />)
    expect(screen.getByText('后台 Worker 当前离线')).toBeInTheDocument()
    expect(screen.getByText(/runtime-restart/)).toBeInTheDocument()
    expect(screen.getByText('排队中')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })
})
