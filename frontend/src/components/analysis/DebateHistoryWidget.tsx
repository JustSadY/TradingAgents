import { useState } from 'react'
import { TrendingUp, TrendingDown, Zap, Shield, Scale, User } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'

interface DebateMessage { sender: string; content: string }

export function parseDebateMessage(msg: string): DebateMessage {
  const parts = msg.split(': ')
  if (parts.length >= 2) {
    const sender = parts[0].trim()
    const content = parts.slice(1).join(': ').trim()
    return { sender, content }
  }
  return { sender: 'System', content: msg }
}

export function getSenderStyles(sender: string) {
  switch (sender) {
    case 'Bull Analyst':
    case 'BullResearcher':
      return {
        bg: 'bg-emerald-500/5 border-emerald-500/15 text-emerald-300 rounded-tl-none',
        side: 'justify-start',
        icon: <TrendingUp size={11} className="text-emerald-400 shrink-0" />
      }
    case 'Bear Analyst':
    case 'BearResearcher':
      return {
        bg: 'bg-rose-500/5 border-rose-500/15 text-rose-300 rounded-tr-none',
        side: 'justify-end',
        icon: <TrendingDown size={11} className="text-rose-400 shrink-0" />
      }
    case 'Aggressive Analyst':
    case 'AggressiveDebator':
      return {
        bg: 'bg-amber-500/5 border-amber-500/15 text-amber-300 rounded-tl-none',
        side: 'justify-start',
        icon: <Zap size={11} className="text-amber-400 shrink-0" />
      }
    case 'Conservative Analyst':
    case 'ConservativeDebator':
      return {
        bg: 'bg-indigo-500/5 border-indigo-500/15 text-indigo-300 rounded-tr-none',
        side: 'justify-end',
        icon: <Shield size={11} className="text-indigo-400 shrink-0" />
      }
    case 'Neutral Analyst':
    case 'NeutralDebator':
      return {
        bg: 'bg-slate-800/40 border-slate-700/30 text-slate-300',
        side: 'justify-center mx-auto max-w-[90%]',
        icon: <Scale size={11} className="text-slate-400 shrink-0" />
      }
    default:
      return {
        bg: 'bg-slate-900/60 border-white/[0.03] text-slate-400',
        side: 'justify-center mx-auto',
        icon: <User size={11} className="text-slate-500 shrink-0" />
      }
  }
}

export function DebateHistoryWidget({ investmentHistory, riskHistory }: { investmentHistory: any; riskHistory: any }) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<'inv' | 'risk'>('inv')

  const parseLines = (historyStr: any): DebateMessage[] => {
    if (!historyStr) return []
    if (typeof historyStr === 'string' && historyStr.trim().startsWith('[')) {
      try {
        const parsed = JSON.parse(historyStr)
        if (Array.isArray(parsed)) return parsed.map((msg: string) => parseDebateMessage(msg))
      } catch { /* not JSON — fall through */ }
    }
    if (typeof historyStr !== 'string') {
        if (Array.isArray(historyStr)) return historyStr.map((msg: any) => parseDebateMessage(String(msg)))
        return []
    }
    return historyStr
      .split('\n')
      .map((line: string) => line.trim())
      .filter((line: string) => line.length > 0)
      .map((line: string) => parseDebateMessage(line))
  }

  const activeHistory = activeTab === 'inv' ? parseLines(investmentHistory) : parseLines(riskHistory)

  return (
    <div className="flex flex-col bg-slate-950/80 border border-white/[0.04] rounded-2xl overflow-hidden p-4 space-y-4">
      <div className="flex gap-2 p-1 bg-slate-900/50 border border-white/[0.04] rounded-xl w-fit self-center">
        <button
          onClick={() => setActiveTab('inv')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer ${
            activeTab === 'inv' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          Consensus Debate
        </button>
        <button
          onClick={() => setActiveTab('risk')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer ${
            activeTab === 'risk' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          {t('analysis.section.risk_debate_history')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 max-h-[45vh] pr-1">
        {activeHistory.length === 0 && (
          <p className="text-slate-600 text-xs text-center py-12">{t('analysis.reports.empty')}</p>
        )}
        {activeHistory.map((m: DebateMessage, idx: number) => {
          const styles = getSenderStyles(m.sender)
          return (
            <div key={idx} className={`flex ${styles.side}`}>
              <div className={`border rounded-2xl px-4 py-2.5 text-xs flex flex-col gap-1 max-w-[85%] ${styles.bg}`}>
                <span className="font-bold uppercase tracking-wider text-[9px] opacity-80 flex items-center gap-1">
                  {styles.icon} {m.sender}
                </span>
                <span className="leading-relaxed whitespace-pre-wrap">{m.content}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
