import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MarkdownReport } from '../MarkdownReport'

describe('MarkdownReport', () => {
  it('renders the Markdown structures used in shared AI reports', () => {
    render(
      <MarkdownReport content={[
        '# Market outlook',
        '',
        'Momentum is **constructive** with `NVDA` above support.',
        '',
        '- First catalyst',
        '- Second catalyst',
        '',
        '1. Define risk',
        '2. Size the position',
        '',
        '| Metric | Value |',
        '| --- | ---: |',
        '| P/E | 30.1 |',
        '',
        '> Keep the stop below support.',
        '',
        '```text',
        'Risk / reward: 2.1',
        '```',
        '',
        '![Price chart](https://example.com/chart.png)',
        '',
        '[Read source](https://example.com/research)',
      ].join('\n')} />,
    )

    expect(screen.getByRole('heading', { name: 'Market outlook' })).toBeInTheDocument()
    expect(screen.getByText('constructive').tagName).toBe('STRONG')
    expect(screen.getByText('NVDA').tagName).toBe('CODE')
    expect(screen.getAllByRole('list')).toHaveLength(2)
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('Keep the stop below support.').closest('blockquote')).not.toBeNull()
    expect(screen.getByText('Risk / reward: 2.1').closest('pre')).not.toBeNull()
    expect(screen.getByRole('img', { name: 'Price chart' })).toHaveAttribute('src', 'https://example.com/chart.png')
    expect(screen.getByRole('link', { name: 'Read source' })).toHaveAttribute('href', 'https://example.com/research')
  })

  it('keeps model-supplied HTML and unsafe links inert', () => {
    const { container } = render(
      <MarkdownReport content={'<script>alert(1)</script>\n\n[Unsafe](javascript:alert(1))\n\n![Unsafe image](javascript:alert(1))\n\n[Safe](https://example.com)'} />,
    )

    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull()
    expect(screen.queryByRole('link', { name: 'Unsafe' })).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Unsafe image' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Safe' })).toHaveAttribute('href', 'https://example.com')
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
  })
})
