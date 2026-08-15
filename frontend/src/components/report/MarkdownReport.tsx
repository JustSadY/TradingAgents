import type { ReactNode } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { safeImageSrc, safeLinkHref } from '../../utils/safeUrl'

interface MarkdownReportProps {
  content: string
  className?: string
}

/**
 * Markdown renderer for AI report text.
 *
 * Report content is untrusted model output. Two properties keep it safe and
 * both are load-bearing:
 *
 * 1. `rehype-raw` is deliberately **not** installed, so react-markdown leaves
 *    embedded HTML as literal text. Scripts, event handlers and injected
 *    markup stay inert rather than becoming elements.
 * 2. `urlTransform` runs every link and image target through the allow-lists
 *    below, so `javascript:`, `data:` and similar schemes never reach an
 *    `href` or `src`.
 *
 * Anything rejected falls back to rendering the label as plain text, which is
 * what the previous hand-written parser did.
 */
export function MarkdownReport({ content, className = '' }: MarkdownReportProps) {
  return (
    <div className={`markdown-report text-sm leading-7 text-slate-300 break-words ${className}`}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        urlTransform={transformUrl}
        components={components}
      >
        {content}
      </Markdown>
    </div>
  )
}

/**
 * react-markdown passes the attribute name, which lets images keep their
 * stricter rule: a `mailto:` or bare fragment is a valid link but never a
 * valid image source.
 */
function transformUrl(url: string, key: string): string {
  const safe = key === 'src' ? safeImageSrc(url) : safeLinkHref(url)
  return safe ?? ''
}

const HEADING_CLASS = {
  h1: 'mt-6 mb-3 text-xl font-extrabold tracking-tight text-white',
  h2: 'mt-6 mb-2 text-lg font-bold text-white',
  h3: 'mt-5 mb-2 text-base font-bold text-slate-100',
} as const

const components = {
  h1: ({ children }: { children?: ReactNode }) => <h1 className={HEADING_CLASS.h1}>{children}</h1>,
  h2: ({ children }: { children?: ReactNode }) => <h2 className={HEADING_CLASS.h2}>{children}</h2>,
  h3: ({ children }: { children?: ReactNode }) => <h3 className={HEADING_CLASS.h3}>{children}</h3>,
  h4: ({ children }: { children?: ReactNode }) => <h4 className={HEADING_CLASS.h3}>{children}</h4>,
  h5: ({ children }: { children?: ReactNode }) => <h5 className={HEADING_CLASS.h3}>{children}</h5>,
  h6: ({ children }: { children?: ReactNode }) => <h6 className={HEADING_CLASS.h3}>{children}</h6>,

  p: ({ children }: { children?: ReactNode }) => <p className="my-3 whitespace-normal">{children}</p>,

  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-bold text-slate-100">{children}</strong>
  ),
  em: ({ children }: { children?: ReactNode }) => (
    <em className="italic text-slate-200">{children}</em>
  ),

  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="my-3 list-disc space-y-1 pl-5 marker:text-violet-300">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="my-3 list-decimal space-y-1 pl-5 marker:font-semibold marker:text-violet-300">{children}</ol>
  ),

  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="my-4 border-l-2 border-violet-400/70 bg-violet-500/[0.06] px-4 py-3 text-slate-300">
      {children}
    </blockquote>
  ),

  hr: () => <hr className="my-5 border-0 border-t border-white/[0.08]" />,

  // Fenced blocks arrive as <pre><code>; inline code arrives on its own. Only
  // the inline form is styled here, because `pre` owns the block presentation.
  code: ({ children, className: codeClassName }: { children?: ReactNode; className?: string }) => {
    const isBlock = Boolean(codeClassName?.startsWith('language-'))
    if (isBlock) return <code className={codeClassName}>{children}</code>
    return (
      <code className="rounded bg-black/35 px-1.5 py-0.5 font-mono text-[0.9em] text-violet-200">
        {children}
      </code>
    )
  },
  pre: ({ children }: { children?: ReactNode }) => (
    <pre className="my-4 overflow-x-auto rounded-xl border border-white/[0.08] bg-black/35 p-4 text-xs leading-6 text-slate-200">
      {children}
    </pre>
  ),

  table: ({ children }: { children?: ReactNode }) => (
    <div className="my-4 overflow-x-auto rounded-xl border border-white/[0.08]">
      <table className="w-full min-w-[420px] border-collapse text-left text-xs leading-6">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: ReactNode }) => (
    <thead className="bg-white/[0.05] text-slate-100">{children}</thead>
  ),
  tbody: ({ children }: { children?: ReactNode }) => (
    <tbody className="divide-y divide-white/[0.05]">{children}</tbody>
  ),
  tr: ({ children }: { children?: ReactNode }) => (
    <tr className="align-top transition-colors hover:bg-white/[0.025]">{children}</tr>
  ),
  th: ({ children }: { children?: ReactNode }) => (
    <th className="border-b border-white/[0.08] px-3 py-2.5 font-bold">{children}</th>
  ),
  td: ({ children }: { children?: ReactNode }) => (
    <td className="px-3 py-2 text-slate-300">{children}</td>
  ),

  // A rejected target renders its label as text rather than an unusable link.
  a: ({ href, children }: { href?: string; children?: ReactNode }) => {
    if (!href) return <>{children}</>
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        className="font-medium text-violet-300 underline decoration-violet-400/45 underline-offset-2 transition-colors hover:text-violet-200"
      >
        {children}
      </a>
    )
  },

  img: ({ src, alt }: { src?: string; alt?: string }) => {
    if (!src) return <>{alt || 'Image'}</>
    return (
      <img
        src={src}
        alt={alt ?? ''}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        className="my-3 max-h-[34rem] max-w-full rounded-xl border border-white/[0.08] bg-black/20 object-contain"
      />
    )
  },
}
