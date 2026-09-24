import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Spinner } from './ui'

function FullPageLoader() {
  return (
    <div className="flex h-full items-center justify-center text-slate-500">
      <Spinner className="size-6" />
    </div>
  )
}

// Any signed-in user.
export function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullPageLoader />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

// Admin role only. The API enforces this too; this guard only avoids
// showing students a page whose every request would be rejected.
export function RequireAdmin() {
  const { user, loading, isAdmin } = useAuth()
  if (loading) return <FullPageLoader />
  if (!user) return <Navigate to="/login" replace />
  if (!isAdmin) return <Navigate to="/chat" replace />
  return <Outlet />
}

// Login/register: bounce signed-in users to their home page.
export function GuestOnly() {
  const { user, loading, isAdmin } = useAuth()
  if (loading) return <FullPageLoader />
  if (user) return <Navigate to={isAdmin ? '/admin' : '/chat'} replace />
  return <Outlet />
}
