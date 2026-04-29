import { frappe } from './FrappeClient'

export class SettingsApiClient {
  async fetchSettings(): Promise<any> {
    return frappe.call('get_settings')
  }

  async updateSettings(config: any): Promise<any> {
    return frappe.call('update_settings', config)
  }

  async fetchProviders(): Promise<any> {
    // For now, providers are static or can be fetched via a method
    return ['ollama', 'lms', 'lmstudio', 'vllm', 'openai', 'anthropic', 'gemini', 'openrouter']
  }

  async fetchModels(): Promise<any> {
    const res = await frappe.call('list_models')
    return res || { models: [] }
  }
}

export const settingsApi = new SettingsApiClient()
