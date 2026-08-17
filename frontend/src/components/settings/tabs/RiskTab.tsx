import type { SettingsRead } from '../../../api/generated/model'
import { Brain, Clock, Database, RefreshCw, ShieldAlert, Wrench } from 'lucide-react'
import { ErrorBoundary } from '../../ErrorBoundary'
import { CompactInputStyle, RiskRowItem, ToggleItem } from './primitives'

type Settings = SettingsRead
type Translate = (key: string, options?: Record<string, unknown>) => string
type Update = (key: keyof Settings, value: unknown) => void

interface RiskTabProps {
  s: Settings
  t: Translate
  update: Update
}

export function RiskTab({ s, t, update }: RiskTabProps) {
  return (
      <ErrorBoundary name="SettingsRisk">
        <div className="space-y-6">
          {/* 1. Risk & Capital Limits */}
          <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
              <div className="p-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400">
                <ShieldAlert className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                {t('settings.section_risk')}
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <RiskRowItem label={t('settings.row_risk_per_trade')} unit="%">
                <input
                  type="number"
                  step="0.1"
                  min="0.1"
                  max="50"
                  className={CompactInputStyle}
                  value={s.max_risk_per_trade_pct}
                  onChange={e => update('max_risk_per_trade_pct', Number.parseFloat(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_max_position_size')} unit="%">
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="100"
                  className={CompactInputStyle}
                  value={s.max_position_size_pct}
                  onChange={e => update('max_position_size_pct', Number.parseFloat(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_max_concentration')} unit="%">
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="100"
                  className={CompactInputStyle}
                  value={s.max_concentration_pct}
                  onChange={e => update('max_concentration_pct', Number.parseFloat(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_max_gross_exposure')} unit="×">
                <input
                  type="number"
                  step="0.1"
                  min="1"
                  max="10"
                  className={CompactInputStyle}
                  value={s.max_gross_exposure}
                  onChange={e => update('max_gross_exposure', Number.parseFloat(e.target.value))}
                />
              </RiskRowItem>

              <ToggleItem
                label={t('settings.row_allow_short_selling')}
                checked={s.allow_short_selling}
                onChange={v => update('allow_short_selling', v)}
                className="md:col-span-2"
              />
            </div>
          </div>

          {/* 2. Debate & Execution Rules */}
          <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
              <div className="p-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-400">
                <Brain className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                {t('settings.section_execution_rules')}
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <RiskRowItem label={t('settings.row_debate_rounds')} unit="tur">
                <input
                  type="number"
                  min="1"
                  max="10"
                  className={CompactInputStyle}
                  value={s.max_debate_rounds}
                  onChange={e => update('max_debate_rounds', Number.parseInt(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_price_tolerance')} unit="%">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="10"
                  className={CompactInputStyle}
                  value={s.price_tolerance_pct}
                  onChange={e => update('price_tolerance_pct', Number.parseFloat(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_parallel_analysts')} unit="analist">
                <input
                  type="number"
                  min="1"
                  max="16"
                  className={CompactInputStyle}
                  value={s.analyst_concurrency_limit}
                  onChange={e => update('analyst_concurrency_limit', Number.parseInt(e.target.value))}
                />
              </RiskRowItem>
            </div>
          </div>

          {/* 3. Agent Resilience & Timeouts */}
          <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
              <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                <RefreshCw className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                {t('settings.section_agent_resilience')}
              </h3>
            </div>

            <p className="text-[11px] text-slate-400 leading-relaxed -mt-1">
              {t('settings.hard_timeout_hint')}
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <RiskRowItem label={t('settings.row_node_retry_attempts')} unit="deneme">
                <input
                  type="number"
                  min="1"
                  max="10"
                  className={CompactInputStyle}
                  value={s.node_retry_attempts ?? 2}
                  onChange={e => update('node_retry_attempts', Number.parseInt(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_node_retry_base_delay')} unit="sn">
                <input
                  type="number"
                  step="0.1"
                  min="0.1"
                  max="10"
                  className={CompactInputStyle}
                  value={s.node_retry_base_delay ?? 1.0}
                  onChange={e => update('node_retry_base_delay', Number.parseFloat(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_node_timeout_seconds')} unit="sn">
                <input
                  type="number"
                  step="10"
                  min="30"
                  max="600"
                  className={CompactInputStyle}
                  value={s.node_timeout_seconds ?? 120}
                  onChange={e => update('node_timeout_seconds', Number.parseInt(e.target.value) || 120)}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_tool_timeout_seconds')} unit="sn">
                <input
                  type="number"
                  step="5"
                  min="15"
                  max="300"
                  className={CompactInputStyle}
                  value={s.tool_timeout_seconds ?? 60}
                  onChange={e => update('tool_timeout_seconds', Number.parseInt(e.target.value) || 60)}
                />
              </RiskRowItem>
            </div>
          </div>

          {/* 4. Circuit Breaker & Stall Protection */}
          <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
              <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400">
                <Clock className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                {t('settings.section_circuit_stall')}
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <RiskRowItem
                label={t('settings.row_circuit_breaker_threshold')}
                hint={t('settings.circuit_breaker_hint')}
                unit="hata"
                className="md:col-span-2"
              >
                <input
                  type="number"
                  min="1"
                  max="20"
                  className={CompactInputStyle}
                  value={s.circuit_breaker_threshold ?? 3}
                  onChange={e => update('circuit_breaker_threshold', Number.parseInt(e.target.value))}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_circuit_breaker_cooldown')} unit="sn">
                <input
                  type="number"
                  step="10"
                  min="10"
                  max="600"
                  className={CompactInputStyle}
                  value={s.circuit_breaker_cooldown ?? 60}
                  onChange={e => update('circuit_breaker_cooldown', Number.parseInt(e.target.value) || 60)}
                />
              </RiskRowItem>

              <RiskRowItem
                label={t('settings.row_stall_timeout_seconds')}
                hint={t('settings.stall_hint')}
                unit="sn"
              >
                <input
                  type="number"
                  step="10"
                  min="30"
                  max="600"
                  className={CompactInputStyle}
                  value={s.stall_timeout_seconds ?? 120}
                  onChange={e => update('stall_timeout_seconds', Number.parseInt(e.target.value) || 120)}
                />
              </RiskRowItem>
            </div>
          </div>

          {/* 5. Token Budget & Optimization */}
          <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
              <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                <Database className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                {t('settings.token_budget')}
              </h3>
            </div>

            <p className="text-[11px] text-slate-400 leading-relaxed -mt-1">
              {t('settings.token_budget_hint')}
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <ToggleItem
                label={t('settings.row_prompt_caching')}
                checked={s.anthropic_prompt_caching ?? true}
                onChange={v => update('anthropic_prompt_caching', v)}
                className="md:col-span-2"
              />

              <RiskRowItem label={t('settings.row_max_report_chars')} unit="karakter">
                <input
                  type="number"
                  min="500"
                  max="50000"
                  step="500"
                  className={CompactInputStyle}
                  value={s.max_report_chars_in_prompts ?? 6000}
                  onChange={e => update('max_report_chars_in_prompts', Number.parseInt(e.target.value) || 6000)}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_max_debate_history')} unit="karakter">
                <input
                  type="number"
                  min="1000"
                  max="100000"
                  step="1000"
                  className={CompactInputStyle}
                  value={s.max_debate_history_chars ?? 8000}
                  onChange={e => update('max_debate_history_chars', Number.parseInt(e.target.value) || 8000)}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_max_tool_output')} unit="karakter" className="md:col-span-2">
                <input
                  type="number"
                  min="1000"
                  max="100000"
                  step="1000"
                  className={CompactInputStyle}
                  value={s.max_tool_output_chars ?? 12000}
                  onChange={e => update('max_tool_output_chars', Number.parseInt(e.target.value) || 12000)}
                />
              </RiskRowItem>

              <ToggleItem
                label={t('settings.row_summary_only_mode')}
                hint={t('settings.summary_only_mode_hint')}
                checked={s.summary_only_mode ?? false}
                onChange={v => update('summary_only_mode', v)}
              />

              <ToggleItem
                label={t('settings.row_prefilter_enabled')}
                hint={t('settings.prefilter_hint')}
                checked={s.analyst_prefilter_enabled ?? false}
                onChange={v => update('analyst_prefilter_enabled', v)}
              />

              {s.analyst_prefilter_enabled && (
                <>
                  <RiskRowItem label={t('settings.row_prefilter_min_samples')} unit="çağrı">
                    <input
                      type="number"
                      min="1"
                      max="100"
                      className={CompactInputStyle}
                      value={s.analyst_prefilter_min_samples ?? 5}
                      onChange={e => update('analyst_prefilter_min_samples', Number.parseInt(e.target.value) || 5)}
                    />
                  </RiskRowItem>

                  <RiskRowItem label={t('settings.row_prefilter_max_win_rate')} unit="%">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="1"
                      className={CompactInputStyle}
                      value={s.analyst_prefilter_max_win_rate ?? 40}
                      onChange={e => update('analyst_prefilter_max_win_rate', Number.parseFloat(e.target.value) || 40)}
                    />
                  </RiskRowItem>
                </>
              )}
            </div>
          </div>

          {/* 6. Institutional Risk Features */}
          <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
              <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                <Wrench className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                {t('settings.section_institutional_features')}
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <ToggleItem
                label={t('settings.row_strict_stop_loss')}
                checked={s.strict_stop_loss_mode}
                onChange={v => update('strict_stop_loss_mode', v)}
              />

              <ToggleItem
                label={t('settings.row_correlation_risk')}
                checked={s.correlation_risk_enabled}
                onChange={v => update('correlation_risk_enabled', v)}
              />

              <ToggleItem
                label={t('settings.row_auto_execute_signals')}
                warning={t('settings.auto_execute_signals_hint')}
                checked={s.auto_execute_signals ?? false}
                onChange={v => update('auto_execute_signals', v)}
                className="md:col-span-2"
              />

              <ToggleItem
                label={t('settings.row_quality_gate')}
                checked={s.quality_gate_enabled}
                onChange={v => update('quality_gate_enabled', v)}
              />

              <ToggleItem
                label={t('settings.row_drawdown_breaker')}
                checked={s.drawdown_breaker_enabled}
                onChange={v => update('drawdown_breaker_enabled', v)}
              />

              {s.drawdown_breaker_enabled && (
                <RiskRowItem label={t('settings.row_max_drawdown_pct')} unit="%" className="md:col-span-2">
                  <input
                    type="number"
                    min={1}
                    max={100}
                    className={CompactInputStyle}
                    value={s.max_portfolio_drawdown_pct}
                    onChange={e => update('max_portfolio_drawdown_pct', Number(e.target.value))}
                  />
                </RiskRowItem>
              )}
            </div>
          </div>

          {/* 7. Strategy Continuity & Decision Stability */}
          <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
              <div className="p-1.5 rounded-lg bg-fuchsia-500/10 border border-fuchsia-500/20 text-fuchsia-300">
                <Brain className="w-4 h-4" />
              </div>
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                {t('settings.section_strategy_continuity')}
              </h3>
            </div>

            <p className="text-[11px] text-slate-400 leading-relaxed -mt-1">
              {t('settings.strategy_continuity_hint')}
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <ToggleItem
                label={t('settings.row_strategy_learning')}
                hint={t('settings.strategy_learning_hint')}
                checked={s.strategy_learning_enabled ?? true}
                onChange={v => update('strategy_learning_enabled', v)}
              />

              <RiskRowItem
                label={t('settings.row_decision_stability_mode')}
                hint={s.decision_stability_mode === 'enforce'
                  ? t('settings.decision_stability_enforce_warning')
                  : undefined}
              >
                <select
                  aria-label={t('settings.row_decision_stability_mode')}
                  className={CompactInputStyle}
                  value={s.decision_stability_mode ?? 'shadow'}
                  onChange={e => update('decision_stability_mode', e.target.value)}
                >
                  <option value="off">{t('settings.decision_stability_off')}</option>
                  <option value="shadow">{t('settings.decision_stability_shadow')}</option>
                  <option value="enforce">{t('settings.decision_stability_enforce')}</option>
                </select>
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_stability_min_quality')} unit="%">
                <input
                  aria-label={t('settings.row_stability_min_quality')}
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  className={CompactInputStyle}
                  value={s.decision_stability_min_quality ?? 70}
                  onChange={e => update('decision_stability_min_quality', Number.parseInt(e.target.value) || 0)}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_stability_min_confidence')} unit="0–1">
                <input
                  aria-label={t('settings.row_stability_min_confidence')}
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  className={CompactInputStyle}
                  value={s.decision_stability_min_confidence ?? 0.65}
                  onChange={e => update('decision_stability_min_confidence', Number.parseFloat(e.target.value) || 0)}
                />
              </RiskRowItem>

              <RiskRowItem label={t('settings.row_stability_min_evidence_groups')} unit="#" className="md:col-span-2">
                <input
                  aria-label={t('settings.row_stability_min_evidence_groups')}
                  type="number"
                  min="1"
                  max="10"
                  step="1"
                  className={CompactInputStyle}
                  value={s.decision_stability_min_evidence_groups ?? 2}
                  onChange={e => update('decision_stability_min_evidence_groups', Number.parseInt(e.target.value) || 1)}
                />
              </RiskRowItem>

              <ToggleItem
                label={t('settings.row_reversal_verifier')}
                hint={t('settings.reversal_verifier_hint')}
                checked={s.reversal_verifier_enabled ?? true}
                onChange={v => update('reversal_verifier_enabled', v)}
              />

              <ToggleItem
                label={t('settings.row_confidence_calibration')}
                hint={t('settings.confidence_calibration_hint')}
                checked={s.confidence_calibration_enabled ?? false}
                onChange={v => update('confidence_calibration_enabled', v)}
              />

              <ToggleItem
                label={t('settings.row_regime_aware_weighting')}
                hint={t('settings.regime_aware_weighting_hint')}
                checked={s.regime_aware_weighting_enabled ?? false}
                onChange={v => update('regime_aware_weighting_enabled', v)}
                className="md:col-span-2"
              />
            </div>
          </div>
        </div>
      </ErrorBoundary>
  )
}
