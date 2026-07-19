import { describe, it, expect } from 'vitest'
import { signalTone, SIGNAL_TONE, TONE_HEX, TONE_DOT_CLASS, TONE_TEXT_CLASS } from '../signalTone'

describe('signalTone', () => {
  it('maps Buy to positive', () => {
    expect(signalTone('Buy')).toBe('positive')
  })

  it('maps Overweight to positive', () => {
    expect(signalTone('Overweight')).toBe('positive')
  })

  it('maps Hold to neutral', () => {
    expect(signalTone('Hold')).toBe('neutral')
  })

  it('maps Neutral to neutral', () => {
    expect(signalTone('Neutral')).toBe('neutral')
  })

  it('maps Underweight to negative', () => {
    expect(signalTone('Underweight')).toBe('negative')
  })

  it('maps Sell to negative', () => {
    expect(signalTone('Sell')).toBe('negative')
  })

  it('returns neutral for unknown signal', () => {
    expect(signalTone('StrongBuy')).toBe('neutral')
  })

  it('returns neutral for null', () => {
    expect(signalTone(null)).toBe('neutral')
  })

  it('returns neutral for undefined', () => {
    expect(signalTone(undefined)).toBe('neutral')
  })
})

describe('SIGNAL_TONE', () => {
  it('contains all expected keys', () => {
    expect(Object.keys(SIGNAL_TONE)).toEqual(['Buy', 'Overweight', 'Hold', 'Neutral', 'Underweight', 'Sell'])
  })
})

describe('TONE_HEX', () => {
  it('has correct hex colors', () => {
    expect(TONE_HEX.positive).toBe('#10b981')
    expect(TONE_HEX.neutral).toBe('#f59e0b')
    expect(TONE_HEX.negative).toBe('#ef4444')
  })
})

describe('TONE_DOT_CLASS', () => {
  it('has correct tailwind classes', () => {
    expect(TONE_DOT_CLASS.positive).toBe('bg-emerald-500')
    expect(TONE_DOT_CLASS.neutral).toBe('bg-amber-500')
    expect(TONE_DOT_CLASS.negative).toBe('bg-rose-500')
  })
})

describe('TONE_TEXT_CLASS', () => {
  it('has correct tailwind classes', () => {
    expect(TONE_TEXT_CLASS.positive).toBe('text-emerald-400')
    expect(TONE_TEXT_CLASS.neutral).toBe('text-amber-400')
    expect(TONE_TEXT_CLASS.negative).toBe('text-rose-400')
  })
})
