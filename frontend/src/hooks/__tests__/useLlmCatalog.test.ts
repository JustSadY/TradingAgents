import { describe, it, expect } from 'vitest'
import { modelsFor, normalizeLlmCatalog, providerOptionsFrom } from '../useLlmCatalog'

const CATALOG = {
  openai: {
    label: 'OpenAI',
    models: [
      { value: 'gpt-5.6-luna', label: 'GPT-5.6 Luna', supported_output_languages: ['English', 'Turkish'] },
      { value: 'gpt-5.6-sol', label: 'GPT-5.6 Sol' },
    ],
  },
  anthropic: {
    label: 'Anthropic (Claude)',
    models: [{ value: 'claude-sonnet-5', label: 'Claude Sonnet 5' }],
  },
}

describe('normalizeLlmCatalog', () => {
  it('keeps providers, labels and models from the API payload', () => {
    const catalog = normalizeLlmCatalog(CATALOG)

    expect(Object.keys(catalog)).toEqual(['openai', 'anthropic'])
    expect(catalog.openai.label).toBe('OpenAI')
    expect(catalog.openai.models).toHaveLength(2)
    expect(catalog.openai.models[0].supported_output_languages).toEqual(['English', 'Turkish'])
  })

  it('drops malformed entries instead of rendering broken options', () => {
    const catalog = normalizeLlmCatalog({
      openai: { label: 'OpenAI', models: [{ value: 'ok', label: 'OK' }, { value: 7 }, 'nope'] },
      broken: { label: 'Broken' },
      alsoBroken: null,
    })

    expect(Object.keys(catalog)).toEqual(['openai'])
    expect(catalog.openai.models).toEqual([{ value: 'ok', label: 'OK', supported_output_languages: undefined }])
  })

  it('returns an empty catalog for a non-object payload', () => {
    expect(normalizeLlmCatalog(undefined)).toEqual({})
    expect(normalizeLlmCatalog([])).toEqual({})
    expect(normalizeLlmCatalog('nope')).toEqual({})
  })
})

describe('providerOptionsFrom', () => {
  it('lists providers in catalog order so options and models cannot diverge', () => {
    expect(providerOptionsFrom(normalizeLlmCatalog(CATALOG))).toEqual([
      ['openai', 'OpenAI'],
      ['anthropic', 'Anthropic (Claude)'],
    ])
  })
})

describe('modelsFor', () => {
  const catalog = normalizeLlmCatalog(CATALOG)

  it('returns the selected provider models', () => {
    expect(modelsFor(catalog, 'anthropic').map(model => model.value)).toEqual(['claude-sonnet-5'])
  })

  it('returns nothing for an unknown or missing provider', () => {
    expect(modelsFor(catalog, 'mystery')).toEqual([])
    expect(modelsFor(catalog, undefined)).toEqual([])
    expect(modelsFor(catalog, null)).toEqual([])
  })
})
