import type { ProductImportDraft } from '../types'

const untouchedProductDraft: ProductImportDraft = {
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

export function productImportHasUnsavedChanges({
  pastedText,
  fileCount,
  draft,
  duplicateReason,
  pending,
}: {
  pastedText: string
  fileCount: number
  draft: ProductImportDraft | null
  duplicateReason: string
  pending: boolean
}) {
  return Boolean(
    pending
      || pastedText.trim()
      || fileCount
      || duplicateReason.trim()
      || (draft && JSON.stringify(draft) !== JSON.stringify(untouchedProductDraft)),
  )
}
