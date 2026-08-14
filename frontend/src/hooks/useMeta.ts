import { useMetaGetMeta, getMetaGetMetaQueryKey } from '../api/generated/meta/meta'
import { queryClient } from '../api/queryClient'



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


// Metadata is user-scoped (custom personas and tool/agent visibility are
// filtered by the API), shared by many components, and must not survive a
// logout. That used to be a hand-rolled module cache with a listener set, an
// in-flight promise and a generation counter guarding against a response from
// the previous account landing after login. TanStack Query provides the shared
// cache, the request de-duplication and the cancellation, so only the
// user-scoping policy lives here.

/** Clear all in-memory metadata associated with the authenticated account. */
export function clearMetaCache() {
  const queryKey = getMetaGetMetaQueryKey()
  // cancel before remove: an in-flight request started by the previous account
  // must not repopulate the cache after the switch.
  void queryClient.cancelQueries({ queryKey })
  queryClient.removeQueries({ queryKey })
}

export function triggerMetaRefetch() {
  return queryClient.invalidateQueries({ queryKey: getMetaGetMetaQueryKey() })
}

export function useMeta(): Meta | null {
  const { data } = useMetaGetMeta()
  // /api/meta is typed as a free-form object in OpenAPI, so the richer local
  // Meta interface above stays the source of truth for consumers.
  return (data as unknown as Meta | undefined) ?? null
}
