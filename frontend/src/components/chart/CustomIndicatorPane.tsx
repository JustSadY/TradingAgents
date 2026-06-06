import React from 'react'
import { 
  ResponsiveContainer, ComposedChart, CartesianGrid, XAxis, YAxis, Tooltip, 
  Bar, Cell, Line, ReferenceLine, AreaChart, Area, LineChart 
} from 'recharts'

const ALLOCATION_COLORS = ['#8b5cf6', '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#14b8a6', '#6366f1']

interface CustomIndicatorPaneProps {
  showRSI: boolean
  showMACD: boolean
  showSentiment: boolean
  candles: any[]
  sentimentChartData: any[]
  customIndicators: any[]
  userIndicatorData: any[]
  userIndicatorLabel: string
  t: any
}

export const CustomIndicatorPane: React.FC<CustomIndicatorPaneProps> = ({
  showRSI, showMACD, showSentiment, candles, sentimentChartData,
  customIndicators, userIndicatorData, userIndicatorLabel, t
}) => {
  if (!showRSI && !showMACD && !showSentiment && customIndicators.length === 0 && userIndicatorData.length === 0) {
    return null
  }

  return (
    <div className="space-y-6 mt-6 pb-12">
      {showRSI && (
        <div className="glass-panel rounded-2xl p-4">
          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Relative Strength Index (14)</h4>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={candles}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis domain={[0, 100]} stroke="#475569" fontSize={10} ticks={[30, 70]} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                  itemStyle={{ fontSize: '10px' }}
                />
                <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" opacity={0.5} />
                <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" opacity={0.5} />
                <Line type="monotone" dataKey="rsi" stroke="#3b82f6" dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {showMACD && (
        <div className="glass-panel rounded-2xl p-4">
          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">MACD (12, 26, 9)</h4>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={candles}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis stroke="#475569" fontSize={10} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                  itemStyle={{ fontSize: '10px' }}
                />
                <Bar dataKey="macd_hist" isAnimationActive={false}>
                  {candles.map((c, i) => (
                    <Cell key={i} fill={c.macd_hist >= 0 ? '#10b98140' : '#ef444440'} />
                  ))}
                </Bar>
                <Line type="monotone" dataKey="macd_line" stroke="#f59e0b" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                <Line type="monotone" dataKey="macd_signal" stroke="#3b82f6" dot={false} strokeWidth={1.5} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {showSentiment && (
        <div className="glass-panel rounded-2xl p-4">
          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">AI Consensus Sentiment History</h4>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={sentimentChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis domain={[-1, 1]} stroke="#475569" fontSize={10} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                  itemStyle={{ fontSize: '10px' }}
                />
                <ReferenceLine y={0} stroke="#475569" opacity={0.3} />
                <Area 
                  type="stepAfter" 
                  dataKey="value" 
                  stroke="#10b981" 
                  fill="url(#colorSent)" 
                  isAnimationActive={false}
                />
                <defs>
                  <linearGradient id="colorSent" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {customIndicators.map((ci, i) => (
        <div key={i} className="glass-panel rounded-2xl p-4">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{ci.label}</h4>
            <span className="text-[9px] font-mono text-slate-600 truncate max-w-[50%]">{ci.formula}</span>
          </div>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ci.data}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis stroke="#475569" fontSize={10} hide />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                  itemStyle={{ fontSize: '10px' }}
                />
                <Line type="monotone" dataKey="value" stroke={ALLOCATION_COLORS[i % ALLOCATION_COLORS.length]} dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}

      {userIndicatorData.length > 0 && (
        <div className="glass-panel rounded-2xl p-4 ring-1 ring-violet-500/20">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-[10px] font-bold text-violet-400 uppercase tracking-widest flex items-center gap-2">
              <BarChart2 size={12} /> Dynamic Indicator
            </h4>
            <span className="text-[9px] font-mono text-slate-500">{userIndicatorLabel}</span>
          </div>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={userIndicatorData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis stroke="#475569" fontSize={10} hide />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                  itemStyle={{ fontSize: '10px' }}
                />
                <Line type="monotone" dataKey="value" stroke="#8b5cf6" dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
