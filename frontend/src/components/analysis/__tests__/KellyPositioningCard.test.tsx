import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KellyPositioningCard } from '../KellyPositioningCard'

describe('KellyPositioningCard', () => {
  it('returns null when kellySize is 0', () => {
    const { container } = render(<KellyPositioningCard kellySize={0} />)
    expect(container.innerHTML).toBe('')
  })

  it('returns null when kellySize is negative', () => {
    const { container } = render(<KellyPositioningCard kellySize={-0.5} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders kelly percentage', () => {
    render(<KellyPositioningCard kellySize={0.25} />)
    expect(screen.getByText('25.00%')).toBeInTheDocument()
    expect(screen.getByText(/of portfolio/)).toBeInTheDocument()
  })

  it('renders suggested capital when provided', () => {
    render(<KellyPositioningCard kellySize={0.15} suggestedCapital={15000} />)
    expect(screen.getByText('15.00%')).toBeInTheDocument()
    expect(screen.getByText('$15,000.00')).toBeInTheDocument()
  })

  it('does not render suggested capital when zero', () => {
    render(<KellyPositioningCard kellySize={0.10} suggestedCapital={0} />)
    expect(screen.getByText('10.00%')).toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })
})
