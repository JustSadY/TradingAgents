import { describe, it, expect } from 'vitest'
import { TRANSLATIONS_EN, TRANSLATIONS_TR } from './i18n-data'

describe('i18n translation coverage', () => {
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
