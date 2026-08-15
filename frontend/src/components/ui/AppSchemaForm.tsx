import type { ReactNode } from 'react'
import { Box, FormHelperText, IconButton, Typography } from '@mui/material'
import { ArrowDown, ArrowUp, Copy, Plus, Trash2 } from 'lucide-react'
import Form from '@rjsf/core'
import validator from '@rjsf/validator-ajv8'
import type {
  ArrayFieldTemplateProps,
  FieldTemplateProps,
  IconButtonProps as RjsfIconButtonProps,
  ObjectFieldTemplateProps,
  RJSFSchema,
  UiSchema,
  WidgetProps,
} from '@rjsf/utils'
import { AppButton, AppSelect, AppSwitch, AppTextField, SecretField } from './AppPrimitives'

export interface AppSchemaFormProps {
  schema: RJSFSchema
  uiSchema?: UiSchema
  formData?: Record<string, unknown>
  disabled?: boolean
  readonly?: boolean
  submitLabel?: ReactNode
  onChange?: (data: Record<string, unknown>) => void
  onSubmit?: (data: Record<string, unknown>) => void
}

function helperText(rawErrors?: string[], help?: ReactNode) {
  if (rawErrors?.length) return rawErrors.join(', ')
  return help
}

function schemaDescription(props: WidgetProps): ReactNode {
  return typeof props.schema.description === 'string' ? props.schema.description : undefined
}

function TextWidget(props: WidgetProps) {
  if (props.schema.type === 'number' || props.schema.type === 'integer') {
    return <NumberWidget {...props} />
  }

  return (
    <AppTextField
      id={props.id}
      label={props.label}
      value={props.value ?? ''}
      required={props.required}
      disabled={props.disabled}
      slotProps={{ input: { readOnly: props.readonly } }}
      placeholder={props.placeholder}
      error={Boolean(props.rawErrors?.length)}
      helperText={helperText(props.rawErrors, schemaDescription(props))}
      onChange={event => props.onChange(event.target.value)}
      onBlur={() => props.onBlur(props.id, props.value)}
      onFocus={() => props.onFocus(props.id, props.value)}
    />
  )
}

function PasswordWidget(props: WidgetProps) {
  return (
    <SecretField
      id={props.id}
      label={props.label}
      value={props.value ?? ''}
      required={props.required}
      disabled={props.disabled}
      slotProps={{ input: { readOnly: props.readonly } }}
      placeholder={props.placeholder}
      error={Boolean(props.rawErrors?.length)}
      helperText={helperText(props.rawErrors, schemaDescription(props))}
      onChange={event => props.onChange(event.target.value)}
    />
  )
}

function TextareaWidget(props: WidgetProps) {
  return (
    <AppTextField
      id={props.id}
      label={props.label}
      value={props.value ?? ''}
      required={props.required}
      disabled={props.disabled}
      slotProps={{ input: { readOnly: props.readonly } }}
      multiline
      minRows={3}
      placeholder={props.placeholder}
      error={Boolean(props.rawErrors?.length)}
      helperText={helperText(props.rawErrors, schemaDescription(props))}
      onChange={event => props.onChange(event.target.value)}
    />
  )
}

function NumberWidget(props: WidgetProps) {
  const minimum = typeof props.schema.minimum === 'number' ? props.schema.minimum : undefined
  const maximum = typeof props.schema.maximum === 'number' ? props.schema.maximum : undefined
  const multipleOf = typeof props.schema.multipleOf === 'number' ? props.schema.multipleOf : undefined
  return (
    <AppTextField
      id={props.id}
      type="number"
      label={props.label}
      value={props.value ?? ''}
      required={props.required}
      disabled={props.disabled}
      slotProps={{
        input: { readOnly: props.readonly },
        htmlInput: { min: minimum, max: maximum, step: multipleOf ?? (props.schema.type === 'integer' ? 1 : 'any') },
      }}
      error={Boolean(props.rawErrors?.length)}
      helperText={helperText(props.rawErrors, schemaDescription(props))}
      onChange={event => {
        const next = event.target.value
        props.onChange(next === '' ? undefined : props.schema.type === 'integer' ? Number.parseInt(next, 10) : Number.parseFloat(next))
      }}
    />
  )
}

function CheckboxWidget(props: WidgetProps) {
  const help = helperText(props.rawErrors, schemaDescription(props))
  return (
    <Box>
      <AppSwitch
        checked={Boolean(props.value)}
        disabled={props.disabled || props.readonly}
        label={props.label}
        onChange={props.onChange}
      />
      {help ? <FormHelperText error={Boolean(props.rawErrors?.length)}>{help}</FormHelperText> : null}
    </Box>
  )
}

