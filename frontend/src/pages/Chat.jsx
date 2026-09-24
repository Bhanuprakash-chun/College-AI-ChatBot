import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowUp,
  Award,
  BookOpen,
  Briefcase,
  CalendarDays,
  ClipboardCheck,
  FileBadge,
  GraduationCap,
  RotateCcw,
  UserCheck,
} from 'lucide-react'
import ChatMessage, { TypingIndicator } from '../components/ChatMessage'
import { Alert, Spinner } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useSessions } from '../context/SessionsContext'
import { api } from '../lib/api'

const SUGGESTIONS = [
  { icon: UserCheck, text: 'What is the minimum attendance requirement?' },
  { icon: CalendarDays, text: 'When are the semester exams held?' },
  { icon: FileBadge, text: 'How do I get a bonafide certificate?' },
  { icon: BookOpen, text: 'What subjects are taught in third year?' },
  { icon: ClipboardCheck, text: 'What documents are needed for admission?' },
  { icon: Award, text: 'What scholarships are available?' },
  { icon: Briefcase, text: 'What are the placement eligibility requirements?' },
]

const MAX_CHARS = 2000

export default function Chat() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { touch, refresh } = useSessions()

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loadingSession, setLoadingSession] = useState(false)
  const [loadError, setLoadError] = useState(null)

  const scrollRef = useRef(null)
  const textareaRef = useRef(null)
  const abortRef = useRef(null)
  // Set when we navigate to a session we just created, so the loader
  // doesn't re-fetch messages we already have on screen.
  const justCreatedRef = useRef(null)

  // Load the conversation when the URL points at an existing session.
  useEffect(() => {
    abortRef.current?.abort()
    setLoadError(null)

    if (!sessionId) {
      setMessages([])
      return
    }
    if (justCreatedRef.current === sessionId) {
      justCreatedRef.current = null
      return
    }

    let cancelled = false
    setLoadingSession(true)
    api
      .session(sessionId)
      .then((data) => {
        if (!cancelled) setMessages(data.messages)
      })
      .catch((err) => {
        if (cancelled) return
        if (err.status === 404) navigate('/chat', { replace: true })
        else setLoadError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoadingSession(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, navigate])

  // Keep the newest message in view.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  // Auto-grow the textarea.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [input])

  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (text) => {
      const question = text.trim()
      if (!question || sending) return

      const tempId = `pending-${Date.now()}`
      setMessages((prev) => [
        ...prev.filter((m) => !m.error),
        { id: tempId, role: 'user', content: question, pending: true },
      ])
      setInput('')
      setSending(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const result = await api.chat(question, sessionId ? Number(sessionId) : null, controller.signal)
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== tempId),
          result.user_message,
          result.assistant_message,
        ])
        touch({
          id: result.session_id,
          title: result.session_title,
          updated_at: result.assistant_message.created_at,
        })
        if (!sessionId) {
          justCreatedRef.current = String(result.session_id)
          navigate(`/chat/${result.session_id}`, { replace: true })
          refresh()
        }
      } catch (err) {
        if (err.name === 'AbortError') return
        setMessages((prev) => [
          ...prev.map((m) => (m.id === tempId ? { ...m, pending: false } : m)),
          {
            id: null,
            role: 'assistant',
            error: true,
            retryText: question,
            content: err.message || 'The assistant could not answer right now.',
          },
        ])
      } finally {
        setSending(false)
        textareaRef.current?.focus()
      }
    },
    [sending, sessionId, navigate, touch, refresh],
  )

  const retry = (text) => {
    // Drop the failed exchange before re-sending it.
    setMessages((prev) => {
      const copy = prev.filter((m) => !m.error)
      const last = copy[copy.length - 1]
      if (last?.role === 'user' && last.content === text && String(last.id).startsWith('pending')) {
        copy.pop()
      }
      return copy
    })
    send(text)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send(input)
    }
  }

  const onRated = (id, rating) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, feedback: rating } : m)))

  const empty = !messages.length && !loadingSession && !sending
  const firstName = user?.full_name?.split(' ')[0]

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
          {loadingSession && (
            <div className="flex justify-center py-16 text-slate-400">
              <Spinner className="size-6" />
            </div>
          )}

          {loadError && <Alert>{loadError}</Alert>}

          {empty && (
            <div className="flex flex-col items-center pt-6 text-center sm:pt-14">
              <div className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-brand-600/20">
                <GraduationCap className="size-7" />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                {firstName ? `Hi ${firstName}, how can I help?` : 'How can I help?'}
              </h1>
              <p className="mt-2 max-w-lg text-sm text-slate-500 dark:text-slate-400">
                Ask about attendance, exams, fees, admissions, certificates, scholarships, hostel or
                placements. Every answer comes from official college documents, with sources.
              </p>

              <div className="mt-8 grid w-full gap-2.5 sm:grid-cols-2">
                {SUGGESTIONS.map(({ icon: Icon, text }) => (
                  <button
                    key={text}
                    type="button"
                    onClick={() => send(text)}
                    className="group flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 shadow-sm transition hover:border-brand-300 hover:bg-brand-50/50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-brand-700 dark:hover:bg-brand-500/5"
                  >
                    <Icon className="size-4 shrink-0 text-brand-600 dark:text-brand-400" />
                    <span>{text}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {!loadingSession && messages.length > 0 && (
            <div className="space-y-6">
              {messages.map((m, i) => (
                <div key={m.id ?? `msg-${i}`}>
                  <ChatMessage message={m} onRated={onRated} />
                  {m.error && m.retryText && (
                    <div className="mt-2 ml-11">
                      <button
                        type="button"
                        onClick={() => retry(m.retryText)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                      >
                        <RotateCcw className="size-3.5" /> Try again
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {sending && <TypingIndicator />}
            </div>
          )}

          {sending && !messages.length && <TypingIndicator />}
        </div>
      </div>

      <div className="border-t border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
        <form
          className="mx-auto w-full max-w-3xl px-4 py-3 sm:px-6 sm:py-4"
          onSubmit={(e) => {
            e.preventDefault()
            send(input)
          }}
        >
          <div className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-900">
            <label htmlFor="chat-input" className="sr-only">
              Ask a question about the college
            </label>
            <textarea
              id="chat-input"
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, MAX_CHARS))}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="Ask a question about the college…"
              className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] placeholder:text-slate-400 focus:outline-none"
              disabled={sending}
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-slate-800 dark:disabled:text-slate-600"
              aria-label="Send message"
            >
              {sending ? <Spinner className="size-4" /> : <ArrowUp className="size-5" />}
            </button>
          </div>
          <p className="mt-2 text-center text-[11px] text-slate-400 dark:text-slate-500">
            Answers come only from official college documents. Verify important details with the
            concerned department.
            {input.length > MAX_CHARS * 0.8 && (
              <span className="ml-1">
                ({input.length}/{MAX_CHARS})
              </span>
            )}
          </p>
        </form>
      </div>
    </div>
  )
}
