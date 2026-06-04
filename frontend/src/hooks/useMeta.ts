import { useEffect, useState } from 'react'
import axios from 'axios'



export interface AnalystMeta { key: string; label: string; description: string; default: boolean }
export interface Choice { value: string; label: string }
export interface SignalMeta { value: string; label: string; tone: 'positive' | 'neutral' | 'negative' }

export interface Meta {
  analysts: AnalystMeta[]
  section_labels: Record<string, string>
  signals: SignalMeta[]
  asset_types: Choice[]
  languages: Choice[]
  data_vendors: Choice[]
  trading_modes: Choice[]
  brokers: Choice[]
  provider_labels: Record<string, string>
}


let _cache: Meta | null = null
let _inflight: Promise<Meta> | null = null

export function useMeta(): Meta | null {
  const [meta, setMeta] = useState<Meta | null>(_cache)

  useEffect(() => {
    if (_cache) { setMeta(_cache); return }
    if (!_inflight) {
      _inflight = axios.get('/api/meta').then(r => { _cache = r.data as Meta; return _cache })
    }
    let active = true
    _inflight.then(m => { if (active) setMeta(m) }).catch(() => { _inflight = null })
    return () => { active = false }
  }, [])

  return meta
}

