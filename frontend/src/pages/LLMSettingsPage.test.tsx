import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import type { LLMUsageReport } from '../types'
import { UsageModal } from './LLMSettingsPage'

const report: LLMUsageReport = {
  requested_days: 30,
  period_start: '2026-06-20T00:00:00Z',
  period_end: '2026-07-20T00:00:00Z',
  totals: {
    calls: 4,
    successful_calls: 3,
    failed_calls: 1,
    input_tokens: 1200,
    output_tokens: 800,
    total_tokens: 2000,
    unreported_token_calls: 1,
    average_latency_ms: 1500,
  },
  by_provider: [{
    provider: 'Primary', model: 'model-a', calls: 4, successful_calls: 3,
    failed_calls: 1, input_tokens: 1200, output_tokens: 800, total_tokens: 2000,
    unreported_token_calls: 1, average_latency_ms: 1500,
  }],
  by_purpose: [{
    purpose: 'xhs_writer', calls: 4, successful_calls: 3, failed_calls: 1,
    input_tokens: 1200, output_tokens: 800, total_tokens: 2000,
    unreported_token_calls: 1, average_latency_ms: 1500,
  }],
}

describe('LLM usage modal', () => {
  it('shows provider-reported totals and can change the reporting period', async () => {
    const usage = vi.spyOn(api, 'getLLMUsage').mockResolvedValue(report)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <UsageModal onClose={vi.fn()} />
      </QueryClientProvider>,
    )

    expect((await screen.findAllByText('2,000')).length).toBeGreaterThan(0)
    expect(screen.getByText('Primary')).toBeInTheDocument()
    expect(screen.getByText('XHS Writer Agent')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '近 7 天' }))
    await waitFor(() => expect(usage).toHaveBeenCalledWith(7))
    usage.mockRestore()
  })
})
