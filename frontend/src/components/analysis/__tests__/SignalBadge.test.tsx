import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SignalBadge } from '../SignalBadge'

const mockMeta = {
  signals: [
    { value: 'Buy', label: 'Buy', tone: 'positive' },
    { value: 'Sell', label: 'Sell', tone: 'negative' },
  ],
}

vi.mock('../../../hooks/useMeta', () => ({
  useMeta: vi.fn(() => mockMeta as any),
}))

describe('SignalBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when signal is null', () => {
    const { container } = render(<SignalBadge signal={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null when signal is empty string', () => {
    const { container } = render(<SignalBadge signal="" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders Buy signal with positive tone', () => {
    render(<SignalBadge signal="Buy" />)
    const el = screen.getByText('Buy')
    expect(el).toBeInTheDocument()
    expect(el.className).toContain('text-emerald-400')
  })

  it('renders Sell signal with negative tone', () => {
    render(<SignalBadge signal="Sell" />)
    const el = screen.getByText('Sell')
    expect(el).toBeInTheDocument()
    expect(el.className).toContain('text-rose-400')
  })

  it('uses label from meta instead of raw signal value', () => {
    mockMeta.signals.push({ value: 'Overweight', label: 'Overweight', tone: 'positive' })
    render(<SignalBadge signal="Overweight" />)
    expect(screen.getByText('Overweight')).toBeInTheDocument()
  })

  it('renders unknown signal without tone-specific classes', () => {
    render(<SignalBadge signal="Unknown" />)
    const el = screen.getByText('Unknown')
    expect(el.className).toContain('text-slate-400')
  })

  it('renders large variant with bigger padding', () => {
    render(<SignalBadge signal="Buy" large />)
    const el = screen.getByText('Buy')
    expect(el.className).toContain('px-4')
    expect(el.className).toContain('text-sm')
  })

  it('renders small variant by default', () => {
    render(<SignalBadge signal="Buy" />)
    const el = screen.getByText('Buy')
    expect(el.className).toContain('px-2.5')
    expect(el.className).toContain('text-[10px')
  })
})
