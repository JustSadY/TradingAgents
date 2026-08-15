import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { errorDetail } from '../errorDetail'

function axiosErrorWith(data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() }
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, null, {
    data,
    status: 400,
    statusText: 'Bad Request',
    headers: {},
    config,
  })
}

describe('errorDetail', () => {
  it('returns the detail FastAPI sent', () => {
    expect(errorDetail(axiosErrorWith({ detail: 'Insufficient cash' }))).toBe('Insufficient cash')
  })

  it('ignores a 422 validation list, which is not a readable message', () => {
    const validationError = axiosErrorWith({
      detail: [{ loc: ['body', 'ticker'], msg: 'field required', type: 'missing' }],
    })

    expect(errorDetail(validationError)).toBeNull()
  })

  it.each([
    ['no body', axiosErrorWith(undefined)],
    ['a body without detail', axiosErrorWith({ message: 'nope' })],
    ['an empty detail', axiosErrorWith({ detail: '   ' })],
    ['a non-axios error', new Error('network down')],
    ['a thrown string', 'boom'],
    ['null', null],
  ])('returns null for %s', (_label, error) => {
    expect(errorDetail(error)).toBeNull()
  })
})
