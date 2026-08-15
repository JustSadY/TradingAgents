import React, { useState, useEffect, useRef } from 'react'
import { useAnalysisGetAnalysisChat, useAnalysisAskAnalysisReport } from '../../api/generated/analysis/analysis'
import { MessageSquare, Loader2 } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'
import { notify } from '../../utils/notify'

export function AnalysisChatWidget({ analysisId }: { analysisId: number }) {
  const { t } = useTranslation()
  type ChatMessage = { id: number; role: 'user' | 'assistant'; content: string }
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // History is server state; the local list additionally holds the optimistic
  // user message that is shown before the assistant replies.
  const history = useAnalysisGetAnalysisChat(analysisId)
  useEffect(() => {
    if (history.data) setMessages(history.data as ChatMessage[])
  }, [history.data])

  const askMutation = useAnalysisAskAnalysisReport()
  const loading = askMutation.isPending

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = (e?: React.FormEvent) => {
    e?.preventDefault()
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')

    const tempUserMsg = { id: Date.now(), role: 'user' as const, content: msg }
    setMessages(prev => [...prev, tempUserMsg])

    askMutation.mutate(
      { analysisId, data: { message: msg } },
      {
        onSuccess: (data) => setMessages(prev => [...prev, data as ChatMessage]),
        onError: (err) => {
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          notify('error', detail || t('analysis.chat.error') || 'Chat error', 'Hata')
        },
      },
    )
  }

  return (
    <div className="flex flex-col h-[48vh] bg-slate-950/80 border border-white/[0.04] rounded-2xl overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-600">
            <MessageSquare size={26} className="text-violet-500/30 mb-2 animate-pulse" />
            <p className="text-xs font-semibold text-slate-400">{t('analysis.chat.welcome_title')}</p>
            <p className="text-[10px] text-slate-600 max-w-xs mt-1 leading-relaxed">{t('analysis.chat.welcome_desc')}</p>
          </div>
        )}
        {messages.map(m => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs leading-relaxed select-text ${
              m.role === 'user'
                ? 'bg-violet-600 text-white rounded-tr-none'
                : 'bg-white/5 text-slate-200 border border-white/[0.04] rounded-tl-none'
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/5 text-slate-400 border border-white/[0.04] rounded-2xl rounded-tl-none px-4 py-2.5 text-xs flex items-center gap-2">
              <Loader2 className="animate-spin" size={12} />
              {t('analysis.chat.thinking')}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSend} className="p-3 border-t border-white/[0.04] bg-slate-900/40 flex gap-2 shrink-0">
        <input
          className="flex-1 glass-input rounded-xl px-3 py-2 text-xs outline-none"
          placeholder={t('analysis.chat.placeholder')}
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-semibold px-4 py-2 rounded-xl transition cursor-pointer"
        >
          {t('analysis.chat.send')}
        </button>
      </form>
    </div>
  )
}
