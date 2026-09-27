// Thin fetch wrapper: attaches the JWT, normalises errors, and signals the
// auth layer when the server says the session is no longer valid.

const API_BASE = import.meta.env.DEV
  ? '/api'
  : ''
const TOKEN_KEY = 'college_ai_token'

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

export const tokenStore = {
  get() {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(token) {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      /* storage blocked: the session simply won't survive a reload */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
}

let unauthorizedHandler = null
export function onUnauthorized(handler) {
  unauthorizedHandler = handler
}

function describeError(status, body) {
  if (body?.errors?.length) {
    return body.errors.map((e) => `${e.field}: ${e.message}`).join('; ')
  }
  if (typeof body?.detail === 'string') return body.detail
  if (status === 0) return 'Cannot reach the server. Check that the backend is running.'
  if (status === 429) return 'Too many requests. Please wait a moment and try again.'
  if (status >= 500) return 'The server ran into a problem. Please try again.'
  return `Request failed (${status}).`
}

export async function request(path, { method = 'GET', body, form, signal, auth = true } = {}) {
  const headers = { Accept: 'application/json' }
  const token = tokenStore.get()
  if (auth && token) headers.Authorization = `Bearer ${token}`

  let payload
  if (form) {
    payload = form // browser sets the multipart boundary
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, { method, headers, body: payload, signal })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError(describeError(0), 0)
  }

  let data = null
  const text = await response.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }

  if (!response.ok) {
    if (response.status === 401 && auth && token && unauthorizedHandler) {
      unauthorizedHandler()
    }
    throw new ApiError(describeError(response.status, data), response.status, data)
  }
  return data
}

const qs = (params = {}) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') search.set(k, v)
  })
  const s = search.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // auth
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  register: (payload) => request('/auth/register', { method: 'POST', body: payload, auth: false }),
  me: () => request('/auth/me'),
  logout: () => request('/auth/logout', { method: 'POST' }),

  // chat
  chat: (message, sessionId, signal) =>
    request('/chat', {
      method: 'POST',
      body: { message, session_id: sessionId ?? null },
      signal,
    }),
  sessions: (search) => request(`/chat/sessions${qs({ search })}`),
  createSession: (title) => request('/chat/sessions', { method: 'POST', body: { title } }),
  session: (id) => request(`/chat/sessions/${id}`),
  deleteSession: (id) => request(`/chat/sessions/${id}`, { method: 'DELETE' }),
  feedback: (messageId, rating, comment) =>
    request('/feedback', { method: 'POST', body: { message_id: messageId, rating, comment } }),

  // documents
  documents: (params) => request(`/documents${qs(params)}`),

  // admin
  adminDocuments: (params) => request(`/admin/documents${qs(params)}`),
  adminDocument: (id) => request(`/admin/documents/${id}`),
  uploadDocument: (formData) =>
    request('/admin/documents/upload', { method: 'POST', form: formData }),
  deleteDocument: (id) => request(`/admin/documents/${id}`, { method: 'DELETE' }),
  reprocessDocument: (id) => request(`/admin/documents/${id}/reprocess`, { method: 'POST' }),
  adminUsers: (params) => request(`/admin/users${qs(params)}`),
  updateUser: (id, patch) => request(`/admin/users/${id}`, { method: 'PATCH', body: patch }),
  deleteUser: (id) => request(`/admin/users/${id}`, { method: 'DELETE' }),
  statistics: () => request('/admin/statistics'),
  analytics: (days) => request(`/admin/analytics${qs({ days })}`),
  adminFeedback: (params) => request(`/admin/feedback${qs(params)}`),
  auditLogs: (params) => request(`/admin/audit-logs${qs(params)}`),
  // Sends the token when present: admins receive full diagnostics.
  health: () => request('/health'),
}
