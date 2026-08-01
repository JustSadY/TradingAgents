import { useState, type ReactNode } from 'react'
import { TrendingUp, TrendingDown, Zap, Shield, Scale, User } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'

export interface DebateMessage { sender: string; content: string }

const SPEAKER_PATTERN =
  'bull(?:\\s+(?:researcher|analyst))?' +
  '|bear(?:\\s+(?:researcher|analyst))?' +
  '|aggressive(?:\\s+(?:risk\\s+)?(?:analyst|debator))?' +
  '|conservative(?:\\s+(?:risk\\s+)?(?:analyst|debator))?' +
  '|neutral(?:\\s+(?:risk\\s+)?(?:analyst|debator))?' +
  '|(?:portfolio\\s+)?manager' +
  '|system'

const SPEAKER_HEADER = new RegExp(
  `^\\s*(?:#{1,6}\\s*)?(?:\\d+[.)]\\s*)?(?:[-*]\\s+)?(?:\\*{1,3}\\s*)?(${SPEAKER_PATTERN})(?:\\s*\\*{1,3})?\\s*(?::|[—–-]\\s+|$)`,
  'im',
)

function canonicalSender(value: unknown, fallback = 'System'): string {
  const key = String(value ?? '').trim().toLowerCase().replace(/[\s_\-:*#]/g, '')
  if (key === 'bull' || key === 'bullanalyst' || key === 'bullresearcher') return 'Bull Analyst'
  if (key === 'bear' || key === 'bearanalyst' || key === 'bearresearcher') return 'Bear Analyst'
  if (key === 'aggressive' || key === 'aggressiveanalyst' || key === 'aggressiveriskanalyst' || key === 'aggressivedebator') return 'Aggressive Analyst'
  if (key === 'conservative' || key === 'conservativeanalyst' || key === 'conservativeriskanalyst' || key === 'conservativedebator') return 'Conservative Analyst'
  if (key === 'neutral' || key === 'neutralanalyst' || key === 'neutralriskanalyst' || key === 'neutraldebator') return 'Neutral Analyst'
  if (key === 'portfoliomanager' || key === 'manager') return 'Portfolio Manager'
  if (key === 'system') return 'System'
  return String(value ?? '').trim() || fallback
}

function cleanContent(value: unknown, sender?: string): string {
  let content = String(value ?? '').replace(/\r\n/g, '\n').trim()
  if (!content) return ''

  // The backend adds the speaker label. Remove the common provider habit of
  // repeating it as a Markdown title inside the same message bubble.
  const duplicate = content.match(SPEAKER_HEADER)
  if (duplicate && (!sender || canonicalSender(duplicate[1]) === canonicalSender(sender))) {
    content = content.slice(duplicate[0].length).replace(/^[\s:—–-]+/, '').trim()
  }
  // Legacy rows can contain a dangling Markdown delimiter after the role
  // label: "Aggressive Analyst: **\nactual response". It is a formatting
  // artifact, not emphasis content. Keep real bold text such as
  // "**Upside:** ..." unchanged.
  content = content.replace(/^(?:\*{1,3}|_{1,3})[ \t]*(?:\n+|$)/, '').trim()
  return content
}

function parseKnownHeader(value: string): DebateMessage | null {
  const match = value.match(SPEAKER_HEADER)
  if (!match) return null
  const sender = canonicalSender(match[1])
  return { sender, content: cleanContent(value.slice(match[0].length), sender) }
}

export function parseDebateMessage(msg: string): DebateMessage {
  const known = parseKnownHeader(msg)
  if (known) return known
  const separator = msg.indexOf(': ')
  if (separator >= 0) {
    return {
      sender: canonicalSender(msg.slice(0, separator)),
      content: cleanContent(msg.slice(separator + 2)),
    }
  }
  return { sender: 'System', content: cleanContent(msg) }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Accept both the new structured transcript and older newline-delimited rows.
 * Only a known speaker header starts a new bubble, so Markdown paragraphs and
 * bullet lists remain inside the analyst response that produced them.
 */
export function parseDebateHistory(history: unknown): DebateMessage[] {
  if (!history) return []
  if (isRecord(history)) {
    if (typeof history.sender === 'string' && history.content !== undefined) {
      const sender = canonicalSender(history.sender)
      const content = cleanContent(history.content, sender)
      return content ? [{ sender, content }] : []
    }
    return []
  }
  if (Array.isArray(history)) return history.flatMap(parseDebateHistory)
  if (typeof history !== 'string') return []

  const text = history.replace(/\r\n/g, '\n').trim()
  if (!text) return []
  if (text.startsWith('[') || text.startsWith('{')) {
    try { return parseDebateHistory(JSON.parse(text)) } catch { /* legacy prose; parse below */ }
  }

  const messages: DebateMessage[] = []
  let current: DebateMessage | null = null
  const prefix: string[] = []
  const pushCurrent = () => {
    if (!current) return
    current.content = cleanContent(current.content, current.sender)
    if (current.content) messages.push(current)
    current = null
  }

  for (const line of text.split('\n')) {
    const header = parseKnownHeader(line)
    if (header) {
      pushCurrent()
      current = header
      continue
    }
    if (current) {
      current.content += `${current.content ? '\n' : ''}${line}`
    } else {
      prefix.push(line)
    }
  }
  pushCurrent()

  const leading = cleanContent(prefix.join('\n'))
  if (leading) messages.unshift({ sender: 'System', content: leading })
  return messages.length ? messages : [{ sender: 'System', content: text }]
}

export function getSenderStyles(sender: string) {
  switch (canonicalSender(sender)) {
    case 'Bull Analyst':
      return {
        bg: 'bg-emerald-500/5 border-emerald-500/15 text-emerald-100 rounded-tl-none',
        side: 'justify-start',
        icon: <TrendingUp size={11} className="text-emerald-400 shrink-0" />,
      }
    case 'Bear Analyst':
      return {
        bg: 'bg-rose-500/5 border-rose-500/15 text-rose-100 rounded-tr-none',
        side: 'justify-end',
        icon: <TrendingDown size={11} className="text-rose-400 shrink-0" />,
      }
    case 'Aggressive Analyst':
      return {
        bg: 'bg-amber-500/5 border-amber-500/15 text-amber-100 rounded-tl-none',
        side: 'justify-start',
        icon: <Zap size={11} className="text-amber-400 shrink-0" />,
      }
    case 'Conservative Analyst':
      return {
        bg: 'bg-indigo-500/5 border-indigo-500/15 text-indigo-100 rounded-tr-none',
        side: 'justify-end',
        icon: <Shield size={11} className="text-indigo-400 shrink-0" />,
      }
    case 'Neutral Analyst':
      return {
        bg: 'bg-slate-800/40 border-slate-700/30 text-slate-200',
        side: 'justify-center mx-auto',
        icon: <Scale size={11} className="text-slate-400 shrink-0" />,
      }
    default:
      return {
        bg: 'bg-slate-900/60 border-white/[0.03] text-slate-300',
        side: 'justify-center mx-auto',
        icon: <User size={11} className="text-slate-500 shrink-0" />,
      }
  }
}

function inlineMarkdown(value: string): ReactNode[] {
  const parts = value.split(/(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\*[^*\n]+\*|_[^_\n]+_)/g)
  return parts.map((part, index) => {
    if (/^\*\*[^*\n]+\*\*$/.test(part) || /^__[^_\n]+__$/.test(part)) {
      return <strong key={index} className="font-semibold text-inherit">{part.slice(2, -2)}</strong>
    }
    if (/^`[^`\n]+`$/.test(part)) {
      return <code key={index} className="rounded bg-black/20 px-1 py-0.5 font-mono text-[0.92em]">{part.slice(1, -1)}</code>
    }
    if (/^\*[^*\n]+\*$/.test(part) || /^_[^_\n]+_$/.test(part)) {
      return <em key={index}>{part.slice(1, -1)}</em>
    }
    return part
  })
}

function DebateContent({ content }: { content: string }) {
  return (
    <div className="space-y-1.5 leading-relaxed whitespace-pre-wrap break-words">
      {content.split('\n').map((line, index) => {
        const heading = line.match(/^\s*#{1,6}\s+(.+)$/)
        const bullet = line.match(/^\s*[-*]\s+(.+)$/)
        if (heading) {
          return <p key={index} className="font-semibold text-[11px]">{inlineMarkdown(heading[1])}</p>
        }
        if (bullet) {
          return <p key={index} className="pl-3 relative before:content-['•'] before:absolute before:left-0 before:opacity-70">{inlineMarkdown(bullet[1])}</p>
        }
        return <p key={index}>{line ? inlineMarkdown(line) : '\u00a0'}</p>
      })}
    </div>
  )
}

function speakerTranslationKey(sender: string): string | null {
  switch (canonicalSender(sender)) {
    case 'Bull Analyst': return 'analysis.debate.speaker.bull'
    case 'Bear Analyst': return 'analysis.debate.speaker.bear'
    case 'Aggressive Analyst': return 'analysis.debate.speaker.aggressive'
    case 'Conservative Analyst': return 'analysis.debate.speaker.conservative'
    case 'Neutral Analyst': return 'analysis.debate.speaker.neutral'
    case 'Portfolio Manager': return 'analysis.debate.speaker.portfolio_manager'
    case 'System': return 'analysis.debate.speaker.system'
    default: return null
  }
}

export function DebateBubble({ message }: { message: DebateMessage }) {
  const { t } = useTranslation()
  const styles = getSenderStyles(message.sender)
  const canonical = canonicalSender(message.sender)
  const speakerKey = speakerTranslationKey(canonical)
  return (
    <div className={`flex w-full ${styles.side}`}>
      <article className={`border rounded-2xl px-4 py-3 text-xs flex flex-col gap-1.5 min-w-0 max-w-[94%] sm:max-w-[85%] ${styles.bg}`}>
        <span className="font-bold uppercase tracking-wider text-[9px] opacity-80 flex items-center gap-1">
          {styles.icon} {speakerKey ? t(speakerKey) : canonical}
        </span>
        <DebateContent content={message.content} />
      </article>
    </div>
  )
}

export function DebateHistoryWidget({ investmentHistory, riskHistory }: { investmentHistory: unknown; riskHistory: unknown }) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<'inv' | 'risk'>('inv')
  const activeHistory = parseDebateHistory(activeTab === 'inv' ? investmentHistory : riskHistory)

  return (
    <div className="flex flex-col bg-slate-950/80 border border-white/[0.04] rounded-2xl overflow-hidden p-4 space-y-4">
      <div className="flex gap-2 p-1 bg-slate-900/50 border border-white/[0.04] rounded-xl w-fit max-w-full self-center overflow-x-auto">
        <button
          onClick={() => setActiveTab('inv')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer whitespace-nowrap ${
            activeTab === 'inv' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          {t('analysis.debate.consensus')}
        </button>
        <button
          onClick={() => setActiveTab('risk')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer whitespace-nowrap ${
            activeTab === 'risk' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          {t('analysis.section.risk_debate_history')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 max-h-[52vh] pr-1">
        {activeHistory.length === 0 && (
          <p className="text-slate-600 text-xs text-center py-12">{t('analysis.reports.empty')}</p>
        )}
        {activeHistory.map((message, index) => <DebateBubble key={`${message.sender}-${index}`} message={message} />)}
      </div>
    </div>
  )
}
