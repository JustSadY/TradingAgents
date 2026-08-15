import { describe, it, expect } from 'vitest'
import { TRANSLATIONS } from '../index'

// Read the same merged table the app resolves `t()` against. This used to run
// against a hand-copied duplicate of the shell keys, which meant 13 of them
// were never actually parity-checked.
const TRANSLATIONS_EN = TRANSLATIONS.en
const TRANSLATIONS_TR = TRANSLATIONS.tr

describe('i18n translation coverage', () => {
  it('loads the shell keys as well as the per-page modules', () => {
    // Guards the glob in ../index.ts: a pattern that stopped matching would
    // otherwise leave every assertion below trivially passing on {}.
    expect(TRANSLATIONS_EN['nav.dashboard']).toBeTruthy()
    expect(TRANSLATIONS_EN['settings.personas_title']).toBeTruthy()
    expect(TRANSLATIONS_EN['analysis.strategy.version']).toBeTruthy()
    expect(Object.keys(TRANSLATIONS_EN).length).toBeGreaterThan(900)
  })

  it('all English keys have Turkish translations', () => {
    const enKeys = Object.keys(TRANSLATIONS_EN)
    const trKeys = new Set(Object.keys(TRANSLATIONS_TR))
    const missing = enKeys.filter(k => !trKeys.has(k))
    if (missing.length > 0) {
      console.warn('Missing Turkish translations for:', missing)
    }
    expect(missing).toEqual([])
  })

  it('all Turkish keys have English translations', () => {
    const enKeys = new Set(Object.keys(TRANSLATIONS_EN))
    const trKeys = Object.keys(TRANSLATIONS_TR)
    const extra = trKeys.filter(k => !enKeys.has(k))
    if (extra.length > 0) {
      console.warn('Extra Turkish keys without English:', extra)
    }
    expect(extra).toEqual([])
  })

  it('no empty translation values in English', () => {
    const empty = Object.entries(TRANSLATIONS_EN).filter(([, v]) => !v)
    expect(empty).toEqual([])
  })

  it('no empty translation values in Turkish', () => {
    const empty = Object.entries(TRANSLATIONS_TR).filter(([, v]) => !v)
    expect(empty).toEqual([])
  })
})
