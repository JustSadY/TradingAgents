import axios from 'axios'
import { getAccessToken } from '../contexts/AuthContext'
import { notify } from './notify'

const api = axios.create({
  baseURL: '/',
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'An unexpected error occurred'
    // Avoid notifying for 401s as they are handled by auth hooks/login page
    if (error.response?.status !== 401) {
       notify('error', message, 'API Error')
    }
    return Promise.reject(error)
  }
)

export default api
