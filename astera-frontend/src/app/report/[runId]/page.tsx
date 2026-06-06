'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { ModelComparison, Run, TestResult, TraceStep } from '@/lib/types'

// ─── Types ───────────────────────────────────────────────────────────────────

type Tab = 'results' | 'comparison' | 'replay'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function scoreColor(score: number) {
  if (score >= 80) return 'text-emerald-400 bg-emerald-900/40 border-emerald-700/50'
  if (score >= 50) return 'text-amber-400 bg-amber-900/40 border-amber-700/50'
  return 'text-red-400 bg-red-900/40 border-red-700/50'
}

function scoreLabel(score: number) {
  if (score >= 80) return 'Excellent'
  if (score >= 50) return 'Good'
  return 'Poor'
}

function stepCircleCls(step: TraceStep) {
  if (step.is_divergence) return 'bg-red-600 border-red-500'
  if (step.expected_tool && step.tool === step.expected_tool) return 'bg-emerald-600 border-emerald-500'
  return 'bg-slate-600 border-slate-500'
}

// ─── Step Timeline ────────────────────────────────────────────────────────────

function StepTimeline({ trace }: { trace: TraceStep[] }) {
  if (!trace.length) return <p className="text-slate-500 text-xs italic">No steps recorded.</p>

  return (
    <div className="flex items-start gap-1 mt-3 overflow-x-auto pb-1">
      {trace.map((step, i) => (
        <div key={i} className="flex items-start">
          <div className="flex flex-col items-center gap-1">
            <div
              className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-bold text-white shrink-0 ${stepCircleCls(step)}`}
              title={step.is_divergence ? step.divergence_reason ?? 'Divergence' : step.tool}
            >
              {step.step + 1}
            </div>
            <span className="text-slate-400 text-xs max-w-16 truncate text-center">{step.tool}</span>
          </div>
          {i < trace.length - 1 && (
            <span className="text-slate-600 text-sm mt-2 mx-0.5 shrink-0">→</span>
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Result Card ─────────────────────────────────────────────────────────────

function ResultCard({ result, index }: { result: TestResult; index: number }) {
  const divergedStep = result.divergence_step
  const divergedTrace = divergedStep != null ? result.execution_trace[divergedStep - 1] : null
  const expectedAtDivergence = divergedStep != null ? result.expected_tools[divergedStep - 1] : null

  return (
    <div className={`bg-slate-900 border rounded-xl p-5 mb-4 ${result.passed ? 'border-slate-800' : 'border-red-900/50'}`}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <span className="text-slate-400 text-sm font-medium">Test {index + 1}</span>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${
          result.passed
            ? 'text-emerald-400 bg-emerald-900/40 border-emerald-700/50'
            : 'text-red-400 bg-red-900/40 border-red-700/50'
        }`}>
          {result.passed ? 'PASSED' : 'FAILED'}
        </span>
        <span className="text-xs bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded-full">
          {result.model_used}
        </span>
        <span className="text-slate-500 text-xs ml-auto">Tokens: {result.token_usage}</span>
      </div>

      {/* Prompt */}
      <p className="text-slate-300 text-sm mb-2 line-clamp-2">{result.prompt}</p>

      {/* Step timeline */}
      <StepTimeline trace={result.execution_trace} />

      {/* Divergence alert */}
      {divergedStep != null && (
        <div className="mt-3 bg-red-900/30 border border-red-800/60 rounded-lg px-3 py-2 text-xs text-red-300">
          Diverged at Step {divergedStep}
          {expectedAtDivergence && ` — Expected: ${expectedAtDivergence}`}
          {divergedTrace && `, Got: ${divergedTrace.tool}`}
        </div>
      )}

      {/* Semantic score */}
      {result.semantic_score != null && (
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${scoreColor(result.semantic_score)}`}>
            {result.semantic_score.toFixed(1)} — {scoreLabel(result.semantic_score)}
          </span>
          {result.judge_explanation && (
            <span className="text-slate-400 text-xs italic">{result.judge_explanation}</span>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Comparison Tab ───────────────────────────────────────────────────────────

function ComparisonTab({ comparison, runId, router }: { comparison: ModelComparison; runId: string; router: ReturnType<typeof useRouter> }) {
  const entries = Object.entries(comparison.models)

  if (entries.length <= 1) {
    return (
      <div className="flex flex-col items-center text-center gap-3 py-16">
        <span className="text-3xl">ℹ️</span>
        <p className="text-slate-300 font-medium">Single model run</p>
        <p className="text-slate-500 text-sm max-w-xs">
          Run with Multi-Model enabled to compare models side-by-side
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800">
            {['Model', 'Pass Rate', 'Total Tokens', 'Avg Score', 'Status', ''].map((h) => (
              <th key={h} className="text-left text-slate-400 text-xs font-medium uppercase tracking-wider pb-3 pr-4">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entries.map(([model, data]) => {
            const passNum = parseFloat(data.pass_rate)
            const passColor = passNum === 100 ? 'text-emerald-400' : passNum >= 50 ? 'text-amber-400' : 'text-red-400'
            return (
              <tr key={model} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                <td className="py-3 pr-4">
                  <span className="text-xs bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded-full">
                    {model}
                  </span>
                </td>
                <td className={`py-3 pr-4 font-bold ${passColor}`}>{data.pass_rate}</td>
                <td className="py-3 pr-4 text-slate-300">{data.total_tokens ?? '—'}</td>
                <td className="py-3 pr-4">
                  {data.avg_semantic_score != null ? (
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${scoreColor(data.avg_semantic_score)}`}>
                      {data.avg_semantic_score.toFixed(1)}
                    </span>
                  ) : (
                    <span className="text-slate-500">—</span>
                  )}
                </td>
                <td className="py-3 pr-4">
                  <span className={`text-xs font-medium ${data.status === 'completed' ? 'text-emerald-400' : data.status === 'failed' ? 'text-red-400' : 'text-amber-400'}`}>
                    {data.status?.toUpperCase() ?? '—'}
                  </span>
                </td>
                <td className="py-3">
                  <button
                    onClick={() => router.push(`/replay/${runId}?model=${model}`)}
                    className="text-xs text-blue-400 hover:text-blue-300 border border-blue-800 hover:border-blue-600 px-2 py-1 rounded transition-colors"
                  >
                    View Replay
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const router = useRouter()
  const { runId } = useParams<{ runId: string }>()

  const [report, setReport] = useState<Run | null>(null)
  const [comparison, setComparison] = useState<ModelComparison | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('results')

  useEffect(() => {
    Promise.all([api.getRunReport(runId), api.getRunCompare(runId)])
      .then(([r, c]) => {
        setReport(r)
        setComparison(c)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [runId])

  // ── Loading ──────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400 text-sm">Loading report…</p>
        </div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <p className="text-slate-400">Report not found.</p>
      </div>
    )
  }

  const allPassed = (report.fail_count ?? 0) === 0 && (report.pass_count ?? 0) > 0
  const results: TestResult[] = report.results ?? []

  const tabs: { id: Tab; label: string }[] = [
    { id: 'results', label: 'Test Results' },
    { id: 'comparison', label: 'Model Comparison' },
    { id: 'replay', label: 'Agent Replay' },
  ]

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Top bar */}
      <div className="border-b border-slate-800 px-6 py-4 flex items-center gap-3 flex-wrap">
        <button
          onClick={() => router.push('/')}
          className="text-slate-400 hover:text-white transition-colors text-lg leading-none shrink-0"
          aria-label="Back"
        >
          ←
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-white font-semibold text-lg leading-tight">Report Card</h1>
          <p className="text-slate-400 text-xs mt-0.5 truncate">
            {report.suite_name || report.suite_id}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs bg-amber-900/50 text-amber-300 border border-amber-700/40 px-2 py-1 rounded-full">
            {report.model_type}
          </span>
          <span className={`text-xs font-bold px-3 py-1 rounded-full border ${
            allPassed
              ? 'text-emerald-400 bg-emerald-900/40 border-emerald-700/50'
              : 'text-red-400 bg-red-900/40 border-red-700/50'
          }`}>
            {allPassed ? 'PASSED' : 'FAILED'}
          </span>
        </div>
      </div>

      <main className="max-w-4xl mx-auto px-6 pb-20">
        {/* Hero stats */}
        <div className="grid grid-cols-3 gap-4 mt-6">
          {[
            { label: 'Passed', value: report.pass_count ?? 0, color: 'text-emerald-400' },
            { label: 'Failed', value: report.fail_count ?? 0, color: 'text-red-400' },
            { label: 'Tokens', value: report.total_tokens ?? 0, color: 'text-blue-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-slate-900 border border-slate-800 rounded-xl p-5 text-center">
              <p className={`text-4xl font-bold ${color}`}>{value}</p>
              <p className="text-slate-400 text-sm mt-1">{label}</p>
            </div>
          ))}
        </div>

        {/* Tab navigation */}
        <div className="flex border-b border-slate-800 mt-8 gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === tab.id
                  ? 'border-blue-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="mt-6">

          {/* Tab 1 — Test Results */}
          {activeTab === 'results' && (
            <div>
              {results.length === 0 ? (
                <p className="text-slate-500 text-sm">No results yet.</p>
              ) : (
                results.map((result, i) => (
                  <ResultCard key={result.test_case_id} result={result} index={i} />
                ))
              )}
            </div>
          )}

          {/* Tab 2 — Model Comparison */}
          {activeTab === 'comparison' && comparison && (
            <ComparisonTab comparison={comparison} runId={runId} router={router} />
          )}

          {/* Tab 3 — Agent Replay */}
          {activeTab === 'replay' && (
            <div className="flex flex-col items-center text-center gap-6 py-12">
              <div className="w-20 h-20 rounded-full bg-purple-900/40 border border-purple-700/50 flex items-center justify-center text-4xl">
                ⏮
              </div>
              <div>
                <h2 className="text-white font-semibold text-xl mb-2">Agent Replay Mode</h2>
                <p className="text-slate-400 text-sm max-w-sm">
                  Step through every tool call the agent made, see exactly where it diverged from the expected sequence
                </p>
              </div>
              <button
                onClick={() => router.push(`/replay/${runId}`)}
                className="bg-purple-600 hover:bg-purple-500 text-white font-semibold px-8 py-3 rounded-xl text-base transition-colors"
              >
                Open Full Replay Mode
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