function SelectWidget(props: WidgetProps) {
  const enumOptions = props.options.enumOptions ?? []
  const help = helperText(props.rawErrors, schemaDescription(props))
  return (
    <Box>
      <AppSelect
        id={props.id}
        label={props.label}
        value={(props.value ?? '') as string | number}
        disabled={props.disabled || props.readonly}
        options={enumOptions.map(option => ({ value: option.value as string | number, label: option.label }))}
        onChange={props.onChange}
      />
      {help ? <FormHelperText error={Boolean(props.rawErrors?.length)}>{help}</FormHelperText> : null}
    </Box>
  )
}

function AppFieldTemplate(props: FieldTemplateProps) {
  if (props.hidden) return <div style={{ display: 'none' }}>{props.children}</div>
  return <Box sx={{ minWidth: 0 }}>{props.children}</Box>
}

function AppArrayFieldTemplate(props: ArrayFieldTemplateProps) {
  return (
    <Box sx={{ display: 'grid', gap: 1 }}>
      {props.title ? <Typography variant="caption" fontWeight={700}>{props.title}{props.required ? ' *' : ''}</Typography> : null}
      {typeof props.schema.description === 'string' ? (
        <Typography variant="caption" color="text.secondary">{props.schema.description}</Typography>
      ) : null}
      {props.items.map((item, index) => (
        <Box key={index} sx={{ minWidth: 0 }}>{item}</Box>
      ))}
      {props.rawErrors?.length ? <FormHelperText error>{props.rawErrors.join(', ')}</FormHelperText> : null}
      {props.canAdd && !props.disabled && !props.readonly ? (
        <AppButton type="button" variant="outlined" startIcon={<Plus size={14} />} onClick={props.onAddClick} sx={{ justifySelf: 'start' }}>
          Add item
        </AppButton>
      ) : null}
    </Box>
  )
}

function RjsfActionButton({ props, label, icon }: { props: RjsfIconButtonProps; label: string; icon: ReactNode }) {
  return (
    <IconButton
      id={props.id}
      className={props.className}
      type="button"
      size="small"
      disabled={props.disabled}
      onClick={props.onClick}
      title={typeof props.title === 'string' ? props.title : label}
      aria-label={typeof props.title === 'string' ? props.title : label}
    >
      {icon}
    </IconButton>
  )
}

function AddButton(props: RjsfIconButtonProps) {
  return (
    <AppButton
      id={props.id}
      className={props.className}
      type="button"
      size="small"
      variant="outlined"
      disabled={props.disabled}
      onClick={props.onClick}
      startIcon={<Plus size={13} />}
    >
      {typeof props.title === 'string' ? props.title : 'Add'}
    </AppButton>
  )
}

function RemoveButton(props: RjsfIconButtonProps) {
  return <RjsfActionButton props={props} label="Remove" icon={<Trash2 size={14} />} />
}

function MoveUpButton(props: RjsfIconButtonProps) {
  return <RjsfActionButton props={props} label="Move up" icon={<ArrowUp size={14} />} />
}

function MoveDownButton(props: RjsfIconButtonProps) {
  return <RjsfActionButton props={props} label="Move down" icon={<ArrowDown size={14} />} />
}

function CopyButton(props: RjsfIconButtonProps) {
  return <RjsfActionButton props={props} label="Copy" icon={<Copy size={14} />} />
}

function AppObjectFieldTemplate(props: ObjectFieldTemplateProps) {
  const visible = props.properties.filter(property => !property.hidden)
  const normal = visible.filter(property => !isAdvancedProperty(props.schema, property.name))
  const advanced = visible.filter(property => isAdvancedProperty(props.schema, property.name))
  const sections = new Map<string, typeof normal>()

  for (const property of normal) {
    const section = getPropertyMetadata(props.schema, property.name, 'x-section') ?? 'General'
    const list = sections.get(String(section)) ?? []
    list.push(property)
    sections.set(String(section), list)
  }

  return (
    <Box sx={{ display: 'grid', gap: 2 }}>
      {props.title ? <Typography variant="subtitle2" fontWeight={800}>{props.title}</Typography> : null}
      {typeof props.description === 'string' && props.description ? (
        <Typography variant="caption" color="text.secondary">{props.description}</Typography>
      ) : null}
      {[...sections.entries()].map(([section, properties]) => (
        <Box key={section} sx={{ display: 'grid', gap: 1.5 }}>
          {sections.size > 1 ? <Typography variant="overline" color="primary.light">{section}</Typography> : null}
          {properties.map(property => <Box key={property.name}>{property.content}</Box>)}
        </Box>
      ))}
      {advanced.length > 0 ? (
        <Box component="details" sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 1.5 }}>
          <Typography component="summary" variant="caption" fontWeight={800} sx={{ cursor: 'pointer', color: 'text.secondary' }}>
            Advanced
          </Typography>
          <Box sx={{ display: 'grid', gap: 1.5, pt: 1.5 }}>
            {advanced.map(property => <Box key={property.name}>{property.content}</Box>)}
          </Box>
        </Box>
      ) : null}
    </Box>
  )
}

