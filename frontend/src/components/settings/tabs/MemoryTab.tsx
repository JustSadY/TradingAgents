import type { MemoryStatusResponse, SettingsRead } from '../../../api/generated/model'
import type { Meta } from '../../../hooks/useMeta'
import { ErrorBoundary } from '../../ErrorBoundary'
import { Input, Row, Section } from './primitives'

type Settings = SettingsRead
type Translate = (key: string, options?: Record<string, unknown>) => string
type Update = (key: keyof Settings, value: unknown) => void

interface MemoryTabProps {
  s: Settings
  t: Translate
  update: Update
  meta: Meta | null
  memoryStatus: MemoryStatusResponse | null
  // Kept temporarily so Settings.tsx does not need a broad generated-API/UI
  // refactor in the same change. Mem0 no longer consumes Pinecone credentials.
  pineconeKey: string
  setPineconeKey: (key: string) => void
  pineconeSaving: boolean
  savePineconeKey: () => void
  deletePineconeKey: () => void
}

export function MemoryTab({ s, t, update, meta, memoryStatus }: MemoryTabProps) {
  const embedder = s.memory_embedder === 'ollama' ? 'ollama' : 'openai'
  const embedders = (meta?.embedders ?? [
    { value: 'openai', label: t('settings.memory_embedder_openai') },
    { value: 'ollama', label: t('settings.memory_embedder_ollama') },
  ]).filter(option => option.value === 'openai' || option.value === 'ollama')

  const updateEmbedder = (value: string) => {
    update('memory_store', 'pgvector')
    update('memory_embedder', value)
  }

  return (
    <ErrorBoundary name="SettingsMemory">
      <Section title={t('settings.section_vector_memory')}>
        <Row label={t('settings.row_memory_store')}>
          <div className="space-y-1">
            <div className={`${Input} flex items-center text-slate-300`}>Mem0 + pgvector (PostgreSQL)</div>
            <p className="text-[10px] text-slate-600 leading-relaxed">
              Long-term memory is stored by Mem0 in the application PostgreSQL database.
            </p>
          </div>
        </Row>

        <Row label={t('settings.row_status')}>
          {memoryStatus?.enabled ? (
            <span className="px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-[10px] font-bold border border-emerald-500/20">
              {t('settings.memory_enabled')}
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-lg bg-slate-700/40 text-slate-400 text-[10px] font-bold border border-white/[0.06]">
              {embedder === 'openai' ? t('settings.memory_disabled_pgvector') : 'Ollama memory unavailable'}
            </span>
          )}
        </Row>

        <Row label={t('settings.row_embedder')}>
          <select className={Input} value={embedder} onChange={event => updateEmbedder(event.target.value)}>
            {embedders.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </Row>

        {embedder === 'openai' ? (
          <Row label={t('settings.row_openai_embed_model')}>
            <input
              className={Input}
              value={s.memory_openai_embed_model}
              onChange={event => update('memory_openai_embed_model', event.target.value)}
            />
          </Row>
        ) : (
          <Row label={t('settings.row_ollama_embed_model')}>
            <input
              className={Input}
              value={s.memory_ollama_embed_model}
              onChange={event => update('memory_ollama_embed_model', event.target.value)}
              placeholder="nomic-embed-text"
            />
          </Row>
        )}

        {memoryStatus?.needs_openai_key && (
          <Row label="">
            <span className="text-[11px] text-amber-400">{t('settings.memory_needs_openai_key')}</span>
          </Row>
        )}

        <Row label="">
          <p className="text-[10px] text-slate-600 leading-relaxed">
            Memory entries are curated by TradingAgents and written to Mem0 without an additional LLM extraction pass.
          </p>
        </Row>

        <Row label={t('settings.row_agent_qa')}>
          <label className="flex items-center gap-2.5 cursor-pointer text-slate-300 select-none">
            <input
              type="checkbox"
              className="w-5 h-5 accent-violet-600 rounded"
              checked={s.agent_qa_enabled}
              onChange={event => update('agent_qa_enabled', event.target.checked)}
            />
            <span className="text-xs font-semibold">{t('settings.agent_qa_description')}</span>
          </label>
        </Row>

        <Row label={t('settings.row_memory_recall_count')}>
          <input
            type="number"
            min={1}
            max={50}
            className={Input}
            value={s.memory_recall_count ?? 5}
            onChange={event => update('memory_recall_count', parseInt(event.target.value) || 5)}
          />
        </Row>
      </Section>
    </ErrorBoundary>
  )
}
