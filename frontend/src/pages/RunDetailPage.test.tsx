import { describe, expect, it } from 'vitest'

import type { ContentCandidate } from '../types'
import { buildMediaProductionPrompt } from '../lib/mediaPrompt'

describe('buildMediaProductionPrompt', () => {
  it('expands the selected candidate from structured fields without another LLM call', () => {
    const candidate = {
      payload: {
        media_plan: {
          preferred_format: 'image_set',
          preferred_generation_prompt: '蓝色科技美学产品静物图',
          aspect_ratio: '3:4',
          duration_seconds: null,
          image_sequence: ['封面', '材质细节'],
          shot_list: [],
          on_screen_text: ['科技美学手链'],
          voiceover: '',
          shooting_notes: ['使用自然侧光'],
          negative_prompts: ['医疗器械画面'],
        },
        visual_brief: {
          cover_concept: '蓝色桌面静物',
          cover_text: '科技美学手链',
          scene: '日常桌面',
          shot_list: ['产品全景'],
        },
      },
    } as unknown as ContentCandidate

    const prompt = buildMediaProductionPrompt(candidate)
    expect(prompt).toContain('图片顺序：封面；材质细节')
    expect(prompt).toContain('镜头：产品全景')
    expect(prompt).toContain('禁止出现：医疗器械画面')
    expect(prompt).toContain('不增加未经证实的健康功效')
  })
})
