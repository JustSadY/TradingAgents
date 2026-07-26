import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MentalModelTicker } from '../MentalModelTicker'

describe('MentalModelTicker', () => {
  it('returns null when thought is empty', () => {
    const { container } = render(<MentalModelTicker agent="Analyst" thought="" />)
    expect(container.innerHTML).toBe('')
  })

  it('renders agent name and thought text', () => {
    render(<MentalModelTicker agent="Market Analyst" thought="The trend is showing strong momentum." />)
    expect(screen.getByText(/Market Analyst Thought/)).toBeInTheDocument()
    expect(screen.getByText('The trend is showing strong momentum.')).toBeInTheDocument()
  })

  it('renders with different agent name', () => {
    render(<MentalModelTicker agent="Risk Manager" thought="Volatility is increasing." />)
    expect(screen.getByText(/Risk Manager Thought/)).toBeInTheDocument()
  })
})
