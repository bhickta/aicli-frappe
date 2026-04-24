import { API_BASE } from '../constants/api.constants'

export class FrappeClient {
  private static instance: FrappeClient
  private baseUrl: string = API_BASE
  private csrfToken: string | null = null

  private constructor() {}

  public static getInstance(): FrappeClient {
    if (!FrappeClient.instance) {
      FrappeClient.instance = new FrappeClient()
    }
    return FrappeClient.instance
  }

  async getCsrfToken(): Promise<string> {
    if (!this.csrfToken) {
      try {
        const tokenRes = await fetch(`${this.baseUrl}/api/method/aicli.api.get_csrf_token`)
        const tokenData = await tokenRes.json()
        this.csrfToken = tokenData.message
      } catch (e) {
        console.warn("Could not fetch CSRF token", e)
      }
    }
    return this.csrfToken || ""
  }

  async call(method: string, args: any = {}): Promise<any> {
    await this.getCsrfToken()

    const url = `${this.baseUrl}/api/method/aicli.api.${method}`
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    }
    if (this.csrfToken) {
      headers['X-Frappe-CSRF-Token'] = this.csrfToken
    }

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(args),
    })

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: 'Request failed' }))
      throw new Error(body.message ?? body.detail ?? `HTTP ${res.status}`)
    }

    const data = await res.json()
    return data.message
  }
}

export const frappe = FrappeClient.getInstance()
