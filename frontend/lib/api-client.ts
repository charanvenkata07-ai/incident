class ApiClient {
  private baseUrl: string
  private token: string | null

  constructor() {
    this.baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    this.token = null
  }

  setToken(token: string) { this.token = token }
  clearToken() { this.token = null }

  getToken(): string | null {
    if (this.token) return this.token
    if (typeof window !== 'undefined') {
      try {
        return localStorage.getItem('auth_token')
      } catch {
        return null
      }
    }
    return null
  }

  getBaseUrl(): string {
    // 1. Prioritize environment-configured API URL
    if (process.env.NEXT_PUBLIC_API_URL) {
      return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '')
    }
    // 2. Dynamically match client network host (e.g. 10.x LAN, localhost)
    if (typeof window !== 'undefined') {
      return `${window.location.protocol}//${window.location.hostname}:8000`
    }
    // 3. Localhost development fallback
    return 'http://localhost:8000'
  }

  getMediaUrl(pathOrKey: string): string {
    if (!pathOrKey) return ''
    let fullUrl = pathOrKey
    if (!pathOrKey.startsWith('http://') && !pathOrKey.startsWith('https://')) {
      const base = this.getBaseUrl()
      const clean = pathOrKey.startsWith('/') ? pathOrKey : `/${pathOrKey}`
      fullUrl = `${base}${clean}`
    }
    // If chat attachment file URL, append auth token as query parameter for media tags (img, video, audio, download)
    if (fullUrl.includes('/api/chat/attachments/') && fullUrl.endsWith('/file')) {
      const token = this.getToken()
      if (token && !fullUrl.includes('token=')) {
        const sep = fullUrl.includes('?') ? '&' : '?'
        fullUrl = `${fullUrl}${sep}token=${encodeURIComponent(token)}`
      }
    }
    return fullUrl
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    const token = this.getToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const baseUrl = this.getBaseUrl()
    
    let res: Response
    try {
      res = await fetch(`${baseUrl}${path}`, { ...options, headers: { ...headers, ...options?.headers } })
    } catch (networkErr: any) {
      if (typeof window !== 'undefined' && path.startsWith('/api')) {
        try {
          res = await fetch(path, { ...options, headers: { ...headers, ...options?.headers } })
        } catch {
          throw new Error(`IncidentFlow server at ${baseUrl} could not be reached. Check network or server status.`)
        }
      } else {
        throw new Error(`IncidentFlow server at ${baseUrl} could not be reached. Check network or server status.`)
      }
    }

    if (!res.ok) {
      if (res.status === 401) {
        this.clearToken()
        if (typeof window !== 'undefined') {
          try {
            localStorage.removeItem('auth_token')
          } catch {
            // ignore
          }
        }
        const error = await res.json().catch(() => null)
        if (path.includes('/auth/login')) {
          throw new Error(error?.detail || error?.message || 'Invalid email or password. Please try again.')
        }
        throw new Error('Your session has expired. Please sign in again.')
      }
      if (res.status === 403) {
        const error = await res.json().catch(() => null)
        throw new Error(error?.detail || error?.message || 'Access denied. You do not have permission for this action.')
      }
      if (res.status === 404) {
        const error = await res.json().catch(() => null)
        throw new Error(error?.detail || error?.message || 'The requested resource was not found.')
      }
      const error = await res.json().catch(() => ({ detail: 'Server error' }))
      const msg = error.detail || error.message || error?.error?.message || `Request failed (${res.status})`
      throw new Error(msg)
    }
    if (res.status === 204) return {} as T
    return res.json()
  }

  get<T>(path: string) { return this.request<T>(path) }
  post<T>(path: string, body?: unknown) { return this.request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }) }
  patch<T>(path: string, body?: unknown) { return this.request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }) }
  delete<T>(path: string) { return this.request<T>(path, { method: 'DELETE' }) }

  uploadFile<T>(path: string, formData: FormData, onProgress?: (percent: number) => void): Promise<T> {
    return new Promise((resolve, reject) => {
      const baseUrl = this.getBaseUrl()
      const url = `${baseUrl}${path}`
      const xhr = new XMLHttpRequest()

      xhr.open('POST', url)
      const token = this.getToken()
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      }

      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.min(100, Math.round((event.loaded / event.total) * 100))
            onProgress(percent)
          }
        }
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText)
            resolve(data as T)
          } catch {
            resolve({} as T)
          }
        } else {
          let errorMsg = `Upload failed (${xhr.status})`
          try {
            const err = JSON.parse(xhr.responseText)
            errorMsg = err.detail || err.message || errorMsg
          } catch {}
          reject(new Error(errorMsg))
        }
      }

      xhr.onerror = () => {
        reject(new Error(`Failed to upload media to ${baseUrl}. Network connection failed.`))
      }

      xhr.ontimeout = () => {
        reject(new Error(`Upload timed out to ${baseUrl}.`))
      }

      xhr.send(formData)
    })
  }
}

export const apiClient = new ApiClient()
