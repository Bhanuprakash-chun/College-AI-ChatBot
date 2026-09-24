import { useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  FileText,
  GraduationCap,
  SearchX,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'
import Markdown from './Markdown'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext'

function Citations({ citations }) {
  const [open, setOpen] = useState(false)
  if (!citations?.length) return null

  return (
    <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700/70">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
        aria-expanded={open}
      >
        <FileText className="size-3.5" />
        {citations.length} source{citations.length > 1 ? 's' : ''}
        <ChevronDown className={`size-3.5 transition ${open ? 'rotate-180' : ''}`} />
      </button>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {citations.map((c, i) => (
          <span
            key={`${c.document_id}-${i}`}
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300"
            title={`Relevance ${(c.similarity * 100).toFixed(0)}%`}
          >
            <span className="font-medium">{c.title}</span>
            {c.page && <span className="text-slate-400">· p.{c.page}</span>}
          </span>
        ))}
      </div>

      {open && (
        <ol className="mt-3 space-y-2">
          {citations.map((c, i) => (
            <li
              key={`detail-${c.document_id}-${i}`}
              className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-700 dark:bg-slate-800/40"
            >
              <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  [{i + 1}] {c.title}
                  {c.page && <span className="font-normal text-slate-500"> — page {c.page}</span>}
                </span>
                <span className="rounded bg-brand-50 px-1.5 py-0.5 font-medium text-brand-700 dark:bg-brand-500/10 dark:text-brand-300">
                  {(c.similarity * 100).toFixed(0)}% match
                </span>
              </div>
              <p className="leading-relaxed text-slate-600 dark:text-slate-400">“{c.snippet}”</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function FeedbackButtons({ message, onRated }) {
  const toast = useToast()
  const [rating, setRating] = useState(message.feedback || null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const rate = async (value) => {
    if (busy || rating === value) return
    setBusy(true)
    const previous = rating
    setRating(value)
    try {
      await api.feedback(message.id, value)
      onRated?.(message.id, value)
      toast.success(value === 'up' ? 'Thanks for the feedback!' : 'Thanks — we’ll use this to improve.')
    } catch (err) {
      setRating(previous)
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('Could not copy to clipboard.')
    }
  }

  const base =
    'rounded-md p-1.5 transition hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800'
  return (
    <div className="mt-2 flex items-center gap-0.5 text-slate-400">
      <button
        type="button"
        onClick={() => rate('up')}
        disabled={busy}
        className={`${base} ${rating === 'up' ? 'text-emerald-600 dark:text-emerald-400' : 'hover:text-slate-700 dark:hover:text-slate-200'}`}
        aria-label="Helpful answer"
        aria-pressed={rating === 'up'}
        title="Helpful"
      >
        <ThumbsUp className="size-4" fill={rating === 'up' ? 'currentColor' : 'none'} />
      </button>
      <button
        type="button"
        onClick={() => rate('down')}
        disabled={busy}
        className={`${base} ${rating === 'down' ? 'text-red-600 dark:text-red-400' : 'hover:text-slate-700 dark:hover:text-slate-200'}`}
        aria-label="Unhelpful answer"
        aria-pressed={rating === 'down'}
        title="Not helpful"
      >
        <ThumbsDown className="size-4" fill={rating === 'down' ? 'currentColor' : 'none'} />
      </button>
      <button
        type="button"
        onClick={copy}
        className={`${base} hover:text-slate-700 dark:hover:text-slate-200`}
        aria-label="Copy answer"
        title="Copy"
      >
        {copied ? <Check className="size-4 text-emerald-600" /> : <Copy className="size-4" />}
      </button>
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white">
        <GraduationCap className="size-4" />
      </div>
      <div className="rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <span className="flex gap-1" aria-hidden="true">
            <span className="typing-dot size-1.5 rounded-full bg-current" />
            <span className="typing-dot size-1.5 rounded-full bg-current" />
            <span className="typing-dot size-1.5 rounded-full bg-current" />
          </span>
          <span>Searching college documents…</span>
        </div>
      </div>
    </div>
  )
}

export default function ChatMessage({ message, onRated }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-white shadow-sm sm:max-w-[75%]">
          {message.content}
        </div>
      </div>
    )
  }

  const notFound = !message.grounded && !message.error
  const degraded = message.grounded && !message.llm_used

  return (
    <div className="flex gap-3">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white">
        <GraduationCap className="size-4" />
      </div>
      <div className="min-w-0 max-w-[85%] flex-1 sm:max-w-[80%]">
        <div
          className={`rounded-2xl rounded-tl-sm border px-4 py-3 shadow-sm ${
            message.error
              ? 'border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/40'
              : notFound
                ? 'border-amber-200 bg-amber-50/70 dark:border-amber-900/50 dark:bg-amber-950/30'
                : 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900'
          }`}
        >
          {message.error && (
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-red-700 dark:text-red-300">
              <AlertTriangle className="size-3.5" /> Something went wrong
            </div>
          )}
          {notFound && (
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300">
              <SearchX className="size-3.5" /> Not found in college documents
            </div>
          )}
          {degraded && (
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300">
              <AlertTriangle className="size-3.5" /> Language model offline — showing document excerpts
            </div>
          )}
          <Markdown>{message.content}</Markdown>
          <Citations citations={message.citations} />
        </div>
        {!message.error && message.id && <FeedbackButtons message={message} onRated={onRated} />}
      </div>
    </div>
  )
}
