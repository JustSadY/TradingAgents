import { Trash2 } from 'lucide-react'
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
  pineconeKey: string
  setPineconeKey: (key: string) => void
  pineconeSaving: boolean
  savePineconeKey: () => void
  deletePineconeKey: () => void
}

export function MemoryTab({ s, t, update, meta, memoryStatus, pineconeKey, setPineconeKey, pineconeSaving, savePineconeKey, deletePineconeKey }: MemoryTabProps) {
  return (
    <ErrorBoundary name="SettingsMemory">
    <Section title={t('settings.section_vector_memory')}>
      <Row label={t('settings.row_memory_store')}>
        <select className={Input} value={s.memory_store} onChange={e => update('memory_store', e.target.value)}>
          {(meta?.memory_stores ?? [{ value: 'pinecone', label: t('settings.memory_store_pinecone') }, { value: 'pgvector', label: t('settings.memory_store_pgvector') }]).map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>
      <Row label={t('settings.row_status')}>
        {memoryStatus?.enabled ? (
          <span className="px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-[10px] font-bold border border-emerald-500/20">{t('settings.memory_enabled')}</span>
        ) : (
          <span className="px-2 py-0.5 rounded-lg bg-slate-700/40 text-slate-400 text-[10px] font-bold border border-white/[0.06]">
            {s.memory_store === 'pgvector' ? t('settings.memory_disabled_pgvector') : t('settings.memory_disabled_pinecone')}
          </span>
        )}
      </Row>
      {s.memory_store === 'pgvector' ? (
        <>
          <Row label={t('settings.row_openai_embed_model')}><input className={Input} value={s.memory_openai_embed_model} onChange={e => update('memory_openai_embed_model', e.target.value)} /></Row>
          <Row label="">
            <p className="text-[10px] text-slate-600 leading-relaxed">{t('settings.pgvector_hint')}</p>
          </Row>
        </>
      ) : (
        <>
          <Row label={t('settings.row_pinecone_api_key')}>
            {memoryStatus?.enabled ? (
              <button onClick={deletePineconeKey} className="flex items-center gap-1.5 text-xs font-semibold text-rose-400 hover:text-rose-300">
                <Trash2 size={13} /> {t('settings.memory_remove_key')}
              </button>
            ) : (
              <div className="flex gap-2 items-center">
                <input type="password" className={Input} value={pineconeKey} onChange={e => setPineconeKey(e.target.value)} placeholder="pcsk_..." />
                <button onClick={savePineconeKey} disabled={pineconeSaving || !pineconeKey.trim()} className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-violet-600 hover:bg-violet-500 disabled:opacity-40">{t('settings.memory_save_key')}</button>
              </div>
            )}
          </Row>
          <Row label={t('settings.row_index_name')}><input className={Input} value={s.pinecone_index} onChange={e => update('pinecone_index', e.target.value)} /></Row>
          <Row label={t('settings.row_cloud')}><input className={Input} value={s.pinecone_cloud} onChange={e => update('pinecone_cloud', e.target.value)} placeholder="aws" /></Row>
          <Row label={t('settings.row_region')}><input className={Input} value={s.pinecone_region} onChange={e => update('pinecone_region', e.target.value)} placeholder="us-east-1" /></Row>
          <Row label={t('settings.row_embedder')}>
            <select className={Input} value={s.memory_embedder} onChange={e => update('memory_embedder', e.target.value)}>
              {(meta?.embedders ?? [{ value: 'pinecone', label: t('settings.memory_embedder_pinecone') }, { value: 'openai', label: t('settings.memory_embedder_openai') }, { value: 'ollama', label: t('settings.memory_embedder_ollama') }]).map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Row>
          {s.memory_embedder === 'openai' && (
            <Row label={t('settings.row_openai_embed_model')}><input className={Input} value={s.memory_openai_embed_model} onChange={e => update('memory_openai_embed_model', e.target.value)} /></Row>
          )}
          {s.memory_embedder === 'ollama' && (
            <Row label={t('settings.row_ollama_embed_model')}>
              <input className={Input} value={s.memory_ollama_embed_model} onChange={e => update('memory_ollama_embed_model', e.target.value)} placeholder="nomic-embed-text" />
            </Row>
          )}
          {s.memory_embedder === 'pinecone' && (
            <Row label={t('settings.row_embed_model')}><input className={Input} value={s.pinecone_embed_model} onChange={e => update('pinecone_embed_model', e.target.value)} /></Row>
          )}
          <Row label="">
            <p className="text-[10px] text-slate-600 leading-relaxed">
              {t('settings.memory_help')}
            </p>
          </Row>
        </>
      )}
      {memoryStatus?.needs_openai_key && (
        <Row label=""><span className="text-[11px] text-amber-400">{t('settings.memory_needs_openai_key')}</span></Row>
      )}
      <Row label={t('settings.row_agent_qa')}>
        <label className="flex items-center gap-2.5 cursor-pointer text-slate-300 select-none">
          <input type="checkbox" className="w-5 h-5 accent-violet-600 rounded" checked={s.agent_qa_enabled} onChange={e => update('agent_qa_enabled', e.target.checked)} />
          <span className="text-xs font-semibold">{t('settings.agent_qa_description')}</span>
        </label>
      </Row>
      <Row label={t('settings.row_memory_recall_count')}>
        <input type="number" min={1} max={50} className={Input} value={s.memory_recall_count ?? 5} onChange={e => update('memory_recall_count', parseInt(e.target.value) || 5)} />
      </Row>
    </Section>
    </ErrorBoundary>
  )
}
