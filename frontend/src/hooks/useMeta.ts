import { useEffect, useState } from 'react'
import axios from 'axios'



export interface AnalystMeta { key: string; label: string; description: string; default: boolean }
export interface Choice { value: string; label: string }
export interface SignalMeta { value: string; label: string; tone: 'positive' | 'neutral' | 'negative' }

export type ToolSettingType =
  | 'boolean'
  | 'number'
  | 'string'
  | 'textarea'
  | 'select'
  | 'multi_select'
  | 'string_list'
  | 'secret'

export interface ToolSettingFieldMeta {
  key: string
  type: ToolSettingType
  scope: 'server' | 'user' | 'both'
  label_key: string
  description_key?: string
  default?: any
  required?: boolean
  min?: number
  max?: number
  step?: number
  options?: { value: string; label_key: string }[]
  secret?: boolean
  advanced?: boolean
}

export interface ToolMeta {
  key: string
  category: string
  default_enabled: boolean
  allowed_analysts: string[]
  label_key: string
  description_key: string
  settings_schema: ToolSettingFieldMeta[]
}

export interface Meta {
  analysts: AnalystMeta[]
  tools: ToolMeta[]
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
const _listeners = new Set<(m: Meta | null) => void>()

export function triggerMetaRefetch() {
  _cache = null
  _inflight = axios.get('/api/meta').then(r => {
    _cache = r.data as Meta
    _listeners.forEach(l => l(_cache))
    return _cache
  }).catch(err => {
    _inflight = null
    throw err
  })
}

export function useMeta(): Meta | null {
  const [meta, setMeta] = useState<Meta | null>(_cache)

  useEffect(() => {
    _listeners.add(setMeta)
    if (_cache) {
      setMeta(_cache)
    } else if (!_inflight) {
      _inflight = axios.get('/api/meta').then(r => {
        _cache = r.data as Meta
        _listeners.forEach(l => l(_cache))
        return _cache
      }).catch(() => {
        _inflight = null
      })
    }
    return () => {
      _listeners.delete(setMeta)
    }
  }, [])

  return meta
}

