import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import type { GridColDef } from '@mui/x-data-grid'
import { appTheme } from '../../../theme/appTheme'
import { settingsSchemaFixture, settingsUiSchemaFixture } from '../../../test/fixtures/settingsSchema'
import AppDataGrid from '../AppDataGrid'
import AppSchemaForm, { legacyFieldsToSchema } from '../AppSchemaForm'
import { AppConfirmDialog } from '../AppPrimitives'

function withTheme(node: ReactNode) {
  return render(<ThemeProvider theme={appTheme}>{node}</ThemeProvider>)
}

describe('AppConfirmDialog', () => {
  it('focuses the destructive action and closes from the keyboard', async () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    withTheme(
      <AppConfirmDialog
        open
        title="Delete alert?"
        message="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    )

    await waitFor(() => expect(screen.getByRole('button', { name: 'Delete' })).toHaveFocus())
    await userEvent.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})

describe('AppDataGrid states', () => {
  const columns: GridColDef[] = [{ field: 'name', headerName: 'Name' }]

  it('renders loading skeletons', () => {
    withTheme(<AppDataGrid rows={[]} columns={columns} loading ariaLabel="Alerts" />)
    expect(screen.getByLabelText('Alerts loading')).toBeInTheDocument()
  })

  it('renders an error state', () => {
    withTheme(<AppDataGrid rows={[]} columns={columns} error={new Error('network down')} />)
    expect(screen.getByText('network down')).toBeInTheDocument()
  })

  it('renders a custom empty state', () => {
    withTheme(<AppDataGrid rows={[]} columns={columns} emptyMessage="No alerts" />)
    expect(screen.getByText('No alerts')).toBeInTheDocument()
  })
})

describe('AppSchemaForm', () => {
  it('renders boolean, number, enum, array and secret fields from a schema fixture', async () => {
    const onChange = vi.fn()
    withTheme(
      <AppSchemaForm
        schema={settingsSchemaFixture}
        uiSchema={settingsUiSchemaFixture}
        formData={{ provider: 'openai', temperature: 0.2, enabled: true, notes: '', tags: [], apiKey: 'secret' }}
        onChange={onChange}
      />,
    )

    expect(screen.getByRole('combobox', { name: /provider/i })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /temperature/i })).toHaveAttribute('min', '0')
    expect(screen.getByRole('switch', { name: /enabled/i })).toBeChecked()
    expect(screen.getByText('Tags')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Advanced'))
    const secret = screen.getByLabelText('API key')
    expect(secret).toHaveAttribute('type', 'password')
    fireEvent.change(secret, { target: { value: 'changed' } })
    await waitFor(() => expect(onChange).toHaveBeenCalled())
  })

  it('maps legacy meta fields to the supported JSON schema types and metadata', () => {
    const { schema, uiSchema } = legacyFieldsToSchema([
      { key: 'enabled', type: 'boolean', label: 'Enabled', default: true },
      { key: 'retries', type: 'integer', label: 'Retries', min: 1, max: 5, required: true },
      { key: 'provider', type: 'select', label: 'Provider', options: [{ value: 'a', label: 'A' }] },
      { key: 'symbols', type: 'array', label: 'Symbols', advanced: true, section: 'Advanced', order: 8 },
      { key: 'token', type: 'secret', label: 'Token' },
    ], key => key)

    const properties = schema.properties as Record<string, Record<string, unknown>>
    expect(properties.enabled.type).toBe('boolean')
    expect(properties.retries.type).toBe('integer')
    expect(properties.retries.minimum).toBe(1)
    expect(properties.retries.maximum).toBe(5)
    expect(properties.provider.enum).toEqual(['a'])
    expect(properties.symbols.type).toBe('array')
    expect(properties.symbols['x-advanced']).toBe(true)
    expect(properties.symbols['x-section']).toBe('Advanced')
    expect(uiSchema.token?.['ui:widget']).toBe('password')
    expect(schema.required).toContain('retries')
  })

  it('renders a multi_select field as a pickable option set', async () => {
    // `multi_select` is a valid tool setting type on the backend — it validates
    // it as list[str] and checks every value against the options — but the
    // panels used to cast their generated types into a narrower local mirror,
    // so a tool declaring one would have rendered as a plain text box.
    const { schema, uiSchema } = legacyFieldsToSchema([
      {
        key: 'sources',
        type: 'multi_select',
        label: 'Sources',
        options: [
          { value: 'rss', label: 'RSS' },
          { value: 'api', label: 'API' },
        ],
      },
    ], key => key)

    const property = (schema.properties as Record<string, Record<string, unknown>>).sources
    expect(property.type).toBe('array')
    expect(property.uniqueItems).toBe(true)
    expect((property.items as Record<string, unknown>).oneOf).toEqual([
      { const: 'rss', title: 'RSS' },
      { const: 'api', title: 'API' },
    ])

    const onChange = vi.fn()
    withTheme(
      <AppSchemaForm schema={schema} uiSchema={uiSchema} formData={{ sources: ['rss'] }} onChange={onChange} />,
    )

    expect(screen.getByRole('checkbox', { name: 'RSS' })).toBeChecked()
    const api = screen.getByRole('checkbox', { name: 'API' })
    expect(api).not.toBeChecked()

    await userEvent.click(api)
    await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ sources: ['rss', 'api'] }))
  })
})
