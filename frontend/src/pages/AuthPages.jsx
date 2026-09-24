import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, GraduationCap, Moon, Sun } from 'lucide-react'
import { Alert, Button, Field, inputClass } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

function AuthShell({ title, subtitle, children, footer }) {
  const { theme, toggle } = useTheme()
  return (
    <div className="relative flex min-h-full items-center justify-center bg-gradient-to-br from-brand-50 via-white to-slate-100 px-4 py-10 dark:from-slate-950 dark:via-slate-950 dark:to-brand-950/40">
      <button
        type="button"
        onClick={toggle}
        className="absolute top-4 right-4 rounded-lg p-2 text-slate-500 hover:bg-white/70 dark:text-slate-400 dark:hover:bg-slate-800"
        aria-label="Toggle dark mode"
      >
        {theme === 'dark' ? <Sun className="size-5" /> : <Moon className="size-5" />}
      </button>

      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-brand-600/25">
            <GraduationCap className="size-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/50 sm:p-8 dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
          {children}
        </div>
        <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">{footer}</p>
      </div>
    </div>
  )
}

function PasswordInput({ id, value, onChange, autoComplete }) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="relative">
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        required
        className={`${inputClass} pr-10`}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
        aria-label={visible ? 'Hide password' : 'Show password'}
      >
        {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  )
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const user = await login(email.trim(), password)
      const from = location.state?.from
      navigate(from && from !== '/login' ? from : user.role === 'admin' ? '/admin' : '/chat', {
        replace: true,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to ask questions about your college"
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
            Create a student account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error && <Alert>{error}</Alert>}
        <Field label="College email" htmlFor="email">
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            autoFocus
            className={inputClass}
            placeholder="you@college.edu"
          />
        </Field>
        <Field label="Password" htmlFor="password">
          <PasswordInput
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </Field>
        <Button type="submit" className="w-full" size="lg" loading={submitting} disabled={!email || !password}>
          Sign in
        </Button>
      </form>
    </AuthShell>
  )
}

function validateRegistration({ fullName, email, password, confirm }) {
  const errors = {}
  if (fullName.trim().length < 2) errors.fullName = 'Enter your full name.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) errors.email = 'Enter a valid email address.'
  if (password.length < 8) errors.password = 'Use at least 8 characters.'
  else if (!/[A-Za-z]/.test(password) || !/\d/.test(password))
    errors.password = 'Include at least one letter and one number.'
  if (confirm !== password) errors.confirm = 'Passwords do not match.'
  return errors
}

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ fullName: '', email: '', department: '', password: '', confirm: '' })
  const [fieldErrors, setFieldErrors] = useState({})
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const onSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    const errors = validateRegistration(form)
    setFieldErrors(errors)
    if (Object.keys(errors).length) return

    setSubmitting(true)
    try {
      await register({
        full_name: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
        department: form.department.trim() || null,
      })
      navigate('/chat', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Student access to the College AI Assistant"
      footer={
        <>
          Already registered?{' '}
          <Link to="/login" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error && <Alert>{error}</Alert>}
        <Field label="Full name" htmlFor="fullName" error={fieldErrors.fullName}>
          <input id="fullName" value={form.fullName} onChange={update('fullName')} autoComplete="name" className={inputClass} autoFocus />
        </Field>
        <Field label="College email" htmlFor="regEmail" error={fieldErrors.email}>
          <input id="regEmail" type="email" value={form.email} onChange={update('email')} autoComplete="email" className={inputClass} placeholder="you@college.edu" />
        </Field>
        <Field label="Department" htmlFor="department" hint="Optional, e.g. Computer Science">
          <input id="department" value={form.department} onChange={update('department')} className={inputClass} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Password" htmlFor="regPassword" error={fieldErrors.password}>
            <PasswordInput id="regPassword" value={form.password} onChange={update('password')} autoComplete="new-password" />
          </Field>
          <Field label="Confirm password" htmlFor="confirm" error={fieldErrors.confirm}>
            <PasswordInput id="confirm" value={form.confirm} onChange={update('confirm')} autoComplete="new-password" />
          </Field>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          At least 8 characters, with a letter and a number.
        </p>
        <Button type="submit" className="w-full" size="lg" loading={submitting}>
          Create account
        </Button>
      </form>
    </AuthShell>
  )
}
