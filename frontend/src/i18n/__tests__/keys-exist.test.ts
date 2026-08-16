import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { TRANSLATIONS } from '../index'

/**
 * Every `t('some.key')` in the source must resolve.
 *
 * i18next returns the key itself when a translation is missing, and a key is a
 * truthy string, so the `t('x') || 'Fallback'` idiom this codebase used never
 * fired — a missing key renders as `watchlist.add_title` in the UI, and no test
 * noticed. This is the check those fallbacks were pretending to be.
 *
 * Only literal single-argument calls are checked. Keys built at runtime
 * (`t(`tools.category.${category}`)`, `t(field.label_key)`) come from API
 * metadata and cannot be resolved statically.
 */

const SOURCE_ROOT = join(import.meta.dirname, '../..')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap(entry => {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      return entry === 'generated' || entry === '__tests__' ? [] : sourceFiles(path)
    }
    return /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [path] : []
  })
}

/** `t('a.b')`, `translate('a.b')` and `i18n.t('a.b')`, single string literal. */
const CALL = /\b(?:i18n\.)?(?:t|translate)\(\s*'([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)'/g

function usedKeys(): Map<string, string[]> {
  const found = new Map<string, string[]>()
  for (const file of sourceFiles(SOURCE_ROOT)) {
    const source = readFileSync(file, 'utf8')
    for (const match of source.matchAll(CALL)) {
      const key = match[1]
      found.set(key, [...(found.get(key) ?? []), file.slice(SOURCE_ROOT.length + 1)])
    }
  }
  return found
}

describe('translation keys used in source', () => {
  const used = usedKeys()

  it('finds the call sites at all, so the assertions below are not vacuous', () => {
    expect(used.size).toBeGreaterThan(300)
  })

  it('every key resolves to an English translation', () => {
    const missing = [...used.entries()]
      .filter(([key]) => !(key in TRANSLATIONS.en))
      .map(([key, files]) => `${key} (${[...new Set(files)].join(', ')})`)

    expect(missing).toEqual([])
  })
})
