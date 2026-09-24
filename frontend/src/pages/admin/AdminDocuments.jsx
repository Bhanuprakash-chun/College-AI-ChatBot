import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  FileText,
  RefreshCw,
  Search,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react'
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  PageHeader,
  Pagination,
  Spinner,
  inputClass,
} from '../../components/ui'
import { useToast } from '../../context/ToastContext'
import { api } from '../../lib/api'
import { formatBytes, formatDateTime, titleCase } from '../../lib/format'

const DOCUMENT_TYPES = ['policy', 'circular', 'syllabus', 'handbook', 'notice', 'report', 'other']
const MAX_MB = 25

function UploadCard({ onUploaded }) {
  const toast = useToast()
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [form, setForm] = useState({ title: '', department: 'General', document_type: 'policy', academic_year: '' })
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)

  const pick = (candidate) => {
    setError(null)
    if (!candidate) return
    if (!candidate.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files can be uploaded.')
      return
    }
    if (candidate.size > MAX_MB * 1024 * 1024) {
      setError(`That file is ${formatBytes(candidate.size)}. The limit is ${MAX_MB} MB.`)
      return
    }
    if (candidate.size === 0) {
      setError('That file is empty.')
      return
    }
    setFile(candidate)
    if (!form.title) {
      const guess = candidate.name.replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ').trim()
      setForm((f) => ({ ...f, title: guess.charAt(0).toUpperCase() + guess.slice(1) }))
    }
  }

  const reset = () => {
    setFile(null)
    setForm({ title: '', department: 'General', document_type: 'policy', academic_year: '' })
    if (inputRef.current) inputRef.current.value = ''
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!file) return
    setUploading(true)
    setError(null)
    const data = new FormData()
    data.append('file', file)
    Object.entries(form).forEach(([k, v]) => data.append(k, v))
    try {
      const doc = await api.uploadDocument(data)
      toast.success(`"${doc.title}" uploaded. Indexing has started.`)
      reset()
      onUploaded(doc)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold">Upload a document</h2>
      <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
        PDF up to {MAX_MB} MB. Text is extracted, split into chunks, embedded and indexed automatically.
      </p>

      <form onSubmit={submit} className="mt-4 space-y-4">
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            pick(e.dataTransfer.files?.[0])
          }}
          className={`relative rounded-xl border-2 border-dashed p-5 text-center transition ${
            dragging
              ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10'
              : 'border-slate-300 hover:border-slate-400 dark:border-slate-700 dark:hover:border-slate-600'
          }`}
        >
          {file ? (
            <div className="flex items-center gap-3 text-left">
              <FileText className="size-8 shrink-0 text-red-500" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
              </div>
              <button type="button" onClick={reset} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Remove file">
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <>
              <UploadCloud className="mx-auto size-8 text-slate-400" />
              <p className="mt-2 text-sm">
                <button type="button" onClick={() => inputRef.current?.click()} className="font-medium text-brand-600 hover:underline dark:text-brand-400">
                  Choose a PDF
                </button>{' '}
                or drag it here
              </p>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={(e) => pick(e.target.files?.[0])}
            aria-label="PDF file"
          />
        </div>

        {error && <Alert>{error}</Alert>}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Title" htmlFor="doc-title">
            <input id="doc-title" className={inputClass} value={form.title} maxLength={255} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Attendance Policy" />
          </Field>
          <Field label="Department" htmlFor="doc-dept">
            <input id="doc-dept" className={inputClass} value={form.department} maxLength={100} onChange={(e) => setForm({ ...form, department: e.target.value })} />
          </Field>
          <Field label="Document type" htmlFor="doc-type">
            <select id="doc-type" className={inputClass} value={form.document_type} onChange={(e) => setForm({ ...form, document_type: e.target.value })}>
              {DOCUMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Academic year" htmlFor="doc-year">
            <input id="doc-year" className={inputClass} value={form.academic_year} maxLength={20} onChange={(e) => setForm({ ...form, academic_year: e.target.value })} placeholder="e.g. 2025-26" />
          </Field>
        </div>

        <Button type="submit" disabled={!file} loading={uploading} className="w-full sm:w-auto">
          {!uploading && <UploadCloud className="size-4" />} Upload and index
        </Button>
      </form>
    </Card>
  )
}

export default function AdminDocuments() {
  const toast = useToast()
  const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 10 })
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true)
      try {
        const result = await api.adminDocuments({
          page,
          page_size: 10,
          status: status || undefined,
          search: debouncedSearch.trim() || undefined,
        })
        setData(result)
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    },
    [page, status, debouncedSearch],
  )

  useEffect(() => {
    load()
  }, [load])

  // Poll quietly while any listed document is still processing.
  const anyProcessing = data.items.some((d) => d.status === 'processing')
  useEffect(() => {
    if (!anyProcessing) return
    const t = setInterval(() => load(true), 2500)
    return () => clearInterval(t)
  }, [anyProcessing, load])

  const reprocess = async (doc) => {
    setBusyId(doc.id)
    try {
      await api.reprocessDocument(doc.id)
      toast.info(`Re-indexing "${doc.title}".`)
      load(true)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const confirmDelete = async () => {
    const doc = pendingDelete
    setBusyId(doc.id)
    try {
      const res = await api.deleteDocument(doc.id)
      toast.success(res.message)
      setPendingDelete(null)
      load(true)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader
        title="Manage documents"
        description="Only documents marked Ready are searchable by the assistant."
      />

      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        <div>
          <UploadCard
            onUploaded={() => {
              setPage(1)
              load(true)
            }}
          />
        </div>

        <Card className="min-w-0 overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row dark:border-slate-800">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                className={`${inputClass} pl-9`}
                placeholder="Search by title or file name…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                aria-label="Search documents"
              />
            </div>
            <select
              className={`${inputClass} sm:w-44`}
              value={status}
              onChange={(e) => {
                setStatus(e.target.value)
                setPage(1)
              }}
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              <option value="ready">Ready</option>
              <option value="processing">Processing</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {error && (
            <div className="p-4">
              <Alert>{error}</Alert>
            </div>
          )}

          {loading ? (
            <div className="flex justify-center py-16 text-slate-400">
              <Spinner className="size-6" />
            </div>
          ) : data.items.length === 0 ? (
            <EmptyState icon={FileText} title="No documents found">
              {status || debouncedSearch ? 'Try clearing the filters.' : 'Upload the first college PDF to get started.'}
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/60 dark:text-slate-400">
                  <tr>
                    <th className="px-3 sm:px-4 py-2.5 font-medium">Document</th>
                    <th className="px-3 sm:px-4 py-2.5 font-medium">Status</th>
                    <th className="hidden px-3 sm:px-4 py-2.5 text-right font-medium md:table-cell">Pages</th>
                    <th className="hidden px-3 sm:px-4 py-2.5 text-right font-medium md:table-cell">Chunks</th>
                    <th className="hidden px-3 sm:px-4 py-2.5 font-medium lg:table-cell">Uploaded</th>
                    <th className="px-3 sm:px-4 py-2.5 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.items.map((doc) => (
                    <tr key={doc.id} className="align-top">
                      <td className="max-w-[12rem] px-3 sm:px-4 py-3 sm:max-w-sm lg:max-w-md">
                        <p className="font-medium text-slate-900 dark:text-white">{doc.title}</p>
                        <p className="mt-0.5 text-xs break-words text-slate-500 dark:text-slate-400">
                          {doc.department} · {titleCase(doc.document_type)}
                          {doc.academic_year && ` · ${doc.academic_year}`} · {formatBytes(doc.file_size)}
                        </p>
                        <p className="mt-0.5 truncate text-xs text-slate-400" title={doc.original_filename}>
                          {doc.original_filename}
                        </p>
                        {doc.status === 'failed' && doc.error_message && (
                          <p className="mt-1.5 flex items-start gap-1 text-xs text-red-600 dark:text-red-400">
                            <AlertCircle className="mt-0.5 size-3.5 shrink-0" /> {doc.error_message}
                          </p>
                        )}
                      </td>
                      <td className="px-3 sm:px-4 py-3">
                        <Badge value={doc.status} label={titleCase(doc.status)} />
                        {doc.status === 'ready' && doc.processing_seconds != null && (
                          <p className="mt-1 text-[11px] text-slate-400">in {doc.processing_seconds}s</p>
                        )}
                      </td>
                      <td className="hidden px-3 sm:px-4 py-3 text-right tabular-nums md:table-cell">{doc.page_count || '—'}</td>
                      <td className="hidden px-3 sm:px-4 py-3 text-right tabular-nums md:table-cell">{doc.chunk_count || '—'}</td>
                      <td className="hidden px-3 sm:px-4 py-3 text-xs text-slate-500 lg:table-cell">{formatDateTime(doc.created_at)}</td>
                      <td className="px-3 sm:px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => reprocess(doc)}
                            disabled={busyId === doc.id || doc.status === 'processing'}
                            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-brand-600 disabled:opacity-40 dark:hover:bg-slate-800"
                            aria-label={`Reprocess ${doc.title}`}
                            title="Reprocess"
                          >
                            <RefreshCw className={`size-4 ${busyId === doc.id ? 'animate-spin' : ''}`} />
                          </button>
                          <button
                            type="button"
                            onClick={() => setPendingDelete(doc)}
                            disabled={busyId === doc.id}
                            className="rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-40 dark:hover:bg-red-950/40"
                            aria-label={`Delete ${doc.title}`}
                            title="Delete"
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
        </Card>
      </div>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete document?"
        message={`"${pendingDelete?.title}" will be removed from the index and deleted from disk. The assistant will no longer answer from it.`}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        loading={busyId === pendingDelete?.id}
      />
    </div>
  )
}
