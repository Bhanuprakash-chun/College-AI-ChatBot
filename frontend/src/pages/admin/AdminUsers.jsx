import { useCallback, useEffect, useState } from 'react'
import { Search, Trash2, UserCheck, UserX, Users } from 'lucide-react'
import {
  Alert,
  Badge,
  Card,
  ConfirmDialog,
  EmptyState,
  PageHeader,
  Pagination,
  Spinner,
  inputClass,
} from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { api } from '../../lib/api'
import { formatDate, timeAgo, titleCase } from '../../lib/format'

export default function AdminUsers() {
  const { user: me } = useAuth()
  const toast = useToast()
  const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 15 })
  const [page, setPage] = useState(1)
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(
        await api.adminUsers({
          page,
          page_size: 15,
          role: role || undefined,
          search: debounced.trim() || undefined,
        }),
      )
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [page, role, debounced])

  useEffect(() => {
    load()
  }, [load])

  const update = async (target, patch, message) => {
    setBusyId(target.id)
    try {
      const updated = await api.updateUser(target.id, patch)
      setData((d) => ({ ...d, items: d.items.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)) }))
      toast.success(message)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const confirmDelete = async () => {
    setBusyId(pendingDelete.id)
    try {
      const res = await api.deleteUser(pendingDelete.id)
      toast.success(res.message)
      setPendingDelete(null)
      load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader title="Users" description="Change roles, deactivate accounts, or remove users and their chat history." />

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row dark:border-slate-800">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              className={`${inputClass} pl-9`}
              placeholder="Search by name or email…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              aria-label="Search users"
            />
          </div>
          <select
            className={`${inputClass} sm:w-40`}
            value={role}
            onChange={(e) => {
              setRole(e.target.value)
              setPage(1)
            }}
            aria-label="Filter by role"
          >
            <option value="">All roles</option>
            <option value="student">Students</option>
            <option value="admin">Admins</option>
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
          <EmptyState icon={Users} title="No users found" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/60 dark:text-slate-400">
                <tr>
                  <th className="px-3 sm:px-4 py-2.5 font-medium">User</th>
                  <th className="px-3 sm:px-4 py-2.5 font-medium">Role</th>
                  <th className="hidden px-3 sm:table-cell sm:px-4 py-2.5 font-medium">Status</th>
                  <th className="hidden px-3 sm:px-4 py-2.5 text-right font-medium md:table-cell">Questions</th>
                  <th className="hidden px-3 sm:px-4 py-2.5 font-medium lg:table-cell">Last sign-in</th>
                  <th className="hidden px-3 sm:px-4 py-2.5 font-medium lg:table-cell">Joined</th>
                  <th className="px-3 sm:px-4 py-2.5 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.items.map((u) => {
                  const isMe = u.id === me.id
                  const busy = busyId === u.id
                  return (
                    <tr key={u.id}>
                      <td className="px-3 sm:px-4 py-3">
                        <p className="font-medium text-slate-900 dark:text-white">
                          {u.full_name} {isMe && <span className="text-xs font-normal text-slate-400">(you)</span>}
                        </p>
                        <p className="text-xs break-all text-slate-500 dark:text-slate-400">{u.email}</p>
                        {u.department && <p className="text-xs text-slate-400">{u.department}</p>}
                        <div className="mt-1.5 sm:hidden">
                          <Badge value={u.is_active ? 'active' : 'inactive'} label={u.is_active ? 'Active' : 'Deactivated'} />
                        </div>
                      </td>
                      <td className="px-3 sm:px-4 py-3">
                        <select
                          value={u.role}
                          disabled={isMe || busy}
                          onChange={(e) =>
                            update(u, { role: e.target.value }, `${u.full_name} is now ${e.target.value === 'admin' ? 'an admin' : 'a student'}.`)
                          }
                          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900"
                          aria-label={`Role for ${u.full_name}`}
                        >
                          <option value="student">Student</option>
                          <option value="admin">Admin</option>
                        </select>
                      </td>
                      <td className="hidden px-3 sm:table-cell sm:px-4 py-3">
                        <Badge value={u.is_active ? 'active' : 'inactive'} label={u.is_active ? 'Active' : 'Deactivated'} />
                      </td>
                      <td className="hidden px-3 sm:px-4 py-3 text-right tabular-nums md:table-cell">{u.message_count}</td>
                      <td className="hidden px-3 sm:px-4 py-3 text-xs text-slate-500 lg:table-cell">
                        {u.last_login_at ? timeAgo(u.last_login_at) : 'Never'}
                      </td>
                      <td className="hidden px-3 sm:px-4 py-3 text-xs text-slate-500 lg:table-cell">{formatDate(u.created_at)}</td>
                      <td className="px-3 sm:px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            disabled={isMe || busy}
                            onClick={() =>
                              update(
                                u,
                                { is_active: !u.is_active },
                                `${u.full_name} ${u.is_active ? 'deactivated' : 'reactivated'}.`,
                              )
                            }
                            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-30 dark:hover:bg-slate-800 dark:hover:text-white"
                            aria-label={u.is_active ? `Deactivate ${u.full_name}` : `Reactivate ${u.full_name}`}
                            title={u.is_active ? 'Deactivate' : 'Reactivate'}
                          >
                            {u.is_active ? <UserX className="size-4" /> : <UserCheck className="size-4" />}
                          </button>
                          <button
                            type="button"
                            disabled={isMe || busy}
                            onClick={() => setPendingDelete(u)}
                            className="rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-30 dark:hover:bg-red-950/40"
                            aria-label={`Delete ${u.full_name}`}
                            title="Delete"
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
      </Card>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete user?"
        message={`${pendingDelete?.full_name} (${pendingDelete?.email}) and all of their conversations and feedback will be permanently deleted.`}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        loading={busyId === pendingDelete?.id}
      />
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Roles: {['student', 'admin'].map(titleCase).join(', ')}. You cannot change your own role or deactivate yourself.
      </p>
    </div>
  )
}
