'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'

// ─── Types ───────────────────────────────────────────────────────────────────

interface TraceStep {
  step: number
  tool: string
  params: Record<string, unknown>
  response?: Record<string, unknown>
  tokens_this_step?: number
  expected_tool?: string
  is_divergence?: boolean
  divergence_reason?: string | null
}

interface TestCaseReplay {
  test_case_id: string
  execution_trace: TraceStep[]
  divergence_step: number | null
  is_divergence: boolean
}

interface ReplayData {
  run_id: string
  model_used: string
  suite_name: string
  execution_trace_replay: TestCaseReplay[]
  pass_count: number
  fail_count: number
  total_tokens: number
  status: string
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function ReplayPage() {
  const router = useRouter()
  const { runId } = useParams<{ runId: string }>()

  const [replayData, setReplayData] = useState<ReplayData | null>(null)
  const [selectedTestCase, setSelectedTestCase] = useState(0)
  const [selectedStep, setSelectedStep] = useState(0)
  const [loading, setLoading] = useState(true)

  // ── Fetch ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    api.getRunReplay(runId)
      .then((data) => setReplayData(data as ReplayData))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [runId])

  // ── Keyboard nav ───────────────────────────────────────────────────────────

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'ArrowRight') {
        setSelectedStep((prev) => Math.min(prev + 1, (currentTrace.length || 1) - 1))
      } else if (e.key === 'ArrowLeft') {
        setSelectedStep((prev) => Math.max(prev - 1, 0))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // ── Derived ────────────────────────────────────────────────────────────────

  const currentTestCase = replayData?.execution_trace_replay?.[selectedTestCase] ?? null
  const currentTrace: TraceStep[] = currentTestCase?.execution_trace ?? []
  const currentStep: TraceStep | null = currentTrace[selectedStep] ?? null

  const toolMatched =
    currentStep != null &&
    currentStep.expected_tool != null &&
    currentStep.tool === currentStep.expected_tool

  // ── Loading ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400 text-sm font-mono">Loading replay…</p>
        </div>
      </div>
    )
  }

  if (!replayData) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <p className="text-slate-400 font-mono">Replay data not found.</p>
      </div>
    )
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="h-screen bg-slate-950 text-white flex flex-col overflow-hidden">

      {/* ── Top bar ── */}
      <div className="h-14 bg-slate-900 border-b border-slate-700 px-4 flex items-center gap-3 shrink-0">
        {/* Decorative traffic lights */}
        <div className="flex items-center gap-1.5 mr-2">
          <span className="w-3 h-3 rounded-full bg-red-500" />
          <span className="w-3 h-3 rounded-full bg-yellow-500" />
          <span className="w-3 h-3 rounded-full bg-green-500" />
        </div>

        <button
          onClick={() => router.push('/')}
          className="text-slate-400 hover:text-white transition-colors text-base leading-none mr-1"
          aria-label="Back"
        >
          ←
        </button>

        <span className="font-mono font-semibold text-white tracking-tight">
          Agent Replay Mode
        </span>

        <div className="flex items-center gap-2 ml-auto">
          <span className="text-slate-500 font-mono text-xs hidden sm:block truncate max-w-48">
            {replayData.suite_name}
          </span>
          <span className="text-xs bg-amber-900/50 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded-full font-mono">
            {replayData.model_used}
          </span>
        </div>
      </div>

      {/* ── Four-column body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Column 1: Test cases sidebar ── */}
        <div className="w-48 bg-slate-900 border-r border-slate-800 overflow-y-auto shrink-0">
          <p className="text-xs text-slate-500 uppercase tracking-wider p-3 pb-2 font-mono border-b border-slate-800">
            Test Cases
          </p>
          {replayData.execution_trace_replay.map((tc, i) => (
            <div
              key={tc.test_case_id}
              onClick={() => { setSelectedTestCase(i); setSelectedStep(0) }}
              className={`p-3 cursor-pointer border-l-2 transition-colors ${
                selectedTestCase === i
                  ? 'border-blue-500 bg-slate-700'
                  : 'border-transparent hover:bg-slate-800'
              }`}
            >
              <p className="text-xs text-blue-400 font-mono font-medium">Case {i + 1}</p>
              <p className="text-xs text-slate-400 mt-0.5">
                {tc.execution_trace.length} steps
              </p>
              {tc.is_divergence && (
                <span className="inline-block mt-1 text-xs text-red-400 bg-red-950/50 border border-red-800/50 px-1.5 py-0.5 rounded">
                  ⚠ Diverged
                </span>
              )}
            </div>
          ))}
        </div>

        {/* ── Column 2: Timeline ── */}
        <div className="w-52 bg-slate-950 border-r border-slate-800 overflow-y-auto shrink-0">
          <p className="text-xs text-slate-500 uppercase tracking-wider p-3 pb-2 font-mono border-b border-slate-800">
            Execution Timeline
          </p>
          {currentTrace.length === 0 && (
            <p className="text-slate-600 text-xs p-3 font-mono">No steps.</p>
          )}
          {currentTrace.map((step, i) => (
            <div
              key={i}
              onClick={() => setSelectedStep(i)}
              className={`p-3 cursor-pointer border-l-4 transition-colors ${
                i === selectedStep
                  ? 'border-blue-500 bg-slate-800'
                  : step.is_divergence
                  ? 'border-red-500 bg-red-950/30 hover:bg-red-950/50'
                  : 'border-transparent hover:bg-slate-900'
              }`}
            >
              <p className="font-mono text-xs text-blue-400">Step {step.step + 1}</p>
              <p className="font-bold text-white text-sm mt-0.5 truncate">{step.tool}</p>
              <div className="flex items-center justify-between mt-1">
                {step.is_divergence ? (
                  <span className="text-red-400 text-xs">⚠ DIVERGED</span>
                ) : (
                  <span className="text-green-400 text-xs">✓ OK</span>
                )}
                {step.tokens_this_step != null && (
                  <span className="text-amber-400 text-xs font-mono">{step.tokens_this_step}t</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* ── Column 3: Step details ── */}
        <div className="flex-1 p-6 overflow-y-auto min-w-0">
          {!currentStep ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-slate-600 font-mono text-sm">Select a step from the timeline</p>
            </div>
          ) : (
            <div>
              {/* Tool name */}
              <div className="flex items-center gap-3 mb-6">
                <h1 className="text-2xl font-bold text-white font-mono break-all">
                  {currentStep.tool}
                </h1>
                <span className="text-xs bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded-full shrink-0">
                  {replayData.model_used}
                </span>
              </div>

              {/* Parameters */}
              <div>
                <p className="text-xs text-amber-400 font-mono uppercase tracking-wider mb-2">
                  Parameters
                </p>
                <pre className="bg-slate-900 border border-slate-700 rounded-lg p-4 font-mono text-sm text-slate-300 overflow-x-auto whitespace-pre-wrap break-words">
                  {JSON.stringify(currentStep.params, null, 2)}
                </pre>
              </div>

              {/* Response */}
              <div className="mt-4">
                <p className="text-xs text-green-400 font-mono uppercase tracking-wider mb-2">
                  Response
                </p>
                <pre className="bg-slate-900 border border-slate-700 rounded-lg p-4 font-mono text-sm text-slate-300 overflow-x-auto whitespace-pre-wrap break-words">
                  {JSON.stringify(currentStep.response ?? {}, null, 2)}
                </pre>
              </div>

              {/* Keyboard hint */}
              <p className="text-slate-600 text-xs font-mono mt-6">
                ← → arrow keys to navigate steps
              </p>
            </div>
          )}
        </div>

        {/* ── Column 4: Analysis panel ── */}
        <div className="w-72 bg-slate-900 border-l border-slate-800 p-5 overflow-y-auto shrink-0">
          <p className="text-xs text-slate-500 uppercase tracking-wider font-mono mb-4">
            Analysis
          </p>

          {!currentStep ? (
            <p className="text-slate-600 text-xs font-mono">No step selected</p>
          ) : (
            <>
              {/* Expected tool */}
              <div className="mb-4">
                <p className="text-xs text-blue-400 font-mono uppercase tracking-wider mb-1">
                  Expected Tool
                </p>
                <p className="font-bold text-white text-lg font-mono break-all">
                  {currentStep.expected_tool ?? '—'}
                </p>
              </div>

              <div className="border-t border-slate-800 pt-4 mb-4">
                <p className={`text-xs font-mono uppercase tracking-wider mb-1 ${
                  currentStep.is_divergence ? 'text-red-400' : 'text-green-400'
                }`}>
                  Actual Tool
                </p>
                <p className={`font-bold text-lg font-mono break-all ${
                  currentStep.is_divergence
                    ? 'text-red-300'
                    : toolMatched
                    ? 'text-emerald-300'
                    : 'text-white'
                }`}>
                  {currentStep.tool}
                </p>
              </div>

              {/* Divergence alert */}
              {currentStep.is_divergence && (
                <div className="bg-red-950 border border-red-700 rounded-lg p-4 mb-4">
                  <p className="text-red-300 font-bold text-sm mb-1">⚠ Divergence Detected</p>
                  <p className="text-red-200 text-sm leading-relaxed">
                    {currentStep.divergence_reason ?? 'Tool call did not match expected sequence.'}
                  </p>
                </div>
              )}

              {/* Tokens */}
              <div className="border-t border-slate-800 pt-4 mb-4">
                <p className="text-xs text-amber-400 font-mono uppercase tracking-wider mb-1">
                  Tokens This Step
                </p>
                <p className="font-mono text-amber-300 text-2xl">
                  {currentStep.tokens_this_step ?? '—'}
                </p>
              </div>

              {/* Step counter */}
              <p className="text-slate-400 text-sm font-mono border-t border-slate-800 pt-4">
                Step {(currentStep.step ?? selectedStep) + 1} of {currentTrace.length}
              </p>
            </>
          )}
        </div>

      </div>
    </div>
  )
}
