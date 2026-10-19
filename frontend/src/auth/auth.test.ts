import { describe, expect, it } from 'vitest'
import { decodePrincipal } from './auth'

function jwt(payload: Record<string, string>) {
  const encode = (value: object) => btoa(JSON.stringify(value))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
  return `${encode({ alg: 'none' })}.${encode(payload)}.signature`
}

describe('decodePrincipal', () => {
  it('decodes a valid application principal', () => {
    expect(decodePrincipal(jwt({
      sub: 'user-1',
      brand_id: 'brand-1',
      role: 'reviewer',
      email: 'reviewer@example.com',
    }))).toEqual({
      userId: 'user-1',
      brandId: 'brand-1',
      role: 'reviewer',
      email: 'reviewer@example.com',
    })
  })

  it('rejects malformed tokens and unsupported roles', () => {
    expect(decodePrincipal('not-a-token')).toBeNull()
    expect(decodePrincipal(jwt({
      sub: 'user-1',
      brand_id: 'brand-1',
      role: 'viewer',
      email: 'viewer@example.com',
    }))).toBeNull()
  })
})
