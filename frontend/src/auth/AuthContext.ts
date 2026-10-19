import { createContext, useContext } from 'react'
import type { Principal } from '../types'

export interface AuthValue {
  principal: Principal | null
  signIn: (token: string) => void
  signOut: () => void
}

export const AuthContext = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthContext is missing')
  return value
}
