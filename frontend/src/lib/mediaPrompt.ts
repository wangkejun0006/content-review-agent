import type { ContentCandidate } from '../types'

export function buildMediaProductionPrompt(candidate: ContentCandidate): string {
  const { media_plan: plan, visual_brief: visual } = candidate.payload
  const lines = [
    plan.preferred_generation_prompt,
    `内容形式：${plan.preferred_format === 'video' ? '竖屏短视频' : '小红书图片组'}；画幅：${plan.aspect_ratio}`,
    plan.duration_seconds ? `建议时长：${plan.duration_seconds} 秒` : '',
    `封面：${visual.cover_concept}；封面文字：${visual.cover_text}`,
    `场景：${visual.scene}`,
    plan.image_sequence.length ? `图片顺序：${plan.image_sequence.join('；')}` : '',
    plan.shot_list.length ? `镜头：${plan.shot_list.join('；')}` : `镜头：${visual.shot_list.join('；')}`,
    plan.on_screen_text.length ? `画面文字：${plan.on_screen_text.join('；')}` : '',
    plan.voiceover ? `旁白：${plan.voiceover}` : '',
    plan.shooting_notes.length ? `制作说明：${plan.shooting_notes.join('；')}` : '',
    plan.negative_prompts.length ? `禁止出现：${plan.negative_prompts.join('；')}` : '',
    '保持产品外观、材质和文字与参考资料一致，不增加未经证实的健康功效、参数或医疗暗示。',
  ]
  return lines.filter(Boolean).join('\n')
}
