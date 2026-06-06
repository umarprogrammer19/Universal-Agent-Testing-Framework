'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { Run, TestSuite } from '@/lib/types'

// ─── Helpers ────────────────────────────────────────────────────────────────

function passRate(runs: Run[]): string {
  const total = runs.reduce((s, r) => s + (r.pass_count ?? 0) + (r.fail_count ?? 0), 0)
  const passed = runs.reduce((s, r) => s + (r.pass_count ?? 0), 0)
  if (total === 0) return '—'
  return `${Math.round((passed / total) * 100)}%`
}

function statusColor(status: string) {
  if (status === 'completed') return 'text-emerald-400'
  if (status === 'failed') return 'text-red-400'
  return 'text-amber-400'
}

function statusLabel(status: string) {
  if (status === 'completed') return 'PASSED'
  if (status === 'failed') return 'FAILED'
  return 'RUNNING'
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-4">
      <p className="text-slate-400 text-sm mb-1">{label}</p>
      <p className="text-white text-2xl font-bold">{value}</p>
    </div>
  )
}

function ModelBadge({ model }: { model: string }) {
  return (
    <span className="text-xs bg-blue-900/60 text-blue-300 border border-blue-700/50 px-2 py-0.5 rounded-full">
      {model}
    </span>
  )
}

function SuiteCard({
  suite,
  onRun,
  onDelete,
}: {
  suite: TestSuite
  onRun: (suite: TestSuite) => void
  onDelete: (id: string) => void
}) {
  const runPassed = suite.last_run_status.includes('passed')
  const neverRun = suite.last_run_status === 'never_run'

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
      <p className="font-bold text-white text-base">{suite.name}</p>

      <div className="flex flex-wrap gap-1.5 items-center">
        {suite.models_to_test.map((m) => (
          <ModelBadge key={m} model={m} />
        ))}
        {suite.multi_model_test && (
          <span className="text-xs bg-purple-900/60 text-purple-300 border border-purple-700/50 px-2 py-0.5 rounded-full">
            Multi-Model
          </span>
        )}
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-400">{suite.test_case_count} test cases</span>
        <span className="flex items-center gap-1.5 text-slate-400">
          <span
            className={`w-2 h-2 rounded-full ${
              neverRun ? 'bg-slate-600' : runPassed ? 'bg-emerald-500' : 'bg-red-500'
            }`}
          />
          {neverRun ? 'Never run' : suite.last_run_status}
        </span>
      </div>

      <div className="flex gap-2 mt-1">
        <button
          onClick={() => onRun(suite)}
          className="flex-1 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
        >
          Run
        </button>
        <button
          onClick={() => onDelete(suite.id)}
          className="flex-1 border border-red-800 hover:bg-red-900/40 text-red-400 text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
        >
          Delete
        </button>
      </div>
    </div>
  )
}

function RunItem({ run, onClick }: { run: Run; onClick: () => void }) {
  const total = (run.pass_count ?? 0) + (run.fail_count ?? 0)
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-slate-900 border border-slate-800 rounded-lg p-3 mb-2 hover:border-slate-600 transition-colors"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="font-semibold text-white text-sm truncate max-w-[140px]">
          {run.suite_name}
        </span>
        <span className={`text-xs font-bold ${statusColor(run.status)}`}>
          {statusLabel(run.status)}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs bg-amber-900/50 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded-full">
          {run.model_type}
        </span>
        <span className="text-slate-400 text-xs">{run.pass_count ?? 0}/{total} passed</span>
      </div>
    </button>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter()
  const [suites, setSuites] = useState<TestSuite[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.getSuites(), api.getRecentRuns(8)])
      .then(([s, r]) => {
        setSuites(s)
        setRuns(r)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  async function handleRunSuite(suite: TestSuite) {
    try {
      const { run_ids } = await api.startRun(suite.id, suite.models_to_test)
      router.push(`/run/${run_ids[0]}`)
    } catch (err) {
      console.error(err)
      alert('Failed to start run. Check the console for details.')
    }
  }

  async function handleDeleteSuite(suiteId: string) {
    if (!confirm('Delete this suite and all its runs?')) return
    try {
      await api.deleteSuite(suiteId)
      setSuites((prev) => prev.filter((s) => s.id !== suiteId))
    } catch (err) {
      console.error(err)
      alert('Failed to delete suite.')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400 text-sm">Loading dashboard…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Navbar */}
      <nav className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <span className="text-blue-400 font-bold text-xl tracking-tight">UATF</span>
        <button
          onClick={() => router.push('/builder')}
          className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Test Suite
        </button>
      </nav>

      <main className="max-w-7xl mx-auto px-6 pb-16">
        {/* Stats bar */}
        <div className="flex gap-4 mt-8">
          <StatCard label="Total Suites" value={suites.length} />
          <StatCard label="Recent Runs" value={runs.length} />
          <StatCard label="Pass Rate" value={passRate(runs)} />
        </div>

        {/* Main grid */}
        <div className="flex gap-6 mt-8 items-start">
          {/* Left — Test Suites */}
          <div className="flex-1 min-w-0">
            <h2 className="text-white font-semibold text-lg mb-4">Test Suites</h2>

            {suites.length === 0 ? (
              <div className="bg-slate-900 border border-dashed border-slate-700 rounded-xl p-12 text-center">
                <p className="text-slate-400 mb-4">
                  No test suites yet. Create your first one!
                </p>
                <button
                  onClick={() => router.push('/builder')}
                  className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                >
                  Create Test Suite
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {suites.map((suite) => (
                  <SuiteCard
                    key={suite.id}
                    suite={suite}
                    onRun={handleRunSuite}
                    onDelete={handleDeleteSuite}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Right — Recent Runs */}
          <div className="w-80 shrink-0">
            <h2 className="text-white font-semibold text-lg mb-4">Recent Runs</h2>
            {runs.length === 0 ? (
              <p className="text-slate-500 text-sm">No runs yet.</p>
            ) : (
              runs.map((run) => (
                <RunItem
                  key={run.run_id}
                  run={run}
                  onClick={() => router.push(`/report/${run.run_id}`)}
                />
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
