import { useEffect, useRef, useState, useCallback } from 'react'
import axios from 'axios'
import { Download, Loader2, X, RefreshCw } from 'lucide-react'
import { notify } from '../utils/notify'
import { useAuth } from '../contexts/AuthContext'

interface UpdateStatus {
  git: boolean
  update_supported: boolean
  update_available: boolean
  updating: boolean
  current_short?: string | null
  latest_short?: string | null
  behind: number
  commits?: string[]
  last_update?: { state?: string; error?: string }
}

const POLL_IDLE_MS = 60 * 60 * 1000   // 1 saat — boşta
const POLL_BUSY_MS = 4_000              // 4 saniye — güncelleme sırasında
const UPDATE_TIMEOUT_MS = 12 * 60 * 1000 // 12 dakika — bu kadar sürer takılı sayılır

export default function UpdateBanner() {
  const { isOwner } = useAuth()
  const [st, setSt] = useState<UpdateStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const seenRef = useRef(false)
  const sawDownRef = useRef(false)
  const busyRef = useRef(false)
  const busyStartRef = useRef<number | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => { busyRef.current = busy }, [busy])

  const poll = useCallback(async () => {
    // Timeout kontrolü: güncelleme 12 dakikadan uzun sürüyorsa hata göster
    if (busyRef.current && busyStartRef.current && Date.now() - busyStartRef.current > UPDATE_TIMEOUT_MS) {
      setBusy(false)
      busyStartRef.current = null
      sawDownRef.current = false
      notify('error', 'Güncelleme çok uzun sürdü — sunucu logu kontrol edin.', 'Güncelleme', 'owner')
      return
    }

    try {
      const { data } = await axios.get<UpdateStatus>('/api/update/status')
      setSt(data)

      if (data.update_available && !data.updating && !seenRef.current) {
        seenRef.current = true
        notify('info', `Yeni güncelleme mevcut (${data.behind} commit).`, 'Güncelleme', 'owner')
      }
      if (!data.update_available) seenRef.current = false

      if (busyRef.current && !data.updating) {
        setBusy(false)
        busyStartRef.current = null
        sawDownRef.current = false
        if (data.last_update?.state === 'failed') {
          notify('error', data.last_update?.error || 'Güncelleme başarısız oldu.', 'Güncelleme', 'owner')
        } else {
          // Güncelleme başarılı, sayfa yenile
          window.location.reload()
        }
      }
    } catch {
      // Sunucu yeniden başlıyor — bir sonraki başarılı yanıtta reload yapılacak
      if (busyRef.current) sawDownRef.current = true
    }
  }, [])

  // busy değiştiğinde polling hızını ayarla
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    const ms = busy ? POLL_BUSY_MS : POLL_IDLE_MS
    intervalRef.current = setInterval(poll, ms)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [busy, poll])

  useEffect(() => {
    poll()
  }, [poll])

  const doUpdate = async () => {
    if (!window.confirm('Uygulama en son sürüme güncellenip yeniden başlatılacak (~1-2 dk). Devam edilsin mi?')) return
    setBusy(true); busyRef.current = true; busyStartRef.current = Date.now(); sawDownRef.current = false
    try {
      await axios.post('/api/update/apply')
      notify('info', 'Güncelleme başlatıldı — lütfen bekleyin, sayfa otomatik yenilenecek.', 'Güncelleme', 'owner')
      poll()
    } catch (e: any) {
      setBusy(false)
      busyStartRef.current = null
      notify('error', e?.response?.data?.detail || 'Güncelleme başlatılamadı.', 'Güncelleme', 'owner')
    }
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
          <span>Güncelleniyor — uygulama birazdan yeniden başlayacak, sayfa otomatik yenilenecek...</span>
        ) : (
          <span>
            Yeni sürüm mevcut{st.behind ? ` — ${st.behind} commit geride` : ''}.{' '}
            <span className="font-mono text-xs text-amber-300/70">{st.current_short} → {st.latest_short}</span>
          </span>
        )}
      </div>
      {!updating && isOwner && (
        <>
          <button
            onClick={doUpdate}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-gray-900 font-semibold text-xs transition-colors shrink-0"
          >
            <RefreshCw size={12} /> Güncelle
          </button>
          <button onClick={() => setDismissed(true)} className="text-amber-300/60 hover:text-amber-100 transition-colors shrink-0" title="Gizle">
            <X size={15} />
          </button>
        </>
      )}
    </div>
  )
}

