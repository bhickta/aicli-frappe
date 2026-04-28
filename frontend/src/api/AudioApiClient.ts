/**
 * Audio API Client — Typed interface to Audio Studio backend endpoints.
 */
import { frappe } from './FrappeClient'
import { API_BASE } from '../constants/api.constants'

export interface AudioJobSummary {
  name: string
  status: string
  whisper_model: string
  llm_model: string
  total_tracks: number
  transcribed_tracks: number
  analyzed_tracks: number
  failed_tracks: number
  creation: string
}

export interface AudioTrack {
  name: string
  file_url: string
  original_filename: string
  status: string
  transcript: string
  duration_seconds: number
  genre: string
  mood: string
  language: string
  topics: string[]
  summary: string
  suggested_title: string
  content_type: string
  playlist_name: string
  error: string
  elapsed_seconds: number
}

export interface Playlist {
  playlist_name: string
  description: string
  track_indices: number[]
  tracks: AudioTrack[]
}

export class AudioApiClient {
  async uploadFiles(
    files: File[], whisperModel: string, llmModel: string
  ): Promise<{ job_name: string; tracks: number }> {
    const csrfToken = await frappe.getCsrfToken()
    const formData = new FormData()
    for (const f of files) {
      formData.append('files', f)
    }
    formData.append('whisper_model', whisperModel)
    formData.append('llm_model', llmModel)

    const headers: Record<string, string> = { Accept: 'application/json' }
    if (csrfToken) headers['X-Frappe-CSRF-Token'] = csrfToken

    const res = await fetch(
      `${API_BASE}/api/method/aicli.api.upload_audio`,
      { method: 'POST', headers, body: formData }
    )
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    return data.message
  }

  async startPipeline(jobName: string, maxWorkers = 2): Promise<{ job_name: string; status: string }> {
    return frappe.call('start_audio_pipeline', { job_name: jobName, max_workers: maxWorkers })
  }

  async getStatus(jobName: string): Promise<any> {
    return frappe.call('audio_job_status', { job_name: jobName })
  }

  async getTracks(jobName: string): Promise<AudioTrack[]> {
    const res = await frappe.call('audio_tracks', { job_name: jobName })
    return res || []
  }

  async getPlaylists(jobName: string): Promise<Playlist[]> {
    const res = await frappe.call('audio_playlists', { job_name: jobName })
    return res || []
  }

  async listJobs(): Promise<AudioJobSummary[]> {
    const res = await frappe.call('audio_jobs')
    return res || []
  }

  async deleteJob(jobName: string): Promise<{ ok: boolean }> {
    return frappe.call('delete_audio_job', { job_name: jobName })
  }

  async stopJob(jobName: string): Promise<{ status: string }> {
    return frappe.call('stop_audio_job', { job_name: jobName })
  }
}

export const audioApi = new AudioApiClient()
