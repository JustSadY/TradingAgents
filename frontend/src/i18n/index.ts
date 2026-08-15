export type Language = 'en' | 'tr'

type TranslationModule = { default?: { en?: Record<string, string>; tr?: Record<string, string> } }

// Every sibling module is a locale bundle. Globbing rather than listing them
// means a new file is picked up by the runtime and by the parity test at the
// same moment — a hand-maintained list previously let the two drift.
const modules = import.meta.glob<TranslationModule>(['./*.ts', '!./index.ts'], { eager: true })

function load(): Record<Language, Record<string, string>> {
  const merged: Record<Language, Record<string, string>> = { en: {}, tr: {} }
  for (const module of Object.values(modules)) {
    const bundle = module.default
    if (!bundle) continue
    Object.assign(merged.en, bundle.en || {})
    Object.assign(merged.tr, bundle.tr || {})
  }
  return merged
}

/**
 * The merged translation table.
 *
 * This is the single source of truth: `LanguageContext` resolves `t()` against
 * it and `__tests__/i18n.test.ts` checks en/tr parity against it, so the test
 * validates what actually ships rather than a copy of it.
 */
export const TRANSLATIONS = load()
