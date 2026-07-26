import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReportCard } from '../ReportCard'

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

describe('ReportCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when content is empty', () => {
    const { container } = render(<ReportCard label="Analysis" content="" />)
    expect(container.innerHTML).toBe('')
  })

  it('renders label and content', () => {
    render(<ReportCard label="Market Analysis" content="The market is bullish." />)
    expect(screen.getByText('Market Analysis')).toBeInTheDocument()
    expect(screen.getByText('The market is bullish.')).toBeInTheDocument()
  })

  it('shows toggle text for expand/collapse', () => {
    render(<ReportCard label="Report" content="Some detailed content here." />)
    expect(screen.getByText('analysis.report_card.show')).toBeInTheDocument()
  })

  it('renders image when IMAGE_DATA is present', () => {
    const content = 'Text before\nIMAGE_DATA: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAAA0lEQVQI12P4z8BQDwAEgAF/QualzQAAAABJRU5ErkJggg==\nText after'
    render(<ReportCard label="Chart" content={content} />)
    const img = screen.getByAltText('Chart Analysis')
    expect(img).toBeInTheDocument()
    expect(img).toHaveAttribute('src', expect.stringContaining('data:image/png;base64'))
  })

  it('shows streaming placeholder when isStreaming with IMAGE_DATA', () => {
    const content = 'IMAGE_DATA: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAAA0lEQVQI12P4z8BQDwAEgAF/QualzQAAAABJRU5ErkJggg=='
    render(<ReportCard label="Chart" content={content} isStreaming={true} />)
    expect(screen.getByText(/Generating chart visualization/)).toBeInTheDocument()
  })

  it('starts open when defaultOpen is true', () => {
    render(<ReportCard label="Report" content="Default open content" defaultOpen={true} />)
    const pre = screen.getByText('Default open content')
    expect(pre).toBeInTheDocument()
  })
})
