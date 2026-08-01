import { describe, expect, it } from 'vitest'
import { buildPublicShareUrl } from '../shareLink'

describe('buildPublicShareUrl', () => {
  it('does not copy an unusable 0.0.0.0 bind address into a share link', () => {
    expect(buildPublicShareUrl('token value', 'http://0.0.0.0:5173'))
      .toBe('http://localhost:5173/share/token%20value')
  })

  it('uses the configured public URL when deployed behind a proxy', () => {
    expect(buildPublicShareUrl('abc', 'http://localhost:5173', 'https://reports.example.test'))
      .toBe('https://reports.example.test/share/abc')
  })

  it('keeps an optional public base path', () => {
    expect(buildPublicShareUrl('abc', 'http://localhost:5173', 'https://reports.example.test/tradingagents'))
      .toBe('https://reports.example.test/tradingagents/share/abc')
  })
})
