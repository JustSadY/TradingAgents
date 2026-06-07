// The default axios instance is fully configured in AuthContext (auth header,
// 401 token refresh + retry/queue, and 5xx error toasts). AuthProvider always
// loads, so those interceptors are always attached.
//
// This module used to export a *separate* axios.create() instance that only had
// the auth header — it lacked the refresh logic, so requests made through it
// 401'd silently without refreshing or logging the user out. Re-export the
// configured default instance so every caller shares one client.
import axios from 'axios'

export default axios
