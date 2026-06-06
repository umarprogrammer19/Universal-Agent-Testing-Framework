'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { RunStatus } from '@/lib/types'

// ─── Page ────────────────────────────────────────────────────────────────────

export default function ExecutionRunnerPage() {
  const router = useRouter()
  const { suiteId } = useParams<{ suiteId: string }>()

  const [runIds, setRunIds] = useState<string[]>([])
  const [currentRunId, setCurrentRunId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [error, setError] = useState('')

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logBoxRef = useRef<HTMLDivElement>(null)

  // Auto-scroll log box whenever logs change
  useEffect(() => {
    const el = logBoxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logs])

  // Polling — starts when currentRunId + isRunning are both set
  useEffect(() => {
    if (!currentRunId || !isRunning) return

    function appendLog(line: string) {
      setLogs((prev) => [...prev, line])
    }

    intervalRef.current = setInterval(async () => {
      try {
        const status = await api.getRunStatus(currentRunId)
        setRunStatus(status)

        appendLog(
          `[${new Date().toLocaleTimeString()}] › Steps completed: ${status.trace_logs.length} — status: ${status.status}`
        )

        if (status.status === 'completed' || status.status === 'failed') {
          if (intervalRef.current) clearInterval(intervalRef.current)
          setIsRunning(false)

          if (status.status === 'completed') {
            appendLog(`[${new Date().toLocaleTimeString()}] › Run completed. Navigating to report…`)
            setTimeout(() => router.push(`/report/${currentRunId}`), 1000)
          } else {
            appendLog(`[${new Date().toLocaleTimeString()}] › Run failed.`)
          }
        }
      } catch (err) {
        if (intervalRef.current) clearInterval(intervalRef.current)
        setIsRunning(false)
        setError(err instanceof Error ? err.message : 'Polling error.')
      }
    }, 1000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [currentRunId, isRunning, router])

  // ── Start handler ──────────────────────────────────────────────────────────

  async function handleStart() {
    setError('')
    setLogs([])
    setRunStatus(null)
    try {
      const { run_ids } = await api.startRun(suiteId, ['gemini'])
      setRunIds(run_ids)
      setCurrentRunId(run_ids[0])
      setIsRunning(true)
      setLogs([`[${new Date().toLocaleTimeString()}] › Run started (id: ${run_ids[0]})`])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run.')
    }
  }

  // ── Reset ──────────────────────────────────────────────────────────────────

  function handleReset() {
    if (intervalRef.current) clearInterval(intervalRef.current)
    setRunIds([])
    setCurrentRunId(null)
    setRunStatus(null)
    setIsRunning(false)
    setLogs([])
    setError('')
  }

  // ── Derived state ──────────────────────────────────────────────────────────

  const hasStarted = runIds.length > 0
  const status = runStatus?.status ?? null

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Top bar */}
      <div className="border-b border-slate-800 px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => router.push('/')}
          className="text-slate-400 hover:text-white transition-colors text-lg leading-none"
          aria-label="Back"
        >
          ←
        </button>
        <div className="flex-1">
          <h1 className="text-white font-semibold text-lg leading-tight">Test Execution</h1>
          <p className="text-slate-400 text-xs mt-0.5 font-mono">suite: {suiteId}</p>
        </div>
      </div>

      <main className="max-w-2xl mx-auto px-6 mt-12 pb-20">
        {/* Error */}
        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 mb-6 text-sm">
            {error}
          </div>
        )}

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">

          {/* ── Not started ─────────────────────────────────────────────── */}
          {!hasStarted && (
            <div className="flex flex-col items-center text-center gap-6 py-6">
              <div className="w-16 h-16 rounded-full bg-blue-900/40 border border-blue-700/50 flex items-center justify-center text-3xl">
                ▶
              </div>
              <div>
                <h2 className="text-white font-semibold text-xl mb-2">Ready to Run</h2>
                <p className="text-slate-400 text-sm max-w-xs">
                  Click Start to begin executing the test suite against the agent
                </p>
              </div>
              <button
                onClick={handleStart}
                className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-8 py-3 rounded-xl text-base transition-colors"
              >
                Start Run
              </button>
            </div>
          )}

          {/* ── Running / completed ─────────────────────────────────────── */}
          {hasStarted && (
            <div className="flex flex-col gap-6">

              {/* Status indicator */}
              <div className="flex items-center gap-3">
                {isRunning && (
                  <>
                    <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
                    <span className="text-amber-400 font-medium">Running…</span>
                  </>
                )}
                {!isRunning && status === 'completed' && (
                  <>
                    <span className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center text-xs font-bold">✓</span>
                    <span className="text-emerald-400 font-medium">Completed</span>
                  </>
                )}
                {!isRunning && status === 'failed' && (
                  <>
                    <span className="w-5 h-5 rounded-full bg-red-500 flex items-center justify-center text-xs font-bold">✕</span>
                    <span className="text-red-400 font-medium">Failed</span>
                  </>
                )}
              </div>

              {/* Stats row */}
              {runStatus && (
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-slate-800 rounded-lg p-3 text-center">
                    <p className="text-emerald-400 text-xl font-bold">{runStatus.pass_count ?? 0}</p>
                    <p className="text-slate-400 text-xs mt-0.5">Tests Passed</p>
                  </div>
                  <div className="bg-slate-800 rounded-lg p-3 text-center">
                    <p className="text-red-400 text-xl font-bold">{runStatus.fail_count ?? 0}</p>
                    <p className="text-slate-400 text-xs mt-0.5">Tests Failed</p>
                  </div>
                  <div className="bg-slate-800 rounded-lg p-3 text-center">
                    <p className="text-blue-400 text-xl font-bold">{runStatus.total_tokens ?? 0}</p>
                    <p className="text-slate-400 text-xs mt-0.5">Tokens Used</p>
                  </div>
                </div>
              )}

              {/* Live log terminal */}
              <div>
                <p className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">
                  Live Log
                </p>
                <div
                  ref={logBoxRef}
                  className="bg-black border border-slate-700 rounded-lg p-4 h-64 overflow-y-auto font-mono text-sm"
                >
                  {logs.length === 0 && isRunning && (
                    <span className="text-slate-500 animate-pulse">
                      Waiting for agent response…
                    </span>
                  )}
                  {logs.map((line, i) => (
                    <div key={i} className="text-green-400 leading-6">
                      › {line}
                    </div>
                  ))}
                </div>
              </div>

              {/* Bottom actions */}
              {!isRunning && status === 'completed' && currentRunId && (
                <button
                  onClick={() => router.push(`/report/${currentRunId}`)}
                  className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-3 rounded-xl transition-colors"
                >
                  View Full Report →
                </button>
              )}
              {!isRunning && status === 'failed' && (
                <button
                  onClick={handleReset}
                  className="w-full bg-red-700 hover:bg-red-600 text-white font-semibold py-3 rounded-xl transition-colors"
                >
                  Try Again
                </button>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
