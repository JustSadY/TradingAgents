import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { CronStatusResponse, SettingsRead } from '../../../api/generated/model'
import { CronTab } from '../tabs/CronTab'

vi.mock('../../../contexts/LanguageContext', async () => ({
  useTranslation: (await import('../../../test/i18nMock')).useTranslationMock,
}))

// The panel renders whatever the status endpoint says, so the test asserts on
// translation keys rather than copy.
const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${JSON.stringify(options)}` : key

const settings = { cron_enabled: true, cron_schedule: '0 9 * * 1-5' } as SettingsRead

function renderTab(status: Partial<CronStatusResponse> | null) {
  return render(
    <CronTab
      s={settings}
      t={t}
      update={vi.fn()}
      cronStatus={status ? ({ running: true, job_configured: true, ...status } as CronStatusResponse) : null}
    />,
  )
}

describe('CronTab scheduler health', () => {
  it('reports a healthy scheduler as online', () => {
    renderTab({ schedule: '0 9 * * 1-5', next_run_time: '2026-09-01T09:00:00+00:00' })

    expect(screen.getByText('settings.cron_online')).toBeInTheDocument()
    expect(screen.queryByText('settings.cron_degraded')).not.toBeInTheDocument()
  })

  it('does not claim to be online when the schedule stopped firing', () => {
    // The failure this panel exists for: the process is up, so `running` is
    // true, but nothing is registered to run.
    renderTab({ job_configured: false, degraded_reason: 'job_missing', degraded_detail: 'no job registered' })

    expect(screen.getByText('settings.cron_degraded')).toBeInTheDocument()
    expect(screen.getByText('settings.cron_reason_job_missing')).toBeInTheDocument()
    expect(screen.getByText('no job registered')).toBeInTheDocument()
    expect(screen.getByText('settings.cron_no_job')).toBeInTheDocument()
  })

  it('reports a stopped scheduler as offline', () => {
    renderTab({ running: false, job_configured: false, degraded_reason: 'scheduler_stopped' })

    expect(screen.getByText('settings.cron_offline')).toBeInTheDocument()
    expect(screen.getByText('settings.cron_reason_scheduler_stopped')).toBeInTheDocument()
  })

  it('shows why the last run did nothing', () => {
    renderTab({ last_outcome: 'skipped', last_outcome_detail: 'NYSE holiday' })

    expect(screen.getByText('settings.cron_outcome_skipped')).toBeInTheDocument()
    expect(screen.getByText('NYSE holiday')).toBeInTheDocument()
  })

  it('says so when the scan has never run', () => {
    renderTab({ last_run_at: null })

    expect(screen.getByText('settings.cron_never_ran')).toBeInTheDocument()
  })
})
