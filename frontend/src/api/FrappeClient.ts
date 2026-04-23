import { API_BASE } from '../constants/api.constants'

export class FrappeClient {
  private static instance: FrappeClient
  private baseUrl: string = API_BASE

  private constructor() {}

  public static getInstance(): FrappeClient {
    if (!FrappeClient.instance) {
      FrappeClient.instance = new FrappeClient()
    }
    return FrappeClient.instance
  }

  async call(method: string, args: any = {}): Promise<any> {
    const url = `${this.baseUrl}/api/method/aicli.api.${method}`
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
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
