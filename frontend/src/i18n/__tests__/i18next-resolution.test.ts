import { describe, it, expect } from 'vitest'
import i18n, { TRANSLATIONS, DEFAULT_LANGUAGE } from '../index'

/**
 * Guards the i18next configuration against the failure mode it is most exposed
 * to: every key in this project is a dotted string like `analysis.strategy.bias`
 * stored in a flat object, so dropping `keySeparator: false` would make i18next
 * read the dots as a path into nested resources and resolve nothing. That would
 * render raw key strings across the entire UI while every parity test still
 * passed, since those only compare the resource table to itself.
 */
describe('i18next key resolution', () => {
  it('returns the exact table value for every key in both locales', async () => {
    const mismatches: string[] = []

    for (const lng of ['en', 'tr'] as const) {
      await i18n.changeLanguage(lng)
      for (const [key, expected] of Object.entries(TRANSLATIONS[lng])) {
        const actual = i18n.t(key)
        if (actual !== expected) {
          mismatches.push(`[${lng}] ${key}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`)
        }
      }
    }

    if (mismatches.length > 0) {
      console.error(mismatches.slice(0, 15).join('\n'))
    }
    expect(mismatches).toEqual([])
  })

  it('resolves dotted keys rather than treating the dots as nesting', async () => {
    await i18n.changeLanguage('en')
    expect(i18n.t('analysis.strategy.bias')).toBe(TRANSLATIONS.en['analysis.strategy.bias'])
    expect(i18n.t('nav.section.trading_desk')).toBe(TRANSLATIONS.en['nav.section.trading_desk'])
  })

  it('falls back to English for a key missing from the active locale', async () => {
    const probe = '__fallback_probe__'
    i18n.addResource(DEFAULT_LANGUAGE, 'translation', probe, 'English only')
    await i18n.changeLanguage('tr')
    expect(i18n.t(probe)).toBe('English only')
    i18n.removeResourceBundle('tr', 'translation')
    i18n.addResourceBundle('tr', 'translation', TRANSLATIONS.tr)
  })

  it('echoes an unknown key instead of rendering empty', async () => {
    await i18n.changeLanguage('tr')
    expect(i18n.t('definitely.not.a.real.key')).toBe('definitely.not.a.real.key')
  })

  it('interpolates values, which the previous hand-rolled t() could not do', async () => {
    await i18n.changeLanguage('en')
    i18n.addResource('en', 'translation', '__interp_probe__', 'Next run at {{time}}')
    expect(i18n.t('__interp_probe__', { time: '09:30' })).toBe('Next run at 09:30')
  })
})
