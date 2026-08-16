import { TRANSLATIONS } from '../i18n'

/**
 * A `t` for tests that resolves against the real English table.
 *
 * The convention had been `t: (k) => k`, which meant assertions read like
 * `getByText('settings.save_tools')` — they pinned the key, not the sentence
 * a user sees, and a key with no translation behind it still passed. Resolving
 * for real keeps the assertions in English and makes a missing key fail.
 *
 * Unknown keys come back unchanged, matching i18next's own fallback, so a test
 * can still assert on a key the component invents at runtime.
 */
export function translate(key: string, options?: Record<string, unknown>): string {
  const template = TRANSLATIONS.en[key] ?? key
  if (!options) return template
  return template.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
    name in options ? String(options[name]) : match,
  )
}

/** Drop-in replacement for the `useTranslation` mock in component tests. */
export const useTranslationMock = () => ({
  t: translate,
  language: 'en' as const,
  setLanguage: () => {},
})
