import { describe, expect, it } from 'vitest'
import {
  KNOWN_REPORT_KEYS,
  liveDebateMessages,
  readableSectionLabel,
  reportKeyForStreamingAgent,
  stringRecord,
  visibleReportEntries,
} from '../streamingReports'

describe('reportKeyForStreamingAgent', () => {
  it.each([
    ['market', 'market_report'],
    ['market_analyst', 'market_report'],
    ['social', 'sentiment_report'],
    ['portfolio_manager', 'final_decision'],
    ['research_manager', 'investment_plan'],
    ['trader', 'trader_plan'],
  ])('maps %s to %s', (agent, expected) => {
    expect(reportKeyForStreamingAgent(agent)).toBe(expected)
  })

  it.each([
    'Market Analyst',
    'market-analyst',
    'marketAnalyst',
    '  market__analyst  ',
    '_market_analyst_',
  ])('normalises the spelling %s', agent => {
    expect(reportKeyForStreamingAgent(agent)).toBe('market_report')
  })

  it('routes an unknown agent to its own field when it names one', () => {
    // The analyst registry can add agents without a frontend release, so an
    // unrecognised `*_report` name is still a report rather than dropped.
    expect(reportKeyForStreamingAgent('sector_rotation_report')).toBe('sector_rotation_report')
  })

  it.each(['thinking', 'system', '', '   '])('treats %s as status chatter, not a report', agent => {
    expect(reportKeyForStreamingAgent(agent)).toBeNull()
  })

  it('drops an unknown agent that does not name a report field', () => {
    expect(reportKeyForStreamingAgent('some_new_agent')).toBeNull()
  })
})

describe('visibleReportEntries', () => {
  it('keeps the built-in order regardless of the order the payload uses', () => {
    const entries = visibleReportEntries({
      news_report: 'news',
      market_report: 'market',
      sentiment_report: 'sentiment',
    })

    expect(entries.map(([key]) => key)).toEqual(['market_report', 'sentiment_report', 'news_report'])
  })

  it('appends unknown report fields after the built-ins, sorted', () => {
    const entries = visibleReportEntries({
      zeta_report: 'z',
      market_report: 'market',
      alpha_report: 'a',
    })

    expect(entries.map(([key]) => key)).toEqual(['market_report', 'alpha_report', 'zeta_report'])
  })

  it('omits empty and non-string reports rather than rendering blank cards', () => {
    const entries = visibleReportEntries({
      market_report: '   ',
      news_report: 42,
      quant_report: 'real content',
    })

    expect(entries).toEqual([['quant_report', 'real content']])
  })

  it.each([null, undefined, 'a string', [1, 2]])('returns nothing for %s', value => {
    expect(visibleReportEntries(value)).toEqual([])
  })
})

describe('readableSectionLabel', () => {
  it('prefers the label the API supplied', () => {
    expect(readableSectionLabel({ market_report: 'Piyasa' }, 'market_report')).toBe('Piyasa')
  })

  it('leaves a built-in key alone while metadata is still loading', () => {
    expect(readableSectionLabel({}, 'market_report')).toBe('market_report')
  })

  it('humanises an unknown key so a new registry field is still readable', () => {
    expect(readableSectionLabel({}, 'sector_rotation_report')).toBe('Sector Rotation')
  })
})

describe('stringRecord', () => {
  it('keeps only the string values', () => {
    expect(stringRecord({ a: 'text', b: 7, c: null, d: '' })).toEqual({ a: 'text', d: '' })
  })

  it.each([null, 'string', [1]])('returns an empty record for %s', value => {
    expect(stringRecord(value)).toEqual({})
  })
})

describe('liveDebateMessages', () => {
  it('keeps only fully formed turns', () => {
    expect(liveDebateMessages([
      { sender: 'Bull', content: 'Buy', type: 'bull' },
      { sender: 'Bear', content: 42, type: 'bear' },
      { content: 'no sender', type: 'x' },
      'not an object',
    ])).toEqual([{ sender: 'Bull', content: 'Buy', type: 'bull' }])
  })

  it.each([null, {}, 'x'])('returns nothing for %s', value => {
    expect(liveDebateMessages(value)).toEqual([])
  })
})

describe('KNOWN_REPORT_KEYS', () => {
  it('has no duplicates, since it drives both ordering and the extras filter', () => {
    expect(new Set(KNOWN_REPORT_KEYS).size).toBe(KNOWN_REPORT_KEYS.length)
  })
})
