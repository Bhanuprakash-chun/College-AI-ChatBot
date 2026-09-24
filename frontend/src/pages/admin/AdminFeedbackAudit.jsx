import { useCallback, useEffect, useState } from 'react'
import { ClipboardList, MessageSquareText, ThumbsDown, ThumbsUp } from 'lucide-react'
import Markdown from '../../components/Markdown'
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  PageHeader,
  Pagination,
  Spinner,
  inputClass,
} from '../../components/ui'
import { api } from '../../lib/api'
import { describeAction, formatDateTime } from '../../lib/format'

// ---------------------------------------------------------------- Feedback

export function AdminFeedback() {
  const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 10 })
  const [page, setPage] = useState(1)
  const [rating, setRating] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api.adminFeedback({ page, page_size: 10, rating: rating || undefined }))
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [page, rating])

  useEffect(() => {
    load()
  }, [load])

  const filters = [
    { value: '', label: 'All' },
    { value: 'down', label: 'Not helpful' },
    { value: 'up', label: 'Helpful' },
  ]

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader title="Feedback" description="Student ratings on assistant answers. Unhelpful answers often point to missing or unclear documents." />

      <div className="mb-4 flex gap-2" role="group" aria-label="Filter by rating">
        {filters.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={rating === f.value}
            onClick={() => {
              setRating(f.value)
              setPage(1)
            }}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              rating === f.value
                ? 'border-brand-600 bg-brand-600 text-white'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <Alert>{error}</Alert>}

      <Card className="overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-16 text-slate-400">
            <Spinner className="size-6" />
          </div>
        ) : data.items.length === 0 ? (
          <EmptyState icon={MessageSquareText} title="No feedback yet">
            Ratings appear here when students use the thumbs up or down buttons.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.items.map((item) => {
              const open = expanded === item.id
              return (
                <li key={item.id} className="p-4">
                  <div className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 rounded-lg p-1.5 ${
                        item.rating === 'up'
                          ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400'
                          : 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400'
                      }`}
                    >
                      {item.rating === 'up' ? <ThumbsUp className="size-4" /> : <ThumbsDown className="size-4" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                        <Badge value={item.rating} label={item.rating === 'up' ? 'Helpful' : 'Not helpful'} />
                        <span>{item.user_email}</span>
                        <span>·</span>
                        <span>{formatDateTime(item.created_at)}</span>
                        {!item.grounded && <Badge value="processing" label="Not found in documents" className="!bg-amber-100" />}
                      </div>
                      <p className="mt-2 text-sm font-medium text-slate-900 dark:text-white">Q: {item.question || '(question unavailable)'}</p>
                      {item.comment && (
                        <p className="mt-1 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700 italic dark:bg-slate-800/60 dark:text-slate-300">
                          “{item.comment}”
                        </p>
                      )}
                      <button
                        type="button"
                        onClick={() => setExpanded(open ? null : item.id)}
                        className="mt-2 text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
                        aria-expanded={open}
                      >
                        {open ? 'Hide answer' : 'Show answer'}
                      </button>
                      {open && (
                        <div className="mt-2 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
                          <Markdown>{item.answer}</Markdown>
                          <p className="mt-2 text-xs text-slate-400">Top match score {(item.top_similarity * 100).toFixed(0)}%</p>
                        </div>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
      </Card>
    </div>
  )
}

// -------------------------------------------------------------- Audit logs

const ACTIONS = [
  'auth.login',
  'auth.login_failed',
  'auth.logout',
  'auth.register',
  'document.upload',
  'document.processed',
  'document.failed',
  'document.delete',
  'document.reprocess',
  'user.update',
  'user.delete',
  'chat.question',
  'chat.session_delete',
  'feedback.submit',
]

const SECURITY_ACTIONS = new Set(['auth.login_failed', 'document.failed', 'user.delete', 'document.delete'])

export function AdminAuditLogs() {
  const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 25 })
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api.auditLogs({ page, page_size: 25, action: action || undefined }))
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [page, action])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader
        title="Audit logs"
        description="Sign-ins, document changes, user management and other security-relevant events."
        actions={
          <select
            className={`${inputClass} w-auto`}
            value={action}
            onChange={(e) => {
              setAction(e.target.value)
              setPage(1)
            }}
            aria-label="Filter by action"
          >
            <option value="">All actions</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        }
      />

      {error && <Alert>{error}</Alert>}

      <Card className="overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-16 text-slate-400">
            <Spinner className="size-6" />
          </div>
        ) : data.items.length === 0 ? (
          <EmptyState icon={ClipboardList} title="No log entries" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/60 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2.5 font-medium sm:px-4">Time</th>
                  <th className="px-3 py-2.5 font-medium sm:px-4">Actor</th>
                  <th className="px-3 py-2.5 font-medium sm:px-4">Action</th>
                  <th className="hidden px-4 py-2.5 font-medium md:table-cell">Target</th>
                  <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Detail</th>
                  <th className="hidden px-4 py-2.5 font-medium xl:table-cell">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.items.map((e) => (
                  <tr key={e.id} className="align-top">
                    <td className="px-3 py-2.5 text-xs text-slate-500 tabular-nums sm:px-4 sm:whitespace-nowrap">{formatDateTime(e.created_at)}</td>
                    <td className="px-3 py-2.5 break-all text-slate-700 sm:px-4 dark:text-slate-300">{e.actor_email || 'System'}</td>
                    <td className="px-3 py-2.5 sm:px-4">
                      <span
                        className={`rounded px-1.5 py-0.5 font-mono text-xs break-all ${
                          SECURITY_ACTIONS.has(e.action)
                            ? 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300'
                            : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                        }`}
                        title={describeAction(e.action)}
                      >
                        {e.action}
                      </span>
                    </td>
                    <td className="hidden px-4 py-2.5 text-xs text-slate-500 md:table-cell">
                      {e.target_type ? `${e.target_type} #${e.target_id ?? '—'}` : '—'}
                    </td>
                    <td className="hidden max-w-sm px-4 py-2.5 text-xs break-words text-slate-500 lg:table-cell">{e.detail || '—'}</td>
                    <td className="hidden px-4 py-2.5 font-mono text-xs text-slate-400 xl:table-cell">{e.ip_address || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
      </Card>
    </div>
  )
}
