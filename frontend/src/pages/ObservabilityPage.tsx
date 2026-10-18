import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ObsExecution, ObsStageStats } from '../api/types'
import { NavBar } from '../components/ui/NavBar'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Skeleton } from '../components/ui/Skeleton'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STAGE_LABELS: Record<string, string> = {
  downloading: 'Download',
  transcribing: 'Transcribe',
  extracting_claims: 'Extract Claims',
  verifying_claims: 'Verify Claims',
  concluding: 'Conclude',
}

const VERDICT_COLORS: Record<string, string> = {
  true: '#22c55e',
  false: '#ef4444',
  misleading: '#f97316',
  'partially true': '#eab308',
  unverifiable: '#6b7280',
}

const HOURS_OPTIONS = [
  { label: '1 h', value: 1 },
  { label: '6 h', value: 6 },
  { label: '24 h', value: 24 },
  { label: '7 d', value: 168 },
  { label: 'All time', value: 0 },
]

function fmt(n: number | null, unit = ''): string {
  if (n === null || n === undefined) return '—'
  if (unit === 's' && n >= 60) {
    const m = Math.floor(n / 60)
    const s = Math.round(n % 60)
    return `${m}m ${s}s`
  }
  return `${n.toLocaleString()}${unit}`
}

function fmtMs(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${ms}ms`
}

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  sub,
  accent,
  id,
}: {
  label: string
  value: string
  sub?: string
  accent?: boolean
  id: string
}) {
  return (
    <div
      id={id}
      className={`border-2 ${accent ? 'border-brand-600 bg-brand-950/30' : 'border-neutral-800 bg-neutral-950/80'} p-4 shadow-[4px_4px_0_0_#000] animate-slide-up`}
    >
      <p className="font-mono text-xs uppercase tracking-widest text-neutral-500">{label}</p>
      <p className={`mt-1 font-display text-3xl uppercase ${accent ? 'text-brand-400' : 'text-neutral-50'}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 font-mono text-xs text-neutral-600">{sub}</p>}
    </div>
  )
}

function StageBar({ stage }: { stage: ObsStageStats }) {
  const label = STAGE_LABELS[stage.stage] ?? stage.stage
  const errorRate = stage.error_rate_pct ?? 0
  const okWidth = stage.total_events > 0 ? 100 - errorRate : 0
  const errWidth = errorRate

  return (
    <div id={`stage-bar-${stage.stage}`} className="group">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-neutral-300">{label}</span>
        <div className="flex gap-3 text-xs font-mono">
          <span className="text-neutral-500">
            avg <span className="text-neutral-200">{fmtMs(stage.avg_duration_ms)}</span>
          </span>
          <span className="text-neutral-500">
            p95 <span className="text-neutral-200">{fmtMs(stage.p95_duration_ms)}</span>
          </span>
          <span className={`${errorRate > 0 ? 'text-brand-400' : 'text-neutral-600'}`}>
            {errorRate > 0 ? `${errorRate}% err` : '0% err'}
          </span>
        </div>
      </div>
      <div className="flex h-2 overflow-hidden border border-neutral-800 bg-neutral-900">
        <div
          className="h-full bg-emerald-600 transition-all duration-500"
          style={{ width: `${okWidth}%` }}
        />
        <div
          className="h-full bg-brand-600 transition-all duration-500"
          style={{ width: `${errWidth}%` }}
        />
        {stage.total_events === 0 && (
          <div className="h-full w-full bg-neutral-800 opacity-40" />
        )}
      </div>
      <p className="mt-0.5 font-mono text-[10px] text-neutral-700">
        {stage.total_events} event{stage.total_events !== 1 ? 's' : ''} · {stage.ok_count} ok · {stage.error_count} err
      </p>
    </div>
  )
}

function VerdictPips({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  if (total === 0) return <span className="font-mono text-xs text-neutral-700">—</span>
  return (
    <div className="flex gap-0.5">
      {Object.entries(counts).map(([verdict, n]) => (
        <div
          key={verdict}
          title={`${verdict}: ${n}`}
          className="h-2 rounded-sm transition-all"
          style={{
            width: `${Math.max(4, (n / total) * 48)}px`,
            backgroundColor: VERDICT_COLORS[verdict] ?? '#6b7280',
          }}
        />
      ))}
    </div>
  )
}

function ExecutionRow({ exec, onNavigate }: { exec: ObsExecution; onNavigate: (id: string) => void }) {
  const statusTone =
    exec.status === 'done' ? 'success' : exec.status === 'error' ? 'danger' : 'neutral'

  return (
    <tr
      id={`exec-row-${exec.id}`}
      className="group cursor-pointer border-b border-neutral-800/60 transition-colors hover:bg-neutral-900/60"
      onClick={() => onNavigate(exec.id)}
    >
      <td className="px-3 py-2.5">
        <code className="font-mono text-[11px] text-neutral-500 group-hover:text-neutral-300 transition">
          {exec.id.slice(0, 8)}
        </code>
      </td>
      <td className="px-3 py-2.5">
        <Badge tone={statusTone} dot pulse={exec.status !== 'done' && exec.status !== 'error'}>
          {exec.status}
        </Badge>
      </td>
      <td className="px-3 py-2.5">
        <VerdictPips counts={exec.verdict_counts} />
        {exec.claim_count > 0 && (
          <span className="ml-1 font-mono text-[10px] text-neutral-600">{exec.claim_count}</span>
        )}
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-neutral-400">
        {exec.duration_s !== null ? fmt(exec.duration_s, 's') : '—'}
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-neutral-600">
        {relTime(exec.created_at)}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ObservabilityPage() {
  const [hours, setHours] = useState(24)
  const [execOffset, setExecOffset] = useState(0)
  const EXEC_LIMIT = 20
  const navigate = useNavigate()

  const summaryQ = useQuery({
    queryKey: ['obs-summary', hours],
    queryFn: () => api.getObsSummary(hours),
    refetchInterval: 30_000,
  })

  const stagesQ = useQuery({
    queryKey: ['obs-stage-stats', hours],
    queryFn: () => api.getObsStageStats(hours),
    refetchInterval: 30_000,
  })

  const execsQ = useQuery({
    queryKey: ['obs-executions', hours, execOffset],
    queryFn: () => api.getObsExecutions(hours, EXEC_LIMIT, execOffset),
    refetchInterval: 30_000,
  })

  const errorsQ = useQuery({
    queryKey: ['obs-errors', hours],
    queryFn: () => api.getObsErrors(hours, 15),
    refetchInterval: 30_000,
  })

  const summary = summaryQ.data
  const stages = stagesQ.data ?? []
  const execs = execsQ.data
  const errors = errorsQ.data ?? []

  const handleHoursChange = (h: number) => {
    setHours(h)
    setExecOffset(0)
  }

  const anyError = summaryQ.isError || stagesQ.isError || execsQ.isError || errorsQ.isError

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <NavBar />

      {/* Header */}
      <div className="mb-8 animate-slide-up">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-5xl uppercase leading-[0.95] tracking-wide text-neutral-50">
              Pipeline <span className="bg-brand-500 px-2 text-black">Observatory</span>
            </h1>
            <p className="mt-2 font-mono text-sm text-neutral-500">
              Real-time verification pipeline health · auto-refreshes every 30 s
            </p>
          </div>

          {/* Time range picker */}
          <div
            id="obs-time-range"
            className="flex border-2 border-neutral-700 font-mono text-xs uppercase tracking-wider"
          >
            {HOURS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                id={`time-range-${opt.value}`}
                onClick={() => handleHoursChange(opt.value)}
                className={`px-3 py-1.5 transition ${
                  hours === opt.value
                    ? 'bg-brand-500 text-black'
                    : 'text-neutral-400 hover:text-neutral-100'
                } border-l-2 border-neutral-700 first:border-l-0`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error banner */}
      {anyError && (
        <div
          id="obs-error-banner"
          className="mb-6 border-2 border-brand-600 bg-brand-950/40 p-4 font-mono text-xs text-brand-300 animate-slide-up"
        >
          <span className="mr-2 text-brand-400">⚠</span>
          Failed to load observability data. The dashboard may show stale information.
        </div>
      )}

      {/* Overview stats */}
      <section id="obs-overview" className="mb-8">
        <h2 className="mb-3 font-display text-sm uppercase tracking-widest text-neutral-500">
          Overview
        </h2>
        {summaryQ.isLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
          </div>
        ) : summaryQ.isError ? (
          <p className="font-mono text-sm text-brand-400">Unable to load summary data.</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              id="stat-total"
              label="Total checks"
              value={fmt(summary?.total_checks ?? 0)}
              sub={`${fmt(summary?.in_progress ?? 0)} in progress`}
            />
            <StatCard
              id="stat-success"
              label="Success rate"
              value={summary?.success_rate_pct !== null ? `${summary!.success_rate_pct}%` : '—'}
              sub={`${fmt(summary?.done ?? 0)} done · ${fmt(summary?.error ?? 0)} failed`}
              accent={(summary?.success_rate_pct ?? 100) < 80}
            />
            <StatCard
              id="stat-duration"
              label="Avg duration"
              value={fmt(summary?.avg_check_duration_s ?? null, 's')}
              sub="end-to-end per check"
            />
            <StatCard
              id="stat-events"
              label="Pipeline events"
              value={fmt(summary?.total_pipeline_events ?? 0)}
              sub={`event err rate ${summary?.pipeline_error_rate_pct !== null ? `${summary!.pipeline_error_rate_pct}%` : '—'}`}
              accent={(summary?.pipeline_error_rate_pct ?? 0) > 10}
            />
          </div>
        )}
      </section>

      {/* Stage performance */}
      <section id="obs-stage-perf" className="mb-8">
        <h2 className="mb-3 font-display text-sm uppercase tracking-widest text-neutral-500">
          Stage performance
        </h2>
        <Card className="p-5">
          {stagesQ.isLoading ? (
            <div className="space-y-4">
              {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
            </div>
          ) : stagesQ.isError ? (
            <p className="font-mono text-sm text-brand-400">Unable to load stage data.</p>
          ) : stages.length === 0 ? (
            <p className="font-mono text-sm text-neutral-600">No stage data yet.</p>
          ) : (
            <div className="space-y-5">
              {stages.map((s) => <StageBar key={s.stage} stage={s} />)}
            </div>
          )}
        </Card>
      </section>

      {/* Bottom two-column grid */}
      <div className="grid gap-6 lg:grid-cols-3">

        {/* Execution history (2/3 width) */}
        <section id="obs-execution-history" className="lg:col-span-2">
          <h2 className="mb-3 font-display text-sm uppercase tracking-widest text-neutral-500">
            Execution history
          </h2>
          <Card className="overflow-hidden p-0">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b-2 border-neutral-800 bg-neutral-950">
                  <th className="px-3 py-2.5 font-mono text-[10px] uppercase tracking-widest text-neutral-600">ID</th>
                  <th className="px-3 py-2.5 font-mono text-[10px] uppercase tracking-widest text-neutral-600">Status</th>
                  <th className="px-3 py-2.5 font-mono text-[10px] uppercase tracking-widest text-neutral-600">Verdicts</th>
                  <th className="px-3 py-2.5 font-mono text-[10px] uppercase tracking-widest text-neutral-600">Duration</th>
                  <th className="px-3 py-2.5 font-mono text-[10px] uppercase tracking-widest text-neutral-600">When</th>
                </tr>
              </thead>
              <tbody>
                {execsQ.isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="border-b border-neutral-800/60">
                      <td colSpan={5} className="px-3 py-2">
                        <Skeleton className="h-5 w-full" />
                      </td>
                    </tr>
                  ))
                ) : execsQ.isError ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center font-mono text-sm text-brand-400">
                      Unable to load execution history.
                    </td>
                  </tr>
                ) : (execs?.items ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center font-mono text-sm text-neutral-700">
                      No executions in this window.
                    </td>
                  </tr>
                ) : (
                  (execs?.items ?? []).map((exec) => (
                    <ExecutionRow
                      key={exec.id}
                      exec={exec}
                      onNavigate={(id) => navigate(`/verify/${id}`)}
                    />
                  ))
                )}
              </tbody>
            </table>

            {/* Pagination */}
            {execs && execs.total > EXEC_LIMIT && (
              <div className="flex items-center justify-between border-t border-neutral-800 px-3 py-2">
                <span className="font-mono text-xs text-neutral-600">
                  {execOffset + 1}–{Math.min(execOffset + EXEC_LIMIT, execs.total)} of {execs.total}
                </span>
                <div className="flex gap-2">
                  <button
                    id="exec-prev"
                    disabled={execOffset === 0}
                    onClick={() => setExecOffset(Math.max(0, execOffset - EXEC_LIMIT))}
                    className="border border-neutral-700 px-2 py-0.5 font-mono text-xs text-neutral-400 hover:text-neutral-100 disabled:opacity-30"
                  >
                    ← prev
                  </button>
                  <button
                    id="exec-next"
                    disabled={execOffset + EXEC_LIMIT >= execs.total}
                    onClick={() => setExecOffset(execOffset + EXEC_LIMIT)}
                    className="border border-neutral-700 px-2 py-0.5 font-mono text-xs text-neutral-400 hover:text-neutral-100 disabled:opacity-30"
                  >
                    next →
                  </button>
                </div>
              </div>
            )}
          </Card>
        </section>

        {/* Recent errors (1/3 width) */}
        <section id="obs-recent-errors">
          <h2 className="mb-3 font-display text-sm uppercase tracking-widest text-neutral-500">
            Recent errors
          </h2>
          <Card className="p-0">
            {errorsQ.isLoading ? (
              <div className="space-y-2 p-4">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
              </div>
            ) : errorsQ.isError ? (
              <div className="p-6 text-center">
                <p className="font-mono text-xs text-brand-400">Unable to load recent errors.</p>
              </div>
            ) : errors.length === 0 ? (
              <div className="p-6 text-center">
                <span className="text-2xl">✓</span>
                <p className="mt-1 font-mono text-xs text-neutral-600">No errors in this window</p>
              </div>
            ) : (
              <ul id="obs-error-list" className="divide-y divide-neutral-800/60">
                {errors.map((err, i) => (
                  <li
                    key={i}
                    id={`error-item-${i}`}
                    className="px-3 py-2.5 transition hover:bg-neutral-900/40"
                  >
                    <div className="flex items-start justify-between gap-1">
                      <div>
                        <span className="font-mono text-[10px] uppercase tracking-wider text-brand-400">
                          {STAGE_LABELS[err.stage] ?? err.stage}
                        </span>
                        <p className="font-mono text-xs text-neutral-300">
                          {err.error_type ?? 'Unknown'}
                        </p>
                        {err.duration_ms !== null && (
                          <p className="font-mono text-[10px] text-neutral-700">
                            after {fmtMs(err.duration_ms)}
                          </p>
                        )}
                      </div>
                      <span className="shrink-0 font-mono text-[10px] text-neutral-700">
                        {relTime(err.recorded_at)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>
      </div>
    </div>
  )
}
