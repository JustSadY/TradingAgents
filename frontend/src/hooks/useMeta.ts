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

export interface AgentSettingFieldMeta {
  key: string
  type: string
  label_key: string
  description_key?: string
  default?: any
  required?: boolean
  min?: number
  max?: number
  step?: number
  options?: { value: string; label_key: string }[]
}

export interface AgentMeta {
  key: string
  label: string
  description: string
  category: string
  parent_key?: string | null
  default_enabled: boolean
  settings_schema: AgentSettingFieldMeta[]
}

export interface Meta {
  analysts: AnalystMeta[]
  tools: ToolMeta[]
  agents?: AgentMeta[]
  section_labels: Record<string, string>
  signals: SignalMeta[]
  asset_types: Choice[]
  languages: Choice[]
  data_vendors: Choice[]
  trading_modes: Choice[]
  brokers: Choice[]
  provider_labels: Record<string, string>
  investor_personas?: Choice[]
  webhook_events: string[]
  memory_stores: Choice[]
  embedders: Choice[]
  page_keys: string[]
  setting_keys: Choice[]
  effort_options?: Record<string, Choice[]>
}


let _cache: Meta | null = null
let _inflight: Promise<Meta> | null = null
const _listeners = new Set<(m: Meta | null) => void>()
// Meta is user-scoped (custom personas and tool/agent visibility are filtered
// by the API).  A generation token keeps a response started for a previous
// account from repopulating the cache after logout/login.
let _generation = 0

function notifyListeners(meta: Meta | null) {
  _listeners.forEach(listener => listener(meta))
}

function fetchMeta(): Promise<Meta> {
  const generation = _generation
  const request = axios.get('/api/meta').then(r => {
    const meta = r.data as Meta
    if (_generation === generation) {
      _cache = meta
      notifyListeners(meta)
    }
    return meta
  }).catch(err => {
    if (_generation === generation) _inflight = null
    throw err
  })
  _inflight = request
  return request
}

/** Clear all in-memory metadata associated with the authenticated account. */
export function clearMetaCache() {
  _generation += 1
  _cache = null
  _inflight = null
  notifyListeners(null)
}

export function triggerMetaRefetch() {
  clearMetaCache()
  return fetchMeta()
}

export function useMeta(): Meta | null {
  const [meta, setMeta] = useState<Meta | null>(_cache)

  useEffect(() => {
    _listeners.add(setMeta)
    if (_cache) {
      setMeta(_cache)
    } else if (!_inflight) {
      // Consumers surface their own loading state; a failed metadata fetch
      // should not create an unhandled rejection in a render effect.
      void fetchMeta().catch(() => {})
    }
    return () => {
      _listeners.delete(setMeta)
    }
  }, [])

  return meta
}
