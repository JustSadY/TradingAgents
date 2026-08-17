import { useMemo } from 'react'
import { useSettingsGetLlmCatalog } from '../api/generated/settings/settings'

/**
 * The one LLM provider/model catalog the whole UI selects from.
 *
 * `/api/settings/llm-catalog` is built from `llm_clients/registry.py`, which
 * CLAUDE.md names as the provider/model source of truth. Before this hook the
 * general LLM preferences listed providers from `/api/meta`'s
 * `provider_labels` while the models beside them came from the catalog, and
 * the per-agent AI configuration had no catalog at all — its model field was a
 * free-text box. Same concept, three different pickers.
 *
 * Everything that offers a provider or a model now reads this.
 */

export interface LlmModelOption {
  value: string
  label: string
  supported_output_languages?: string[]
}

export interface LlmProviderEntry {
  label: string
  models: LlmModelOption[]
}

export type LlmCatalog = Record<string, LlmProviderEntry>

export function normalizeLlmCatalog(value: unknown): LlmCatalog {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return {}
  const catalog: LlmCatalog = {}
  for (const [provider, entry] of Object.entries(value)) {
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) continue
    const rawModels = (entry as Record<string, unknown>).models
    if (!Array.isArray(rawModels)) continue
    const models = rawModels.flatMap(model => {
      if (typeof model !== 'object' || model === null || Array.isArray(model)) return []
      const option = model as Record<string, unknown>
      if (typeof option.value !== 'string' || typeof option.label !== 'string') return []
      const supported_output_languages = Array.isArray(option.supported_output_languages)
        ? option.supported_output_languages.filter((language): language is string => typeof language === 'string')
        : undefined
      return [{ value: option.value, label: option.label, supported_output_languages }]
    })
    catalog[provider] = {
      label: typeof (entry as Record<string, unknown>).label === 'string'
        ? (entry as Record<string, unknown>).label as string
        : provider,
      models,
    }
  }
  return catalog
}

/** Provider `[key, label]` pairs in catalog order, for a provider `<select>`. */
export function providerOptionsFrom(catalog: LlmCatalog): Array<[string, string]> {
  return Object.entries(catalog).map(([key, entry]) => [key, entry.label])
}

/** The models a provider offers; empty for an unknown or unconfigured provider. */
export function modelsFor(catalog: LlmCatalog, provider: string | undefined | null): LlmModelOption[] {
  return (provider && catalog[provider]?.models) || []
}

export function useLlmCatalog(): LlmCatalog {
  const { data } = useSettingsGetLlmCatalog()
  return useMemo(() => normalizeLlmCatalog(data), [data])
}
