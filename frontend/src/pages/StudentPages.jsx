import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Building2,
  CalendarRange,
  FileText,
  History as HistoryIcon,
  Mail,
  MessageSquare,
  Search,
  Shield,
  Trash2,
} from 'lucide-react'
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  PageHeader,
  Spinner,
  inputClass,
} from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useSessions } from '../context/SessionsContext'
import { useToast } from '../context/ToastContext'
import { api } from '../lib/api'
import { formatDate, formatDateTime, timeAgo, titleCase } from '../lib/format'

function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

// ---------------------------------------------------------------- History

export function HistoryPage() {
  const toast = useToast()
  const { refresh: refreshSidebar, remove } = useSessions()
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search)
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setSessions(await api.sessions(debounced.trim() || undefined))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [debounced])

  useEffect(() => {
    load()
  }, [load])

  const confirmDelete = async () => {
    setDeleting(true)
    try {
      await remove(pendingDelete.id)
      setSessions((list) => list.filter((s) => s.id !== pendingDelete.id))
      toast.success('Conversation deleted.')
      refreshSidebar()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader title="Chat history" description="Search, reopen or delete your past conversations." />

      <div className="relative mb-4">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search conversations and messages…"
          className={`${inputClass} pl-9`}
          aria-label="Search conversations"
        />
      </div>

      {error && <Alert>{error}</Alert>}

      <Card>
        {loading ? (
          <div className="flex justify-center py-14 text-slate-400">
            <Spinner className="size-6" />
          </div>
        ) : sessions.length === 0 ? (
          <EmptyState
            icon={HistoryIcon}
            title={debounced ? 'No matching conversations' : 'No conversations yet'}
            action={
              !debounced && (
                <Link to="/chat">
                  <Button>
                    <MessageSquare className="size-4" /> Start a chat
                  </Button>
                </Link>
              )
            }
          >
            {debounced ? 'Try a different search term.' : 'Your questions and answers will appear here.'}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-slate-200 dark:divide-slate-800">
            {sessions.map((s) => (
              <li key={s.id} className="group flex items-center gap-3 px-4 py-3.5 hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">
                  <MessageSquare className="size-4" />
                </div>
                <Link to={`/chat/${s.id}`} className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900 dark:text-white">{s.title}</p>
                  <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                    {s.preview || 'Empty conversation'}
                  </p>
                </Link>
                <div className="hidden shrink-0 text-right text-xs text-slate-500 sm:block dark:text-slate-400">
                  <p>{timeAgo(s.updated_at)}</p>
                  <p>{Math.ceil(s.message_count / 2)} question{s.message_count > 2 ? 's' : ''}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setPendingDelete(s)}
                  className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                  aria-label={`Delete ${s.title}`}
                >
                  <Trash2 className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete conversation?"
        message={`"${pendingDelete?.title}" and all its messages will be permanently deleted.`}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        loading={deleting}
      />
    </div>
  )
}

// -------------------------------------------------------------- Documents

export function DocumentsPage() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [department, setDepartment] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .documents()
      .then((data) => !cancelled && setDocuments(data))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const departments = useMemo(
    () => [...new Set(documents.map((d) => d.department))].sort(),
    [documents],
  )
  const visible = department ? documents.filter((d) => d.department === department) : documents

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader
        title="College documents"
        description="The official documents the assistant answers from. If a topic isn't covered here, the assistant will say so."
        actions={
          departments.length > 1 && (
            <select
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className={`${inputClass} w-auto`}
              aria-label="Filter by department"
            >
              <option value="">All departments</option>
              {departments.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          )
        }
      />

      {error && <Alert>{error}</Alert>}

      {loading ? (
        <div className="flex justify-center py-16 text-slate-400">
          <Spinner className="size-6" />
        </div>
      ) : visible.length === 0 ? (
        <Card>
          <EmptyState icon={FileText} title="No documents available yet">
            An administrator hasn't published any college documents. The assistant can't answer
            questions until documents are uploaded.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((doc) => (
            <Card key={doc.id} className="flex flex-col p-5">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div className="flex size-10 items-center justify-center rounded-xl bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400">
                  <FileText className="size-5" />
                </div>
                <Badge value="student" label={titleCase(doc.document_type)} />
              </div>
              <h3 className="font-semibold text-slate-900 dark:text-white">{doc.title}</h3>
              <div className="mt-3 space-y-1.5 text-xs text-slate-500 dark:text-slate-400">
                <p className="flex items-center gap-1.5">
                  <Building2 className="size-3.5" /> {doc.department}
                </p>
                {doc.academic_year && (
                  <p className="flex items-center gap-1.5">
                    <CalendarRange className="size-3.5" /> Academic year {doc.academic_year}
                  </p>
                )}
                <p className="flex items-center gap-1.5">
                  <FileText className="size-3.5" /> {doc.page_count} page{doc.page_count === 1 ? '' : 's'} · added{' '}
                  {formatDate(doc.created_at)}
                </p>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- Profile

export function ProfilePage() {
  const { user, logout } = useAuth()
  const { sessions } = useSessions()
  const questionCount = sessions.reduce((sum, s) => sum + Math.ceil((s.message_count || 0) / 2), 0)

  const rows = [
    { icon: Mail, label: 'Email', value: user.email },
    { icon: Shield, label: 'Role', value: <Badge value={user.role} label={titleCase(user.role)} /> },
    { icon: Building2, label: 'Department', value: user.department || '—' },
    { icon: CalendarRange, label: 'Member since', value: formatDate(user.created_at) },
    { icon: HistoryIcon, label: 'Last sign-in', value: formatDateTime(user.last_login_at) },
  ]

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader title="Profile" />
      <Card className="overflow-hidden">
        <div className="flex items-center gap-4 border-b border-slate-200 bg-gradient-to-r from-brand-50 to-white p-6 dark:border-slate-800 dark:from-brand-500/10 dark:to-slate-900">
          <div className="flex size-16 items-center justify-center rounded-full bg-brand-600 text-2xl font-semibold text-white">
            {user.full_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h2 className="text-lg font-semibold">{user.full_name}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {sessions.length} conversation{sessions.length === 1 ? '' : 's'} · {questionCount} question
              {questionCount === 1 ? '' : 's'} asked
            </p>
          </div>
        </div>
        <dl className="divide-y divide-slate-200 dark:divide-slate-800">
          {rows.map(({ icon: Icon, label, value }) => (
            <div key={label} className="flex items-center justify-between gap-4 px-6 py-3.5 text-sm">
              <dt className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
                <Icon className="size-4" /> {label}
              </dt>
              <dd className="text-right font-medium text-slate-900 dark:text-white">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="border-t border-slate-200 px-6 py-4 dark:border-slate-800">
          <Button variant="secondary" onClick={logout}>
            Sign out
          </Button>
        </div>
      </Card>
    </div>
  )
}

export function NotFoundPage() {
  return (
    <div className="flex h-full items-center justify-center px-4">
      <EmptyState
        icon={Search}
        title="Page not found"
        action={
          <Link to="/chat">
            <Button>Go to chat</Button>
          </Link>
        }
      >
        The page you're looking for doesn't exist.
      </EmptyState>
    </div>
  )
}
