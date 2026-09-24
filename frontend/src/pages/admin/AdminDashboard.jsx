import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertOctagon,
  ArrowRight,
  Boxes,
  Cpu,
  Database,
  FileText,
  Loader,
  MessageCircleQuestion,
  RefreshCw,
  Users,
} from 'lucide-react'
import { Meter, StatTile } from '../../components/charts'
import { Alert, Button, Card, PageHeader, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { describeAction, timeAgo } from '../../lib/format'

function HealthRow({ icon: Icon, label, ok, warn, detail }) {
  const state = ok ? 'Operational' : warn ? 'Degraded' : 'Unavailable'
  const dot = ok ? 'bg-emerald-500' : warn ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-start gap-3 py-3">
      <Icon className="mt-0.5 size-4 shrink-0 text-slate-400" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-slate-900 dark:text-white">{label}</p>
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300">
            <span className={`size-2 rounded-full ${dot}`} aria-hidden="true" />
            {state}
          </span>
        </div>
        {detail && <p className="mt-0.5 text-xs break-words text-slate-500 dark:text-slate-400">{detail}</p>}
      </div>
    </div>
  )
}


export default function AdminDashboard() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [recent, setRecent] = useState([])
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const [s, h, logs] = await Promise.all([
        api.statistics(),
        api.health(),
        api.auditLogs({ page_size: 8 }),
      ])
      setStats(s)
      setHealth(h)
      setRecent(logs.items)
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Keep polling while anything is still being indexed.
  useEffect(() => {
    if (!stats?.documents_processing) return
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [stats?.documents_processing, load])

  if (!stats && !error) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        <Spinner className="size-6" />
      </div>
    )
  }

  const llm = health?.llm
  const llmOk = llm?.available && llm?.model_pulled

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader
        title="Admin dashboard"
        description="Live counts from the database, vector store and language model."
        actions={
          <Button variant="secondary" onClick={load} loading={refreshing}>
            {!refreshing && <RefreshCw className="size-4" />} Refresh
          </Button>
        }
      />

      {error && (
        <div className="mb-4">
          <Alert>{error}</Alert>
        </div>
      )}

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <StatTile
              label="Users"
              value={stats.total_users}
              sub={`${stats.total_students} students · ${stats.total_admins} admins`}
              icon={Users}
            />
            <StatTile label="Documents" value={stats.total_documents} sub={`${stats.documents_ready} ready`} icon={FileText} />
            <StatTile label="Chunks" value={stats.total_chunks} sub="indexed in ChromaDB" icon={Boxes} />
            <StatTile label="Questions" value={stats.total_questions} sub={`${stats.total_sessions} conversations`} icon={MessageCircleQuestion} />
            <StatTile label="Active users" value={stats.active_users_7d} sub="last 7 days" icon={Activity} />
            <StatTile
              label="Processing"
              value={stats.documents_processing}
              sub={stats.documents_processing ? 'indexing now' : 'queue empty'}
              icon={Loader}
              status={stats.documents_processing ? 'warning' : undefined}
            />
            <StatTile
              label="Failed documents"
              value={stats.documents_failed}
              sub={stats.documents_failed ? 'needs attention' : 'none'}
              icon={AlertOctagon}
              status={stats.documents_failed ? 'critical' : undefined}
            />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-1">
              <h2 className="text-sm font-semibold">Answer quality</h2>
              <div className="mt-4 space-y-5">
                <Meter
                  label="Answered from documents"
                  value={stats.grounded_rate}
                  caption={`${stats.grounded_answers} grounded answers · ${stats.fallback_answers} refused as not found`}
                />
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <p className="text-xs text-slate-500 dark:text-slate-400">Helpful ratings</p>
                    <p className="mt-1 text-lg font-semibold">{stats.feedback_up}</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <p className="text-xs text-slate-500 dark:text-slate-400">Unhelpful ratings</p>
                    <p className="mt-1 text-lg font-semibold">{stats.feedback_down}</p>
                  </div>
                </div>
                <Link
                  to="/admin/analytics"
                  className="inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:underline dark:text-brand-400"
                >
                  View analytics <ArrowRight className="size-3.5" />
                </Link>
              </div>
            </Card>

            <Card className="p-5">
              <h2 className="text-sm font-semibold">System health</h2>
              <div className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
                <HealthRow
                  icon={Database}
                  label={`Database (${health?.database?.backend || 'unknown'})`}
                  ok={health?.database?.connected && !health?.database?.fallback_reason}
                  warn={health?.database?.connected && health?.database?.fallback_reason}
                  detail={
                    health?.database?.fallback_reason
                      ? `Running on SQLite fallback — ${health.database.fallback_reason}`
                      : null
                  }
                />
                <HealthRow
                  icon={Boxes}
                  label="Vector store (ChromaDB)"
                  ok={health?.vector_store?.connected}
                  detail={
                    health?.vector_store?.connected
                      ? `${health.vector_store.indexed_chunks} chunks indexed`
                      : health?.vector_store?.error
                  }
                />
                <HealthRow
                  icon={Cpu}
                  label={`Language model (${llm?.model || 'Ollama'})`}
                  ok={llmOk}
                  warn={llm?.available && !llm?.model_pulled}
                  detail={
                    llmOk
                      ? 'Ollama is running and the model is pulled.'
                      : llm?.detail || 'Ollama is not reachable. Answers fall back to document excerpts.'
                  }
                />
              </div>
              {health?.rag_config && (
                <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  Retrieval: top {health.rag_config.top_k} chunks · similarity threshold{' '}
                  {health.rag_config.similarity_threshold} · {health.rag_config.embedding_model}
                </p>
              )}
            </Card>

            <Card className="p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Recent activity</h2>
                <Link to="/admin/audit-logs" className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400">
                  All logs
                </Link>
              </div>
              {recent.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-500">No activity yet.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {recent.map((entry) => (
                    <li key={entry.id} className="flex items-start justify-between gap-3 text-sm">
                      <p className="min-w-0 text-slate-700 dark:text-slate-300">
                        <span className="font-medium text-slate-900 dark:text-white">
                          {entry.actor_email || 'System'}
                        </span>{' '}
                        {describeAction(entry.action)}
                      </p>
                      <span className="shrink-0 text-xs text-slate-400">{timeAgo(entry.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            {[
              { to: '/admin/documents', title: 'Manage documents', text: 'Upload, reprocess or remove college PDFs.', icon: FileText },
              { to: '/admin/users', title: 'Manage users', text: 'Roles, access and account status.', icon: Users },
              { to: '/admin/feedback', title: 'Review feedback', text: 'See which answers students rated down.', icon: MessageCircleQuestion },
            ].map(({ to, title, text, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="group flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-brand-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-700"
              >
                <Icon className="mt-0.5 size-5 text-brand-600 dark:text-brand-400" />
                <div>
                  <p className="text-sm font-semibold">{title}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{text}</p>
                </div>
                <ArrowRight className="ml-auto size-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand-500" />
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
