import { API_BASE } from '../constants/api.constants';
import { frappe } from './FrappeClient';

export interface RecallHistoryItem {
  name: string;
  notes: string;
  triggers: string;
  model: string;
  timestamp: string;
}

class RecallApiClient {
  async generateTriggers(notes: string) {
    const response = await frappe.call('generate_recall_triggers', { notes });
    return response;
  }

  async getHistory(limit: number = 20): Promise<RecallHistoryItem[]> {
    const response = await frappe.call('get_recall_history', { limit });
    return response || [];
  }
}

export const recallApi = new RecallApiClient();
