// Single source for mapping an analysis signal to a semantic tone and its
// display colors. Pages/hooks were each re-implementing "Buy/Overweight =
// green, Sell/Underweight = red, Hold/Neutral = amber" inline and had drifted
// (e.g. some coloured Hold as red); import from here instead.

export type Tone = 'positive' | 'neutral' | 'negative'

// Signal -> tone. Unknown signals return undefined so callers can decide
// whether to fall back (the badge renders plain text; charts use neutral).
export const SIGNAL_TONE: Record<string, Tone> = {
  Buy: 'positive',
  Overweight: 'positive',
  Hold: 'neutral',
  Neutral: 'neutral',
  Underweight: 'negative',
  Sell: 'negative',
}

export function signalTone(signal: string | null | undefined): Tone {
  return (signal && SIGNAL_TONE[signal]) || 'neutral'
}

export const TONE_HEX: Record<Tone, string> = {
  positive: '#10b981',
  neutral: '#f59e0b',
  negative: '#ef4444',
}

export const TONE_DOT_CLASS: Record<Tone, string> = {
  positive: 'bg-emerald-500',
  neutral: 'bg-amber-500',
  negative: 'bg-rose-500',
}

export const TONE_TEXT_CLASS: Record<Tone, string> = {
  positive: 'text-emerald-400',
  neutral: 'text-amber-400',
  negative: 'text-rose-400',
}
