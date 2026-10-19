import { describe, expect, it } from 'vitest'
import { generateSecurePassword } from '../lib/password'

describe('user administration', () => {
  it('generates a strong temporary password accepted by the API policy', () => {
    const password = generateSecurePassword()

    expect(password.length).toBeGreaterThanOrEqual(12)
    expect(password).toMatch(/[A-Z]/)
    expect(password).toMatch(/[a-z]/)
    expect(password).toMatch(/[0-9]/)
    expect(password).toMatch(/[^A-Za-z0-9]/)
    expect(generateSecurePassword()).not.toBe(password)
  })
})
