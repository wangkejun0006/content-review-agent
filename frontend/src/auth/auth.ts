import type { Principal } from '../types'

export function decodePrincipal(token: string): Principal | null {
  try {
    const encodedPayload = token.split('.')[1]
    if (!encodedPayload) return null
    const normalizedPayload = encodedPayload.replace(/-/g, '+').replace(/_/g, '/')
    const paddedPayload = normalizedPayload.padEnd(
      normalizedPayload.length + ((4 - (normalizedPayload.length % 4)) % 4),
      '=',
    )
    const payload = JSON.parse(
      decodeURIComponent(
        atob(paddedPayload)
          .split('')
          .map((character) => `%${character.charCodeAt(0).toString(16).padStart(2, '0')}`)
          .join(''),
      ),
    ) as Record<string, string>
    if (
      !payload.sub ||
      !payload.brand_id ||
      !payload.email ||
      !['admin', 'editor', 'reviewer'].includes(payload.role)
    ) return null
    return {
      userId: payload.sub,
      brandId: payload.brand_id,
      role: payload.role as Principal['role'],
      email: payload.email,
    }
  } catch {
    return null
  }
}
