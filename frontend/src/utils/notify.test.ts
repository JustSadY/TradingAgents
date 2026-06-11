import { describe, expect, it } from 'vitest'
import { formatErrorDetail } from './notify'

describe('formatErrorDetail', () => {
  it('returns plain strings unchanged', () => {
    expect(formatErrorDetail('boom')).toBe('boom')
  })

  it('falls back for null and undefined', () => {
    expect(formatErrorDetail(null)).toBe('Unknown error')
    expect(formatErrorDetail(undefined)).toBe('Unknown error')
  })

  it('formats FastAPI validation arrays and strips body/query from loc', () => {
    const detail = [
      { loc: ['body', 'ticker'], msg: 'field required' },
      { loc: ['query', 'limit'], msg: 'value is not a valid integer' },
    ]
    expect(formatErrorDetail(detail)).toBe('ticker: field required, limit: value is not a valid integer')
  })

  it('joins nested loc segments with dots', () => {
    expect(formatErrorDetail([{ loc: ['body', 'settings', 'llm_model'], msg: 'invalid' }])).toBe(
      'settings.llm_model: invalid'
    )
  })

  it('unwraps nested detail objects recursively', () => {
    expect(formatErrorDetail({ detail: { detail: 'inner cause' } })).toBe('inner cause')
  })

  it('prefers message over msg on plain objects', () => {
    expect(formatErrorDetail({ message: 'a', msg: 'b' })).toBe('a')
    expect(formatErrorDetail({ msg: 'b' })).toBe('b')
  })

  it('stringifies objects without known fields', () => {
    expect(formatErrorDetail({ code: 42 })).toBe('{"code":42}')
  })
})
