/**
 * Narrow an unknown value to a plain object.
 *
 * Arrays are excluded deliberately: every caller here is about to read named
 * keys off a payload, and `typeof [] === 'object'` would let an array through
 * to code that then reads `.ticker` off it and gets `undefined`.
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
