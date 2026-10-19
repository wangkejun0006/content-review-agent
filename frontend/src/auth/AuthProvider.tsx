import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type PropsWithChildren } from 'react'
import { AUTH_EXPIRED_EVENT, tokenStore } from '../lib/api'
import type { Principal } from '../types'
import { decodePrincipal } from './auth'
import { AuthContext } from './AuthContext'

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient()
  const [principal, setPrincipal] = useState<Principal | null>(() => {
    const token = tokenStore.get()
    return token ? decodePrincipal(token) : null
  })

  useEffect(() => {
    const handleExpired = () => {
      queryClient.clear()
      setPrincipal(null)
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired)
  }, [queryClient])

  const value = useMemo(
    () => ({
      principal,
      signIn: (token: string) => {
        queryClient.clear()
        tokenStore.set(token)
        setPrincipal(decodePrincipal(token))
      },
      signOut: () => {
        queryClient.clear()
        tokenStore.clear()
        setPrincipal(null)
      },
    }),
    [principal, queryClient],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
