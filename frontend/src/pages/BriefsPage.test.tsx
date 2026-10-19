import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { CampaignBrief, RegistryItemDetail } from '../types'
import { BriefDetailModal } from './BriefsPage'

const brief: CampaignBrief = {
  id: '11111111-1111-4111-8111-111111111111',
  brand_id: '22222222-2222-4222-8222-222222222222',
  name: '雅典娜戒指内容测试',
  objective: '验证日常趋势观察内容方向',
  product_item_ids: ['33333333-3333-4333-8333-333333333333'],
  audience_item_ids: [],
  constraints: {
    key_message: '数据仅供个人趋势参考',
    scenario: '通勤与睡眠趋势观察',
    required_points: ['消费级健康设备'],
    forbidden_points: ['诊断和治疗功效'],
    tone: ['克制', '生活化'],
    cta_type: 'discussion',
    body_length: 600,
    candidate_count: 3,
    marketing_support_policy: 'evaluate',
    marketing_objective: 'content_validation',
    marketing_budget_min: null,
    marketing_budget_max: null,
  },
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T01:00:00Z',
  archived_at: null,
}

const product: RegistryItemDetail = {
  id: '33333333-3333-4333-8333-333333333333',
  brand_id: brief.brand_id,
  registry_type: 'product',
  stable_key: 'athena-ring',
  current_revision_id: '44444444-4444-4444-8444-444444444444',
  archived_at: null,
  created_at: brief.created_at,
  updated_at: brief.updated_at,
  revisions: [
    {
      id: '44444444-4444-4444-8444-444444444444',
      item_id: '33333333-3333-4333-8333-333333333333',
      version: 1,
      status: 'active',
      verification_status: 'provisional',
      payload: {
        name: 'QK-LFE-19 雅典娜女性桌面收纳夹',
        sku: 'QK-LFE-19',
        product_type: 'desk_accessory',
        description: '消费级桌面收纳夹',
        features: [],
        materials: [],
        non_medical_disclaimer: '不属于医疗设备',
      },
      search_text: '',
      source_uri: null,
      created_at: brief.created_at,
      activated_at: brief.updated_at,
    },
  ],
}

describe('Brief detail', () => {
  it('shows a read-only operational summary without opening the edit form', () => {
    const onClose = vi.fn()
    render(<BriefDetailModal brief={brief} products={[product]} onClose={onClose} />)

    expect(screen.getByRole('heading', { name: brief.name })).toBeInTheDocument()
    expect(screen.getByText('QK-LFE-19 雅典娜女性桌面收纳夹')).toBeInTheDocument()
    expect(screen.getByText(brief.objective)).toBeInTheDocument()
    expect(screen.getByText('数据仅供个人趋势参考')).toBeInTheDocument()
    expect(screen.getByText('由 Strategy 评估')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '保存修改' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
