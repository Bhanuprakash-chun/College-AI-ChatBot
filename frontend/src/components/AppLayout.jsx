import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  BarChart3,
  ClipboardList,
  FileText,
  GraduationCap,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  MessageSquarePlus,
  Moon,
  Sun,
  ThumbsUp,
  Trash2,
  User,
  Users,
  X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useSessions } from '../context/SessionsContext'
import { useTheme } from '../context/ThemeContext'
import { useToast } from '../context/ToastContext'
import { timeAgo } from '../lib/format'
import { ConfirmDialog } from './ui'

const STUDENT_NAV = [
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/history', label: 'History', icon: History },
  { to: '/documents', label: 'Documents', icon: FileText },
]

const ADMIN_NAV = [
  { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/admin/documents', label: 'Manage documents', icon: FileText },
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/admin/feedback', label: 'Feedback', icon: ThumbsUp },
  { to: '/admin/audit-logs', label: 'Audit logs', icon: ClipboardList },
]

function NavItem({ to, label, icon: Icon, end, onNavigate }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
          isActive
            ? 'bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300'
            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
        }`
      }
    >
      <Icon className="size-4 shrink-0" />
      {label}
    </NavLink>
  )
}

function RecentChats({ onNavigate }) {
  const { sessions, remove } = useSessions()
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const confirmDelete = async () => {
    setDeleting(true)
    try {
      await remove(pendingDelete.id)
      toast.success('Conversation deleted.')
      if (String(pendingDelete.id) === sessionId) navigate('/chat')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  if (!sessions.length) {
    return <p className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">No conversations yet.</p>
  }

  return (
    <>
      <ul className="space-y-0.5">
        {sessions.slice(0, 30).map((s) => {
          const active = String(s.id) === sessionId
          return (
            <li key={s.id} className="group relative">
              <Link
                to={`/chat/${s.id}`}
                onClick={onNavigate}
                className={`block rounded-lg py-2 pr-8 pl-3 text-sm transition ${
                  active
                    ? 'bg-slate-200/70 text-slate-900 dark:bg-slate-800 dark:text-white'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/60'
                }`}
              >
                <span className="block truncate">{s.title}</span>
                <span className="block text-[11px] text-slate-400 dark:text-slate-500">{timeAgo(s.updated_at)}</span>
              </Link>
              <button
                type="button"
                onClick={() => setPendingDelete(s)}
                className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-md p-1.5 text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-slate-200 hover:text-red-600 focus:opacity-100 dark:hover:bg-slate-700"
                aria-label={`Delete conversation ${s.title}`}
              >
                <Trash2 className="size-3.5" />
              </button>
            </li>
          )
        })}
      </ul>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete conversation?"
        message={`"${pendingDelete?.title}" and all its messages will be permanently deleted.`}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        loading={deleting}
      />
    </>
  )
}

function SidebarContent({ onNavigate }) {
  const { user, isAdmin, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const location = useLocation()
  const navigate = useNavigate()
  const inChat = location.pathname.startsWith('/chat')

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-4 pt-5 pb-4">
        <div className="flex size-9 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
          <GraduationCap className="size-5" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-slate-900 dark:text-white">College AI</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">Assistant</p>
        </div>
      </div>

      <div className="px-3">
        <Link
          to="/chat"
          onClick={onNavigate}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          <MessageSquarePlus className="size-4" />
          New chat
        </Link>
      </div>

      <nav className="scroll-thin mt-4 flex-1 space-y-6 overflow-y-auto px-3 pb-4">
        <div className="space-y-0.5">
          {STUDENT_NAV.map((item) => (
            <NavItem key={item.to} {...item} onNavigate={onNavigate} />
          ))}
        </div>

        {isAdmin && (
          <div>
            <p className="mb-1.5 px-3 text-[11px] font-semibold tracking-wider text-slate-400 uppercase dark:text-slate-500">
              Administration
            </p>
            <div className="space-y-0.5">
              {ADMIN_NAV.map((item) => (
                <NavItem key={item.to} {...item} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        )}

        {inChat && (
          <div>
            <p className="mb-1.5 px-3 text-[11px] font-semibold tracking-wider text-slate-400 uppercase dark:text-slate-500">
              Recent conversations
            </p>
            <RecentChats onNavigate={onNavigate} />
          </div>
        )}
      </nav>

      <div className="border-t border-slate-200 p-3 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Link
            to="/profile"
            onClick={onNavigate}
            className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-700 dark:bg-slate-700 dark:text-slate-200">
              {user?.full_name?.charAt(0)?.toUpperCase() || <User className="size-4" />}
            </div>
            <div className="min-w-0 leading-tight">
              <p className="truncate text-sm font-medium text-slate-900 dark:text-white">{user?.full_name}</p>
              <p className="truncate text-xs text-slate-500 capitalize dark:text-slate-400">{user?.role}</p>
            </div>
          </Link>
          <button
            type="button"
            onClick={toggle}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          >
            {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-red-600 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Log out"
            title="Log out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  // Close the drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-white lg:block dark:border-slate-800 dark:bg-slate-900">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-950/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85%] bg-white shadow-xl dark:bg-slate-900">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute top-4 right-3 rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Close menu"
            >
              <X className="size-5" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 lg:hidden dark:border-slate-800 dark:bg-slate-900">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="-ml-1 rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>
          <div className="flex items-center gap-2">
            <GraduationCap className="size-5 text-brand-600" />
            <span className="text-sm font-semibold">College AI Assistant</span>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
