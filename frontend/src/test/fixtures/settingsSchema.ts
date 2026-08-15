import type { RJSFSchema, UiSchema } from '@rjsf/utils'

export const settingsSchemaFixture: RJSFSchema = {
  type: 'object',
  required: ['provider', 'temperature'],
  properties: {
    provider: {
      type: 'string',
      title: 'Provider',
      description: 'LLM provider used by this agent.',
      enum: ['openai', 'anthropic'],
      default: 'openai',
      'x-section': 'Model',
      'x-order': 1,
    },
    temperature: {
      type: 'number',
      title: 'Temperature',
      minimum: 0,
      maximum: 2,
      multipleOf: 0.1,
      default: 0.2,
      'x-section': 'Model',
      'x-order': 2,
    },
    enabled: {
      type: 'boolean',
      title: 'Enabled',
      default: true,
      'x-section': 'General',
      'x-order': 3,
    },
    notes: {
      type: 'string',
      title: 'Notes',
      description: 'Optional operator notes.',
      'x-section': 'General',
      'x-order': 4,
    },
    tags: {
      type: 'array',
      title: 'Tags',
      items: { type: 'string' },
      default: [],
      'x-section': 'Advanced',
      'x-advanced': true,
      'x-order': 5,
    },
    apiKey: {
      type: 'string',
      title: 'API key',
      'x-section': 'Advanced',
      'x-advanced': true,
      'x-order': 6,
    },
  },
}

export const settingsUiSchemaFixture: UiSchema = {
  'ui:order': ['provider', 'temperature', 'enabled', 'notes', 'tags', 'apiKey'],
  notes: { 'ui:widget': 'textarea' },
  apiKey: { 'ui:widget': 'password' },
}
