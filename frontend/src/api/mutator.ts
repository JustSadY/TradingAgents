import axios, { type AxiosRequestConfig } from 'axios'

/**
 * HTTP transport for every Orval-generated hook.
 *
 * This deliberately uses the *default* axios instance rather than a fresh
 * `axios.create()`. AuthContext attaches the auth header, the 401 refresh +
 * retry queue, and the 5xx toast handling to that instance; a separate client
 * would silently miss all of it and 401 without refreshing. See utils/api.ts,
 * which exists for the same reason.
 *
 * The `signal` passed by TanStack Query is forwarded so cancelled or superseded
 * queries actually abort their request instead of running to completion.
 */
export const customInstance = async <T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig,
): Promise<T> => {
  const { data } = await axios({ ...config, ...options })
  return data as T
}

export default customInstance
