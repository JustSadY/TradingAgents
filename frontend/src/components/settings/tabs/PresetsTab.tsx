import { BookmarkPlus, Play, Trash2 } from 'lucide-react'
import type { PresetRead } from '../../../api/generated/model'
import { ErrorBoundary } from '../../ErrorBoundary'
import { Input, Section } from './primitives'

type Translate = (key: string, options?: Record<string, unknown>) => string

interface PresetsTabProps {
  t: Translate
  presets: PresetRead[]
  presetName: string
  setPresetName: (name: string) => void
  presetSaving: boolean
  savePreset: () => void
  applyPreset: (id: number) => void
  deletePreset: (id: number) => void
}

export function PresetsTab({ t, presets, presetName, setPresetName, presetSaving, savePreset, applyPreset, deletePreset }: PresetsTabProps) {
  return (
    <ErrorBoundary name="SettingsPresets">
    <Section title={t('settings.section_presets')}>
      <div className="flex gap-2">
        <input
          className={Input}
          placeholder={t('settings.preset_name_placeholder')}
          value={presetName}
          onChange={e => setPresetName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && savePreset()}
        />
        <button
          onClick={savePreset}
          disabled={presetSaving || !presetName.trim()}
          className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-semibold px-4 py-2 rounded-xl transition whitespace-nowrap cursor-pointer shadow shadow-violet-500/10"
        >
          <BookmarkPlus size={14} /> {t('settings.preset_save_button')}
        </button>
      </div>
      {presets.length === 0 ? (
        <p className="text-slate-600 text-xs text-center py-4">{t('settings.preset_no_presets')}</p>
      ) : (
        <div className="space-y-2 pt-1">
          {presets.map(p => (
            <div key={p.id} className="flex items-center justify-between bg-slate-900/40 border border-white/[0.04] rounded-xl px-4 py-2.5">
              <span className="text-xs text-slate-300 font-semibold">{p.name}</span>
              <div className="flex items-center gap-3">
                <button onClick={() => applyPreset(p.id)} className="text-violet-400 hover:text-violet-300 p-1 transition-colors cursor-pointer" title={t('settings.preset_apply_title')}>
                  <Play size={14} fill="currentColor" />
                </button>
                <button onClick={() => deletePreset(p.id)} className="text-slate-500 hover:text-rose-400 p-1 transition-colors cursor-pointer">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Section>
    </ErrorBoundary>
  )
}
