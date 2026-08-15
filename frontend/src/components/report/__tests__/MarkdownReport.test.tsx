import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MarkdownReport } from '../MarkdownReport'

/**
 * Report content is untrusted model output, so these tests pin two things: the
 * Markdown subset the report prompts actually produce, and the guarantee that
 * nothing in that content can escape into markup or a dangerous URL.
 */
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

  describe('headings', () => {
    it.each([
      ['# One', 1],
      ['## Two', 2],
      ['### Three', 3],
      ['#### Four', 4],
    ])('renders %s at the matching level', (source, level) => {
      const { container } = render(<MarkdownReport content={source} />)
      expect(container.querySelector(`h${level}`)).not.toBeNull()
    })

    it('renders inline emphasis inside a heading', () => {
      render(<MarkdownReport content={'## Outlook for **NVDA**'} />)
      expect(screen.getByText('NVDA').tagName).toBe('STRONG')
    })
  })

  describe('inline formatting', () => {
    it('supports both bold spellings', () => {
      render(<MarkdownReport content={'**stars** and __underscores__'} />)
      expect(screen.getByText('stars').tagName).toBe('STRONG')
      expect(screen.getByText('underscores').tagName).toBe('STRONG')
    })

    it('supports both italic spellings', () => {
      render(<MarkdownReport content={'*stars* and _underscores_'} />)
      expect(screen.getByText('stars').tagName).toBe('EM')
      expect(screen.getByText('underscores').tagName).toBe('EM')
    })

    it('nests emphasis inside a link label', () => {
      render(<MarkdownReport content={'[see **this**](https://example.com)'} />)
      expect(screen.getByText('this').tagName).toBe('STRONG')
      expect(screen.getByRole('link')).toHaveAttribute('href', 'https://example.com')
    })

    it('leaves inline code contents unformatted', () => {
      render(<MarkdownReport content={'`**not bold**`'} />)
      const code = screen.getByText('**not bold**')
      expect(code.tagName).toBe('CODE')
      expect(code.querySelector('strong')).toBeNull()
    })
  })

  describe('code blocks', () => {
    it('preserves contents verbatim', () => {
      render(<MarkdownReport content={'```\nline one\n  indented\n```'} />)
      expect(screen.getByText(/line one/).closest('pre')).not.toBeNull()
    })

    it('renders a fence with no language', () => {
      const { container } = render(<MarkdownReport content={'```\nplain\n```'} />)
      expect(container.querySelector('pre')).not.toBeNull()
    })
  })

  describe('lists', () => {
    it.each(['-', '+', '*'])('accepts %s as a bullet marker', marker => {
      render(<MarkdownReport content={`${marker} item one\n${marker} item two`} />)
      expect(screen.getAllByRole('listitem')).toHaveLength(2)
    })

    it('renders an ordered list', () => {
      const { container } = render(<MarkdownReport content={'1. first\n2. second'} />)
      expect(container.querySelector('ol')).not.toBeNull()
      expect(screen.getAllByRole('listitem')).toHaveLength(2)
    })
  })

  describe('tables', () => {
    it('keeps rows and columns aligned with the header', () => {
      render(<MarkdownReport content={'| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |'} />)
      expect(screen.getAllByRole('columnheader')).toHaveLength(2)
      expect(screen.getAllByRole('row')).toHaveLength(3)
    })

    it('renders inline formatting inside cells', () => {
      render(<MarkdownReport content={'| Metric |\n| --- |\n| **bold** |'} />)
      expect(screen.getByText('bold').tagName).toBe('STRONG')
    })

    it('does not treat a lone pipe line as a table', () => {
      const { container } = render(<MarkdownReport content={'a | b without separator'} />)
      expect(container.querySelector('table')).toBeNull()
    })
  })

  describe('other blocks', () => {
    it('renders a thematic break', () => {
      const { container } = render(<MarkdownReport content={'above\n\n---\n\nbelow'} />)
      expect(container.querySelector('hr')).not.toBeNull()
    })

    it('joins multi-line blockquotes into one block', () => {
      const { container } = render(<MarkdownReport content={'> first\n> second'} />)
      expect(container.querySelectorAll('blockquote')).toHaveLength(1)
    })

    it('renders empty content without crashing', () => {
      const { container } = render(<MarkdownReport content={''} />)
      expect(container).toBeInTheDocument()
    })
  })

  describe('untrusted content', () => {
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

    it('renders inline HTML as visible text rather than markup', () => {
      const { container } = render(
        <MarkdownReport content={'before <img src=x onerror="alert(1)"> after'} />,
      )
      expect(container.querySelector('img')).toBeNull()
      expect(container.textContent).toContain('onerror')
    })

    it.each([
      'javascript:alert(1)',
      'data:text/html;base64,PHNjcmlwdD4=',
      'vbscript:msgbox(1)',
    ])('refuses %s as a link target', href => {
      const { container } = render(<MarkdownReport content={`[x](${href})`} />)
      expect(container.querySelector('a')).toBeNull()
      expect(container.textContent).toContain('x')
    })

    it.each([
      ['https://example.com/a', 'absolute https'],
      ['http://example.com/a', 'absolute http'],
      ['mailto:a@example.com', 'mailto'],
      ['/relative/path', 'root-relative'],
      ['#anchor', 'fragment'],
    ])('allows %s (%s)', href => {
      const { container } = render(<MarkdownReport content={`[x](${href})`} />)
      expect(container.querySelector('a')).toHaveAttribute('href', href)
    })

    it('opens external links safely', () => {
      render(<MarkdownReport content={'[x](https://example.com)'} />)
      const link = screen.getByRole('link')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link.getAttribute('rel')).toContain('noopener')
      expect(link.getAttribute('rel')).toContain('noreferrer')
    })

    it('does not leak a referrer when loading report images', () => {
      render(<MarkdownReport content={'![chart](https://example.com/c.png)'} />)
      const image = screen.getByRole('img', { name: 'chart' })
      expect(image).toHaveAttribute('referrerpolicy', 'no-referrer')
      expect(image).toHaveAttribute('loading', 'lazy')
    })

    it('refuses a mailto or fragment as an image source', () => {
      const { container } = render(
        <MarkdownReport content={'![a](mailto:a@example.com)\n\n![b](#frag)'} />,
      )
      expect(container.querySelector('img')).toBeNull()
    })
  })
})
