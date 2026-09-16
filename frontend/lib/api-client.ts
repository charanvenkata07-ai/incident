class ApiClient {
  private baseUrl: string
  private token: string | null

  constructor() {
    this.baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    this.token = null
  }

  setToken(token: string) { this.token = token }
  clearToken() { this.token = null }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`
    }
    const res = await fetch(`${this.baseUrl}${path}`, { ...options, headers: { ...headers, ...options?.headers } })
    if (!res.ok) {
      if (res.status === 401) {
        this.clearToken()
        if (typeof window !== 'undefined') {
          window.location.href = '/login'
        }
        throw new Error('Session expired')
      }
      const error = await res.json().catch(() => ({ detail: 'An error occurred' }))
      throw new Error(error.detail || `Request failed: ${res.status}`)
    }
    if (res.status === 204) return {} as T
    return res.json()
  }

  get<T>(path: string) { return this.request<T>(path) }
  post<T>(path: string, body?: unknown) { return this.request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }) }
  patch<T>(path: string, body?: unknown) { return this.request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }) }
  delete<T>(path: string) { return this.request<T>(path, { method: 'DELETE' }) }
}

export const apiClient = new ApiClient()
