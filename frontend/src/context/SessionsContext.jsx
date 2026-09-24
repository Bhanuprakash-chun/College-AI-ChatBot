import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from './AuthContext'

// Shared list of the signed-in user's chat sessions, so the sidebar and the
// chat page stay in sync when a conversation is created, renamed or deleted.
const SessionsContext = createContext(null)

export function SessionsProvider({ children }) {
  const { user } = useAuth()
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setError(null)
    try {
      setSessions(await api.sessions())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    if (user) refresh()
    else setSessions([])
  }, [user, refresh])

  const remove = useCallback(async (id) => {
    await api.deleteSession(id)
    setSessions((list) => list.filter((s) => s.id !== id))
  }, [])

  // Optimistically place a session at the top after a new message.
  const touch = useCallback((session) => {
    setSessions((list) => {
      const rest = list.filter((s) => s.id !== session.id)
      const existing = list.find((s) => s.id === session.id)
      return [{ ...existing, ...session }, ...rest]
    })
  }, [])

  const value = useMemo(
    () => ({ sessions, loading, error, refresh, remove, touch }),
    [sessions, loading, error, refresh, remove, touch],
  )
  return <SessionsContext.Provider value={value}>{children}</SessionsContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSessions() {
  const ctx = useContext(SessionsContext)
  if (!ctx) throw new Error('useSessions must be used inside <SessionsProvider>')
  return ctx
}
