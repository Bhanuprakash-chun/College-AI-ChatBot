import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, onUnauthorized, tokenStore } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(() => Boolean(tokenStore.get()))

  const clearSession = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  // Any 401 from an authenticated call means the token expired or was revoked.
  useEffect(() => {
    onUnauthorized(clearSession)
    return () => onUnauthorized(null)
  }, [clearSession])

  // Restore the session on first load if a token is present.
  useEffect(() => {
    if (!tokenStore.get()) return
    let cancelled = false
    api
      .me()
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        if (!cancelled) clearSession()
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [clearSession])

  const login = useCallback(async (email, password) => {
    const result = await api.login(email, password)
    tokenStore.set(result.access_token)
    setUser(result.user)
    return result.user
  }, [])

  const register = useCallback(async (payload) => {
    const result = await api.register(payload)
    tokenStore.set(result.access_token)
    setUser(result.user)
    return result.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      /* the token is discarded regardless */
    }
    clearSession()
  }, [clearSession])

  const value = useMemo(
    () => ({
      user,
      loading,
      isAdmin: user?.role === 'admin',
      login,
      register,
      logout,
    }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
