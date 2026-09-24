import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import { GuestOnly, RequireAdmin, RequireAuth } from './components/RouteGuards'
import { useAuth } from './context/AuthContext'
import Chat from './pages/Chat'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import { DocumentsPage, HistoryPage, NotFoundPage, ProfilePage } from './pages/StudentPages'
import { Spinner } from './components/ui'

// Admin screens load on demand: students never download them.
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'))
const AdminDocuments = lazy(() => import('./pages/admin/AdminDocuments'))
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers'))
const AdminAnalytics = lazy(() => import('./pages/admin/AdminAnalytics'))
const AdminFeedback = lazy(() =>
  import('./pages/admin/AdminFeedbackAudit').then((m) => ({ default: m.AdminFeedback })),
)
const AdminAuditLogs = lazy(() =>
  import('./pages/admin/AdminFeedbackAudit').then((m) => ({ default: m.AdminAuditLogs })),
)

function PageLoader() {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      <Spinner className="size-6" />
    </div>
  )
}

function HomeRedirect() {
  const { user, isAdmin, loading } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={isAdmin ? '/admin' : '/chat'} replace />
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
    <Routes>
      <Route path="/" element={<HomeRedirect />} />

      <Route element={<GuestOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/chat" element={<Chat />} />
          <Route path="/chat/:sessionId" element={<Chat />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/profile" element={<ProfilePage />} />

          <Route element={<RequireAdmin />}>
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/documents" element={<AdminDocuments />} />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/admin/analytics" element={<AdminAnalytics />} />
            <Route path="/admin/feedback" element={<AdminFeedback />} />
            <Route path="/admin/audit-logs" element={<AdminAuditLogs />} />
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
    </Suspense>
  )
}
