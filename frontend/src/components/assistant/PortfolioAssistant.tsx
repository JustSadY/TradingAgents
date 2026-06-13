import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  BotMessageSquare, X, Send, Loader2, Trash2, TrendingUp,
  ChevronDown, Sparkles,
} from 'lucide-react'
import axios from 'axios'
import { useAuth } from '../../contexts/AuthContext'

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

const QUICK_PROMPTS = [
  "What's my portfolio balance?",
  "Show me my recent analyses",
  "Analyze NVDA for me",
  "Set an alert when AAPL goes above $200",
]

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} gap-2`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-lg bg-violet-500/20 border border-violet-500/20 flex items-center justify-center shrink-0 mt-0.5">
          <Sparkles size={11} className="text-violet-400" />
        </div>
      )}
      <div
        className={`max-w-[82%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed select-text ${
          isUser
            ? 'bg-violet-600 text-white rounded-tr-none'
            : 'bg-white/[0.05] text-slate-200 border border-white/[0.05] rounded-tl-none'
        }`}
        style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
      >
        {msg.content}
      </div>
    </div>
  )
}

export function PortfolioAssistant() {
  const { isAuthenticated } = useAuth()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const tempIdRef = useRef(-1)

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    if (!open || historyLoaded) return
    axios
      .get('/api/assistant/history')
      .then(r => {
        setMessages(r.data)
        setHistoryLoaded(true)
      })
      .catch(() => setHistoryLoaded(true))
  }, [open, historyLoaded])

  useEffect(() => {
    if (open) {
      setTimeout(scrollToBottom, 80)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open, scrollToBottom])

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading, scrollToBottom])

  const send = async (text?: string) => {
    const msg = (text ?? input).trim()
    if (!msg || loading) return
    setInput('')

    const tempId = tempIdRef.current--
    const tempUser: Message = { id: tempId, role: 'user', content: msg, created_at: '' }
    setMessages(prev => [...prev, tempUser])
    setLoading(true)

    try {
      const { data } = await axios.post<Message>('/api/assistant/chat', { message: msg })
      setMessages(prev => [...prev, data])
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Assistant error. Please try again.'
      const errMsg: Message = {
        id: tempIdRef.current--,
        role: 'assistant',
        content: `⚠ ${detail}`,
        created_at: '',
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    send()
  }

  const clearHistory = async () => {
    try {
      await axios.delete('/api/assistant/history')
      setMessages([])
    } catch {
      /* ignore */
    }
  }

  if (!isAuthenticated) return null

  return (
    <div className="fixed bottom-6 right-6 z-[48] flex flex-col items-end gap-3 pointer-events-none">
      {/* Chat panel */}
      {open && (
        <div
          className="pointer-events-auto w-[22rem] sm:w-96 bg-[#0a0f1e] border border-white/10 rounded-2xl shadow-2xl shadow-black/60 flex flex-col overflow-hidden"
          style={{ height: '520px' }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-[#0d1225]/90 shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-md shadow-violet-500/30">
                <TrendingUp size={13} className="text-white" strokeWidth={2.5} />
              </div>
              <div>
                <p className="text-[11px] font-bold text-white leading-none">Portfolio Assistant</p>
                <p className="text-[9px] text-slate-500 mt-0.5 uppercase tracking-wider">AI · TradingAgents</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={clearHistory}
                className="p-1.5 text-slate-600 hover:text-slate-300 rounded-lg hover:bg-white/5 transition"
                title="Clear history"
              >
                <Trash2 size={12} />
              </button>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 text-slate-600 hover:text-slate-300 rounded-lg hover:bg-white/5 transition"
                title="Minimize"
              >
                <ChevronDown size={14} />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center px-2 py-6">
                <div className="w-14 h-14 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center mb-4">
                  <BotMessageSquare size={26} className="text-violet-400" />
                </div>
                <p className="text-sm font-semibold text-slate-200">Portfolio Assistant</p>
                <p className="text-[11px] text-slate-500 mt-1.5 max-w-[260px] leading-relaxed">
                  Ask me about your portfolio, past analyses, alerts — or have me run a new stock analysis.
                </p>
                <div className="mt-5 flex flex-col gap-2 w-full">
                  {QUICK_PROMPTS.map(p => (
                    <button
                      key={p}
                      onClick={() => send(p)}
                      className="text-left text-[11px] text-slate-400 px-3 py-2.5 rounded-xl border border-white/[0.06] hover:bg-white/[0.04] hover:text-slate-300 hover:border-violet-500/20 transition"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map(m => (
              <MessageBubble key={m.id} msg={m} />
            ))}

            {loading && (
              <div className="flex justify-start gap-2">
                <div className="w-6 h-6 rounded-lg bg-violet-500/20 border border-violet-500/20 flex items-center justify-center shrink-0">
                  <Sparkles size={11} className="text-violet-400" />
                </div>
                <div className="bg-white/[0.05] text-slate-400 border border-white/[0.05] rounded-2xl rounded-tl-none px-3.5 py-2.5 text-xs flex items-center gap-2">
                  <Loader2 className="animate-spin" size={11} />
                  <span>Thinking…</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="p-3 border-t border-white/[0.06] bg-[#0d1225]/90 flex gap-2 shrink-0"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              placeholder="Ask about your portfolio…"
              disabled={loading}
              className="flex-1 bg-white/[0.04] border border-white/[0.07] rounded-xl px-3 py-2 text-xs text-white placeholder-slate-600 outline-none focus:border-violet-500/40 transition"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white p-2 rounded-xl transition shrink-0 cursor-pointer"
            >
              <Send size={13} />
            </button>
          </form>
        </div>
      )}

      {/* Toggle button */}
      <button
        onClick={() => setOpen(o => !o)}
        className={`pointer-events-auto w-12 h-12 rounded-2xl flex items-center justify-center shadow-xl transition-all duration-200 ${
          open
            ? 'bg-violet-600 text-white shadow-violet-600/40'
            : 'bg-[#0d1225] border border-white/10 text-violet-400 hover:border-violet-500/40 hover:text-violet-300 shadow-black/40'
        }`}
        title="Portfolio Assistant"
      >
        {open ? <X size={17} /> : <BotMessageSquare size={18} />}
      </button>
    </div>
  )
}
