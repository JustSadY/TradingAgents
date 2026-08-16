import { isAxiosError } from 'axios'

/**
 * The message FastAPI put in the response body, if there is one.
 *
 * Every failing endpoint answers with `{"detail": ...}`, so five pages had each
 * grown their own copy of the same reach into the error object — written as a
 * cast through `unknown`, which meant none of them was checked against what
 * axios actually produces.
 *
 * `detail` is a string for `HTTPException`, but FastAPI's own 422 handler puts
 * a list of validation errors there instead. Only the string form is a message
 * a user can read, so anything else yields `null` and the caller falls back to
 * its own wording.
 */
export function errorDetail(error: unknown): string | null {
  if (!isAxiosError(error)) return null
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
  return typeof detail === 'string' && detail.trim() ? detail : null
}
