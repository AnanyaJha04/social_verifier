export interface Session {
  id: string
  url: string
  source_type: 'youtube_live' | 'direct'
  status: 'starting' | 'capturing' | 'stopped' | 'error'
  created_at: string
  started_at: string | null
  ended_at: string | null
}

export interface NewspaperArticle {
  clip_id: string
  headline: string
  body: string
}

export interface NewspaperSection {
  name: string
  articles: NewspaperArticle[]
}

export interface NewspaperContent {
  masthead: string
  sections: NewspaperSection[]
}

export interface Newspaper {
  session_id: string
  content: string
  created_at: string
}

export interface FullArticle {
  clip_id: string
  article: string
}

export interface Clip {
  id: string
  session_id: string
  title: string
  summary: string
  start_seconds: number
  end_seconds: number
  status: string
  created_at: string
}

export type ClipReelStatus = 'generating' | 'done' | 'error'

export interface ClipReel {
  id: string
  clip_id: string
  status: ClipReelStatus
  hook_text: string | null
  audio_style: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type SessionEvent =
  | { type: 'status'; status: string }
  | { type: 'transcript_tick'; text: string; start: number; end: number }
  | { type: 'segment_boundary_detected'; title: string; summary: string; start: number; end: number }
  | { type: 'clip_ready'; clip_id: string; title: string; video_url: string; thumbnail_url: string }
  | { type: 'error'; message: string }

export type Verdict = 'true' | 'false' | 'misleading' | 'partially true' | 'unverifiable'

export interface ClaimVerification {
  quote: string
  timestamp: string
  claim: string
  verdict: Verdict
  analysis: string
  sources: string[]
  grounded: boolean
  official_sources: string[]
  official_verdict: GovVerdict
  official_analysis: string
  start_seconds: number
  end_seconds: number
}

export type GovVerdict = 'confirmed' | 'contradicted' | 'partially confirmed' | 'not addressed' | 'no source found'

export type ReelCheckStatus =
  | 'queued'
  | 'downloading'
  | 'transcribing'
  | 'extracting_claims'
  | 'verifying_claims'
  | 'concluding'
  | 'done'
  | 'error'

export interface ReelCheck {
  id: string
  url: string
  status: ReelCheckStatus
  progress: string
  manuscript: string | null
  claims: ClaimVerification[]
  conclusion: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type BatchStatus = 'processing' | 'done'

export interface Batch {
  id: string
  status: BatchStatus
  created_at: string
  completed_at: string | null
  checks: ReelCheck[]
}

export interface TimelineItem {
  type: 'claim' | 'upload'
  claim_index: number | null
  upload_id: string | null
}

export interface Timeline {
  check_id: string
  items: TimelineItem[]
}

export interface EditorUpload {
  id: string
  check_id: string
  filename: string
  duration_seconds: number
}

export type EditorExportStatus = 'compiling' | 'done' | 'error'

export interface EditorExport {
  id: string
  check_id: string
  status: EditorExportStatus
  output_path: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type InstagramKitStatus = 'generating' | 'done' | 'error'

export interface InstagramKit {
  id: string
  export_id: string
  check_id: string
  status: InstagramKitStatus
  caption: string | null
  best_time: string | null
  audio_style: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type DebunkScriptStatus = 'generating' | 'done' | 'error'

export interface DebunkBeat {
  claim_index: number
  claim_quote: string
  verdict: Verdict
  reaction_narration: string
  humor_cue: string | null
  question_cue: string | null
}

export interface DebunkScript {
  id: string
  check_id: string
  status: DebunkScriptStatus
  title: string | null
  intro_hook: string | null
  beats: DebunkBeat[]
  outro_cta: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

// ---------------------------------------------------------------------------
// Observability Dashboard
// ---------------------------------------------------------------------------

export interface ObsSummary {
  period_hours: number
  total_checks: number
  done: number
  error: number
  in_progress: number
  success_rate_pct: number | null
  pipeline_error_rate_pct: number | null
  avg_check_duration_s: number | null
  total_pipeline_events: number
}

export interface ObsStageStats {
  stage: string
  total_events: number
  ok_count: number
  error_count: number
  avg_duration_ms: number | null
  p95_duration_ms: number | null
  error_rate_pct: number | null
}

export interface ObsExecution {
  id: string
  status: string
  claim_count: number
  verdict_counts: Record<string, number>
  created_at: string
  completed_at: string | null
  duration_s: number | null
}

export interface ObsExecutions {
  total: number
  offset: number
  limit: number
  items: ObsExecution[]
}

export interface ObsErrorEvent {
  check_id: string
  stage: string
  duration_ms: number | null
  error_type: string | null
  recorded_at: string
}
