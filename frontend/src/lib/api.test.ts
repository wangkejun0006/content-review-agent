import { describe, expect, it, vi } from 'vitest'
import { AUTH_EXPIRED_EVENT, tokenStore } from './api'

describe('tokenStore', () => {
  it('expires a stale login and leaves a one-time user notice', () => {
    const listener = vi.fn()
    window.addEventListener(AUTH_EXPIRED_EVENT, listener)
    tokenStore.set('stale-token')

    tokenStore.expire()

    expect(tokenStore.get()).toBeNull()
    expect(listener).toHaveBeenCalledOnce()
    expect(tokenStore.getNotice()).toContain('重新登录')
    tokenStore.clearNotice()
    expect(tokenStore.getNotice()).toBeNull()
    window.removeEventListener(AUTH_EXPIRED_EVENT, listener)
  })
})