function getPropertyMetadata(schema: RJSFSchema, propertyName: string, key: string): unknown {
  const property = schema.properties?.[propertyName]
  if (!property || typeof property === 'boolean') return undefined
  return (property as Record<string, unknown>)[key]
}

function isAdvancedProperty(schema: RJSFSchema, propertyName: string): boolean {
  return getPropertyMetadata(schema, propertyName, 'x-advanced') === true
}

const widgets = {
  TextWidget,
  PasswordWidget,
  TextareaWidget,
  UpDownWidget: NumberWidget,
  RangeWidget: NumberWidget,
  CheckboxWidget,
  SelectWidget,
}

const templates = {
  FieldTemplate: AppFieldTemplate,
  ObjectFieldTemplate: AppObjectFieldTemplate,
  ArrayFieldTemplate: AppArrayFieldTemplate,
  ButtonTemplates: {
    AddButton,
    RemoveButton,
    MoveUpButton,
    MoveDownButton,
    CopyButton,
  },
}

export function AppSchemaForm({
  schema,
  uiSchema,
  formData,
  disabled = false,
  readonly = false,
  submitLabel,
  onChange,
  onSubmit,
}: AppSchemaFormProps) {
  return (
    <Box className="app-schema-form" sx={{ display: 'grid', gap: 1.5 }}>
      <Form
        schema={schema}
        uiSchema={uiSchema}
        validator={validator}
        formData={formData}
        disabled={disabled}
        readonly={readonly}
        widgets={widgets}
        templates={templates}
        showErrorList={false}
        liveValidate="onChange"
        onChange={event => onChange?.((event.formData ?? {}) as Record<string, unknown>)}
        onSubmit={event => onSubmit?.((event.formData ?? {}) as Record<string, unknown>)}
      >
        {submitLabel && onSubmit ? <AppButton type="submit">{submitLabel}</AppButton> : <></>}
      </Form>
    </Box>
  )
}

export interface LegacySchemaOption {
  value: string | number
  label_key?: string
  label?: string
}

export interface LegacySchemaField {
  key: string
  type: 'string' | 'secret' | 'password' | 'number' | 'integer' | 'boolean' | 'select' | 'enum' | 'textarea' | 'string_list' | 'array'
  label_key?: string
  label?: string
  description_key?: string
  description?: string
  default?: RJSFSchema['default']
  required?: boolean
  min?: number
  max?: number
  step?: number
  options?: LegacySchemaOption[]
  advanced?: boolean
  section?: string
  order?: number
}

export function legacyFieldsToSchema(fields: LegacySchemaField[], translate: (key: string) => string): { schema: RJSFSchema; uiSchema: UiSchema } {
  const ordered = [...fields].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
  const properties: Record<string, RJSFSchema> = {}
  const required: string[] = []
  const uiSchema: UiSchema = { 'ui:order': ordered.map(field => field.key) }

  for (const field of ordered) {
    const label = field.label_key ? translate(field.label_key) : field.label ?? field.key
    const description = field.description_key ? translate(field.description_key) : field.description
    const base: RJSFSchema = {
      title: label,
      description,
      default: field.default,
      ...(field.min !== undefined ? { minimum: field.min } : {}),
      ...(field.max !== undefined ? { maximum: field.max } : {}),
      ...(field.step !== undefined ? { multipleOf: field.step } : {}),
      'x-advanced': field.advanced ?? false,
      'x-section': field.section ?? 'General',
      'x-order': field.order ?? 0,
    }

    if (field.type === 'boolean') base.type = 'boolean'
    else if (field.type === 'number') base.type = 'number'
    else if (field.type === 'integer') base.type = 'integer'
    else if (field.type === 'string_list' || field.type === 'array') {
      base.type = 'array'
      base.items = { type: 'string' }
    } else {
      base.type = 'string'
    }

    if (field.type === 'select' || field.type === 'enum') {
      base.enum = field.options?.map(option => option.value)
      if (field.options?.length) {
        ;(uiSchema[field.key] ??= {})['ui:enumNames'] = field.options.map(option => option.label_key ? translate(option.label_key) : option.label ?? String(option.value))
      }
    }
    if (field.type === 'textarea') (uiSchema[field.key] ??= {})['ui:widget'] = 'textarea'
    if (field.type === 'secret' || field.type === 'password') (uiSchema[field.key] ??= {})['ui:widget'] = 'password'
    if (field.required) required.push(field.key)
    properties[field.key] = base
  }

  return {
    schema: { type: 'object', properties, required, additionalProperties: false },
    uiSchema,
  }
}

export default AppSchemaForm
