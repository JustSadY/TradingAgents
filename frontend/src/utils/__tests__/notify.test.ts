import { describe, it, expect, vi, beforeEach } from 'vitest'
import { formatErrorDetail, notify } from '../notify'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('formatErrorDetail', () => {
  it('returns Unknown error for null/undefined', () => {
    expect(formatErrorDetail(null)).toBe('Unknown error')
    expect(formatErrorDetail(undefined)).toBe('Unknown error')
  })

  it('returns string as is', () => {
    expect(formatErrorDetail('Something went wrong')).toBe('Something went wrong')
  })

  it('formats array of error objects', () => {
    const detail = [
      { loc: ['body', 'username'], msg: 'Field required', type: 'missing' },
      { loc: ['query', 'limit'], msg: 'Value must be > 0', type: 'value_error' },
    ]
    const result = formatErrorDetail(detail)
    expect(result).toContain('username: Field required')
    expect(result).toContain('limit: Value must be > 0')
  })

  it('strips body/query from loc segments', () => {
    const detail = [{ loc: ['body', 'password'], msg: 'Too short' }]
    expect(formatErrorDetail(detail)).toBe('password: Too short')
  })

  it('handles array items without loc', () => {
    const detail = [{ msg: 'Generic error' }]
    expect(formatErrorDetail(detail)).toBe('Generic error')
  })

  it('extracts message from object', () => {
    expect(formatErrorDetail({ message: 'Oops' })).toBe('Oops')
  })

  it('extracts msg from object', () => {
    expect(formatErrorDetail({ msg: 'Error occurred' })).toBe('Error occurred')
  })

  it('recursively extracts detail from object', () => {
    expect(formatErrorDetail({ detail: 'Nested detail' })).toBe('Nested detail')
  })

  it('JSON stringifies unknown objects', () => {
    const obj = { foo: 'bar' }
    expect(formatErrorDetail(obj)).toBe(JSON.stringify(obj))
  })

  it('converts non-string primitives', () => {
    expect(formatErrorDetail(42)).toBe('42')
    expect(formatErrorDetail(true)).toBe('true')
  })
})

describe('notify', () => {
  beforeEach(() => {
    vi.spyOn(window, 'dispatchEvent')
  })

  it('dispatches a ta-notify custom event', () => {
    notify('success', 'Operation completed', 'Success')
    expect(window.dispatchEvent).toHaveBeenCalled()
    const event = (window.dispatchEvent as any).mock.calls[0][0]
    expect(event.type).toBe('ta-notify')
    expect(event.detail.type).toBe('success')
    expect(event.detail.message).toBe('Operation completed')
    expect(event.detail.title).toBe('Success')
    expect(event.detail.visibility).toBe('all')
  })

  it('deduplicates same error within 3 seconds', () => {
    notify('error', 'Server error', 'HTTP 500')
    notify('error', 'Server error', 'HTTP 500')
    expect(window.dispatchEvent).toHaveBeenCalledTimes(1)
  })

  it('allows different error messages through', () => {
    notify('error', 'Error A', 'Title')
    notify('error', 'Error B', 'Title')
    expect(window.dispatchEvent).toHaveBeenCalledTimes(2)
  })

  it('converts object message to formatted string', () => {
    notify('warning', { message: 'Disk space low' })
    const event = (window.dispatchEvent as any).mock.calls[0][0]
    expect(event.detail.message).toBe('Disk space low')
  })

  it('respects visibility parameter', () => {
    notify('info', 'Admin only message', undefined, 'admin')
    const event = (window.dispatchEvent as any).mock.calls[0][0]
    expect(event.detail.visibility).toBe('admin')
  })
})
