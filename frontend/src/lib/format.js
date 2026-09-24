// Small presentation helpers shared across pages.

// The API stores naive UTC timestamps; treat strings without a zone as UTC.
export function parseDate(value) {
  if (!value) return null
  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value)
  const date = new Date(hasZone ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value) {
  const date = parseDate(value)
  if (!date) return '—'
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(value) {
  const date = parseDate(value)
  if (!date) return '—'
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function timeAgo(value) {
  const date = parseDate(value)
  if (!date) return ''
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days}d ago`
  return formatDate(value)
}

export function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function percent(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function titleCase(value) {
  if (!value) return ''
  return value.charAt(0).toUpperCase() + value.slice(1)
}

const compactNumber = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 })
const fullNumber = new Intl.NumberFormat()

// 1,284 / 12.9K: full precision until the number gets long.
export function formatCount(value) {
  if (value === null || value === undefined) return '—'
  return Math.abs(value) >= 10000 ? compactNumber.format(value) : fullNumber.format(value)
}

const ACTION_LABELS = {
  'auth.login': 'signed in',
  'auth.login_failed': 'failed sign-in',
  'auth.logout': 'signed out',
  'auth.register': 'registered',
  'document.upload': 'uploaded a document',
  'document.processed': 'document indexed',
  'document.failed': 'document processing failed',
  'document.delete': 'deleted a document',
  'document.reprocess': 'reprocessed a document',
  'user.update': 'updated a user',
  'user.delete': 'deleted a user',
  'chat.question': 'asked a question',
  'chat.session_delete': 'deleted a conversation',
  'feedback.submit': 'rated an answer',
}

export function describeAction(action) {
  return ACTION_LABELS[action] || action
}
