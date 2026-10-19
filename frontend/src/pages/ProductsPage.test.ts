import { describe, expect, it } from 'vitest'
import type { ProductImportDraft } from '../types'
import { productImportHasUnsavedChanges } from '../lib/productImport'

const untouchedDraft: ProductImportDraft = {
  stable_key: '',
  payload: {
    name: '', sku: '', product_type: 'stationery', description: '',
    features: [], materials: [], non_medical_disclaimer: '消费级电子产品，不属于医疗设备。',
  },
  search_text: '', field_confidence: {}, missing_fields: [], warnings: [], source_summaries: [],
}

describe('product import data-loss guard', () => {
  it('does not warn for a newly opened untouched manual form', () => {
    expect(productImportHasUnsavedChanges({
      pastedText: '', fileCount: 0, draft: untouchedDraft, duplicateReason: '', pending: false,
    })).toBe(false)
  })

  it('detects text, files, generated edits and requests in progress', () => {
    expect(productImportHasUnsavedChanges({
      pastedText: '产品规格', fileCount: 0, draft: null, duplicateReason: '', pending: false,
    })).toBe(true)
    expect(productImportHasUnsavedChanges({
      pastedText: '', fileCount: 1, draft: null, duplicateReason: '', pending: false,
    })).toBe(true)
    expect(productImportHasUnsavedChanges({
      pastedText: '', fileCount: 0,
      draft: { ...untouchedDraft, stable_key: 'paper-orbit-note01' },
      duplicateReason: '', pending: false,
    })).toBe(true)
    expect(productImportHasUnsavedChanges({
      pastedText: '', fileCount: 0, draft: null, duplicateReason: '', pending: true,
    })).toBe(true)
  })
})
