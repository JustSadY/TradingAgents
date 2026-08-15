import { useEffect } from 'react'
import { notify } from '../utils/notify'

/**
 * Surface a failed query as a toast.
 *
 * TanStack Query v5 removed the per-query `onError` callback, so pages that
 * previously toasted inside a try/catch need somewhere to do it. Reading
 * `response.data.detail` keeps FastAPI's error message visible instead of
 * replacing it with a generic string.
 */
export function useQueryErrorToast(error: unknown, fallback: string, title: string): void {
  useEffect(() => {
    if (!error) return
    const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    notify('error', detail || fallback, title)
  }, [error, fallback, title])
}

export default useQueryErrorToast
