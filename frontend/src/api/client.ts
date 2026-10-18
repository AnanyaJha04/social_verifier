import { apiUrl } from './base'
import { clearToken, getToken } from './auth'
import type {
  Batch,
  Clip,
  ClipReel,
  DebunkScript,
  EditorExport,
  EditorUpload,
  FullArticle,
  InstagramKit,
  Newspaper,
  ObsErrorEvent,
  ObsExecutions,
  ObsStageStats,
  ObsSummary,
  ReelCheck,
  Session,
  Timeline,
  TimelineItem,
} from './types'

function authHeader(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// A 401 means the token is missing/stale (e.g. the backend restarted, which
// mints a fresh session token) -- clear it and bounce to the login screen
// rather than surfacing a confusing fetch error on whatever page was open.
function handleUnauthorized() {
  clearToken()
  if (window.location.pathname !== '/login') window.location.href = '/login'
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    credentials: 'include',
    ...options,
  })
  if (res.status === 401) {
    handleUnauthorized()
    throw new Error('401 Unauthorized')
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  login: async (username: string, password: string): Promise<{ token: string }> => {
    // Deliberately not using request(): a failed login is a normal 401 here,
    // not a stale-session signal, so it must not trigger the global
    // clear-token-and-redirect-to-login handling request() does for 401s.
    const res = await fetch(apiUrl('/api/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
    }
    return res.json()
  },

  createSession: (url: string) =>
    request<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ url }) }),
  listSessions: () => request<Session[]>('/api/sessions'),
  getSession: (id: string) => request<Session>(`/api/sessions/${id}`),
  stopSession: (id: string) => request<Session>(`/api/sessions/${id}/stop`, { method: 'POST' }),
  generateNewspaper: (id: string) =>
    request<Newspaper>(`/api/sessions/${id}/newspaper`, { method: 'POST' }),
  getNewspaper: (id: string) => request<Newspaper>(`/api/sessions/${id}/newspaper`),

  listClips: (sessionId: string) => request<Clip[]>(`/api/sessions/${sessionId}/clips`),
  renameClip: (id: string, fields: { title?: string; summary?: string }) =>
    request<Clip>(`/api/clips/${id}`, { method: 'PATCH', body: JSON.stringify(fields) }),
  retrimClip: (id: string, start_seconds: number, end_seconds: number) =>
    request<Clip>(`/api/clips/${id}/retrim`, {
      method: 'POST',
      body: JSON.stringify({ start_seconds, end_seconds }),
    }),

  createClipReel: (clipId: string) =>
    request<ClipReel>(`/api/clips/${clipId}/reel`, { method: 'POST' }),
  getClipReel: (clipId: string, reelId: string) =>
    request<ClipReel>(`/api/clips/${clipId}/reel/${reelId}`),
  deleteClip: (id: string) => request<{ ok: boolean }>(`/api/clips/${id}`, { method: 'DELETE' }),
  getFullArticle: (clipId: string) =>
    request<FullArticle>(`/api/clips/${clipId}/full-article`, { method: 'POST' }),

  createReelCheck: (url: string) =>
    request<ReelCheck>('/api/verify', { method: 'POST', body: JSON.stringify({ url }) }),
  listReelChecks: () => request<ReelCheck[]>('/api/verify'),
  getReelCheck: (id: string) => request<ReelCheck>(`/api/verify/${id}`),

  createBatch: (urls: string[]) =>
    request<Batch>('/api/verify/batch', { method: 'POST', body: JSON.stringify({ urls }) }),
  listBatches: () => request<Batch[]>('/api/verify/batches'),
  getBatch: (id: string) => request<Batch>(`/api/verify/batch/${id}`),

  getTimeline: (checkId: string) => request<Timeline>(`/api/verify/${checkId}/editor/timeline`),
  setTimeline: (checkId: string, items: TimelineItem[]) =>
    request<Timeline>(`/api/verify/${checkId}/editor/timeline`, {
      method: 'PUT',
      body: JSON.stringify(items),
    }),
  listUploads: (checkId: string) => request<EditorUpload[]>(`/api/verify/${checkId}/editor/uploads`),
  uploadEditorVideo: async (checkId: string, file: File): Promise<EditorUpload> => {
    const form = new FormData()
    form.append('file', file)
    // Deliberately not using request(): it forces a JSON Content-Type,
    // which would break the multipart boundary the browser needs to set
    // itself for FormData bodies.
    const res = await fetch(apiUrl(`/api/verify/${checkId}/editor/uploads`), {
      method: 'POST', body: form, headers: authHeader(), credentials: 'include',
    })
    if (res.status === 401) {
      handleUnauthorized()
      throw new Error('401 Unauthorized')
    }
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text().catch(() => '')}`)
    return res.json()
  },
  compileTimeline: (checkId: string) =>
    request<EditorExport>(`/api/verify/${checkId}/editor/compile`, { method: 'POST' }),
  getExport: (checkId: string, exportId: string) =>
    request<EditorExport>(`/api/verify/${checkId}/editor/exports/${exportId}`),

  createInstagramKit: (checkId: string, exportId: string) =>
    request<InstagramKit>(`/api/verify/${checkId}/editor/exports/${exportId}/instagram`, {
      method: 'POST',
    }),
  getInstagramKit: (checkId: string, exportId: string, kitId: string) =>
    request<InstagramKit>(`/api/verify/${checkId}/editor/exports/${exportId}/instagram/${kitId}`),

  createDebunkScript: (checkId: string) =>
    request<DebunkScript>(`/api/verify/${checkId}/debunk-script`, { method: 'POST' }),
  getDebunkScript: (checkId: string, scriptId: string) =>
    request<DebunkScript>(`/api/verify/${checkId}/debunk-script/${scriptId}`),

  // Observability dashboard (read-only, no sensitive data)
  getObsSummary: (hours = 24) =>
    request<ObsSummary>(`/api/observability/summary?hours=${hours}`),
  getObsStageStats: (hours = 24) =>
    request<ObsStageStats[]>(`/api/observability/stage-stats?hours=${hours}`),
  getObsExecutions: (hours = 24, limit = 50, offset = 0) =>
    request<ObsExecutions>(`/api/observability/executions?hours=${hours}&limit=${limit}&offset=${offset}`),
  getObsErrors: (hours = 24, limit = 30) =>
    request<ObsErrorEvent[]>(`/api/observability/errors?hours=${hours}&limit=${limit}`),
}
