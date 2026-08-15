import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, X, RefreshCw } from 'lucide-react'
import {
  getUpdateUpdateStatusQueryKey,
  useUpdateUpdateApply,
  useUpdateUpdateStatus,
} from '../api/generated/update/update'
import { notify } from '../utils/notify'
import { useAuth } from '../contexts/AuthContext'
import { useTranslation } from '../contexts/LanguageContext'

const POLL_IDLE_MS = 60 * 60 * 1000
const POLL_BUSY_MS = 4_000
const UPDATE_TIMEOUT_MS = 12 * 60 * 1000

export default function UpdateBanner() {
  const { t } = useTranslation()
  const { isOwner } = useAuth()
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const seenRef = useRef(false)
  const busyRef = useRef(false)
  const busyStartRef = useRef<number | null>(null)

  useEffect(() => { busyRef.current = busy }, [busy])

  const statusQuery = useUpdateUpdateStatus({
    query: {
      retry: false,
      refetchInterval: busy ? POLL_BUSY_MS : POLL_IDLE_MS,
      refetchOnWindowFocus: false,
    },
  })
  const st = statusQuery.data ?? null

  useEffect(() => {
    if (!busy || !busyStartRef.current) return
    const remaining = UPDATE_TIMEOUT_MS - (Date.now() - busyStartRef.current)
    const timeout = window.setTimeout(() => {
      setBusy(false)
      busyRef.current = false
      busyStartRef.current = null
      notify('error', t('update.timed_out'), t('update.title'), 'owner')
    }, Math.max(0, remaining))
    return () => window.clearTimeout(timeout)
  }, [busy, t])

  useEffect(() => {
    if (!st) return

    if (st.update_available && !st.updating && !seenRef.current) {
      seenRef.current = true
      notify('info', t('update.available_notice', { commits: st.behind }), t('update.title'), 'owner')
    }
    if (!st.update_available) seenRef.current = false

    // Only react to a fresh successful status response. A failed poll while the
    // server restarts is intentionally silent; the active query keeps polling.
    if (busyRef.current && !st.updating) {
      setBusy(false)
      busyRef.current = false
      busyStartRef.current = null
      if (st.last_update?.state === 'failed') {
        notify('error', st.last_update?.error || t('update.failed'), t('update.title'), 'owner')
      } else {
        window.location.reload()
      }
    }
  }, [statusQuery.dataUpdatedAt, st, t])

  const applyMutation = useUpdateUpdateApply<unknown>({
    mutation: {
      onSuccess: () => {
        notify('info', t('update.started'), t('update.title'), 'owner')
        void queryClient.invalidateQueries({ queryKey: getUpdateUpdateStatusQueryKey() })
      },
      onError: (error) => {
        setBusy(false)
        busyRef.current = false
        busyStartRef.current = null
        const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        notify('error', detail || t('update.could_not_start'), t('update.title'), 'owner')
      },
    },
  })

  const doUpdate = () => {
    if (!window.confirm(t('update.confirm'))) return
    setBusy(true)
    busyRef.current = true
    busyStartRef.current = Date.now()
    applyMutation.mutate()
  }

  if (!st || !st.update_supported) return null
  const updating = busy || st.updating

  if (!updating) {
    if (!isOwner || !st.update_available || dismissed) return null
  }

  return (
    <div
      className={`flex items-center gap-3 px-5 py-2.5 text-sm border-b ${
        updating
          ? 'bg-violet-500/10 border-violet-500/20 text-violet-200'
          : 'bg-amber-500/10 border-amber-500/20 text-amber-100'
      }`}
    >
      {updating ? <Loader2 size={15} className="animate-spin shrink-0" /> : <Download size={15} className="shrink-0 text-amber-300" />}
      <div className="flex-1 min-w-0">
        {updating ? (
          <span>{t('update.in_progress')}</span>
        ) : (
          <span>
            {t('update.new_version')}{st.behind ? ` — ${t('update.commits_behind', { commits: st.behind })}` : ''}.{' '}
            <span className="font-mono text-xs text-amber-300/70">{st.current_short} → {st.latest_short}</span>
          </span>
        )}
      </div>
      {!updating && isOwner && (
        <>
          <button
            onClick={doUpdate}
            disabled={applyMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-gray-900 font-semibold text-xs transition-colors shrink-0 disabled:opacity-50"
          >
            <RefreshCw size={12} /> {t('update.apply')}
          </button>
          <button onClick={() => setDismissed(true)} className="text-amber-300/60 hover:text-amber-100 transition-colors shrink-0" title={t('update.dismiss')}>
            <X size={15} />
          </button>
        </>
      )}
    </div>
  )
}
