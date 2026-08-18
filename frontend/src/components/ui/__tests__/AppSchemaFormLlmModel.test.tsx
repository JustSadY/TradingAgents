import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AppSchemaForm, { legacyFieldsToSchema } from '../AppSchemaForm'
import { normalizeLlmCatalog } from '../../../hooks/useLlmCatalog'

const CATALOG = normalizeLlmCatalog({
  openai: {
    label: 'OpenAI',
    models: [
      { value: 'gpt-5.6-luna', label: 'GPT-5.6 Luna' },
      { value: 'gpt-5.6-sol', label: 'GPT-5.6 Sol' },
    ],
  },
  anthropic: {
    label: 'Anthropic (Claude)',
    models: [{ value: 'claude-sonnet-5', label: 'Claude Sonnet 5' }],
  },
})

const FIELDS = [
  {
    key: 'llm_provider',
    type: 'select' as const,
    label: 'LLM Provider',
    default: '',
    options: [
      { value: 'openai', label: 'OpenAI' },
      { value: 'anthropic', label: 'Anthropic (Claude)' },
    ],
  },
  { key: 'llm_model', type: 'llm_model' as const, label: 'Model Name', default: '' },
]

function renderForm(formData: Record<string, unknown>, onChange = vi.fn()) {
  const { schema, uiSchema } = legacyFieldsToSchema(FIELDS, key => key)
  render(
    <AppSchemaForm
      schema={schema}
      uiSchema={uiSchema}
      formData={formData}
      formContext={{ llmCatalog: CATALOG, formData, inheritLabel: 'Default', customLabel: 'Custom model…' }}
      onChange={onChange}
    />,
  )
  return onChange
}

function openModelDropdown() {
  // MUI renders the select as a button-like combobox; the provider select is first.
  const comboboxes = screen.getAllByRole('combobox')
  fireEvent.mouseDown(comboboxes[comboboxes.length - 1])
}

describe('llm_model widget', () => {
  it('offers the models of the provider selected beside it', () => {
    renderForm({ llm_provider: 'openai', llm_model: '' })
    openModelDropdown()

    expect(screen.getByRole('option', { name: 'GPT-5.6 Luna' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'GPT-5.6 Sol' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Claude Sonnet 5' })).not.toBeInTheDocument()
  })

  it('follows the sibling provider rather than showing a fixed list', () => {
    renderForm({ llm_provider: 'anthropic', llm_model: '' })
    openModelDropdown()

    expect(screen.getByRole('option', { name: 'Claude Sonnet 5' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'GPT-5.6 Luna' })).not.toBeInTheDocument()
  })

  it('keeps an inherit-the-default choice distinct from a custom model id', () => {
    renderForm({ llm_provider: 'openai', llm_model: '' })
    openModelDropdown()

    expect(screen.getByRole('option', { name: 'Default' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Custom model…' })).toBeInTheDocument()
    // Empty means "inherit", so no free-text box is shown for it.
    expect(screen.queryByPlaceholderText(/custom/i)).not.toBeInTheDocument()
  })

  it('reveals a text box when the user picks a custom model', () => {
    renderForm({ llm_provider: 'openai', llm_model: '' })
    openModelDropdown()
    fireEvent.click(screen.getByRole('option', { name: 'Custom model…' }))

    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('shows a model saved outside the catalog as a custom value', () => {
    renderForm({ llm_provider: 'openai', llm_model: 'some-private-deployment' })

    expect(screen.getByRole('textbox')).toHaveValue('some-private-deployment')
  })
})
