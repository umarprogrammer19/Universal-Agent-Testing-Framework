'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

// ─── Constants ───────────────────────────────────────────────────────────────

const AVAILABLE_MODELS = ['gemini', 'gpt-4', 'claude'] as const

// ─── Types ───────────────────────────────────────────────────────────────────

interface DraftTestCase {
  id: string
  prompt: string
  expected_tools: string
  max_steps: number
  golden_response: string
}

function emptyTestCase(): DraftTestCase {
  return {
    id: crypto.randomUUID(),
    prompt: '',
    expected_tools: '',
    max_steps: 5,
    golden_response: '',
  }
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="block text-slate-300 text-sm font-medium mb-1.5">{children}</label>
}

function inputCls(extra = '') {
  return `w-full bg-slate-800 border border-slate-700 text-white placeholder-slate-500 rounded-lg p-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors ${extra}`
}

function TestCaseCard({
  tc,
  index,
  onChange,
  onRemove,
}: {
  tc: DraftTestCase
  index: number
  onChange: (id: string, field: keyof DraftTestCase, value: string | number) => void
  onRemove: (id: string) => void
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 mb-4 relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-slate-400 text-xs font-medium uppercase tracking-wider">
          Test Case {index + 1}
        </span>
        <button
          onClick={() => onRemove(tc.id)}
          className="text-slate-500 hover:text-red-400 transition-colors text-lg leading-none px-1"
          aria-label="Remove test case"
        >
          ✕
        </button>
      </div>

      <div className="flex flex-col gap-4">
        {/* Prompt */}
        <div>
          <FieldLabel>Trigger Prompt</FieldLabel>
          <textarea
            rows={3}
            placeholder="What should the agent do?"
            value={tc.prompt}
            onChange={(e) => onChange(tc.id, 'prompt', e.target.value)}
            className={inputCls('resize-none')}
          />
        </div>

        {/* Expected tools */}
        <div>
          <FieldLabel>Expected Tool Sequence</FieldLabel>
          <input
            type="text"
            placeholder="search_db, format_response, send_email (comma separated)"
            value={tc.expected_tools}
            onChange={(e) => onChange(tc.id, 'expected_tools', e.target.value)}
            className={inputCls()}
          />
          <p className="text-slate-500 text-xs mt-1">Enter tool names in order, comma separated</p>
        </div>

        {/* Max steps */}
        <div>
          <FieldLabel>Max Steps</FieldLabel>
          <input
            type="number"
            min={1}
            max={20}
            value={tc.max_steps}
            onChange={(e) => onChange(tc.id, 'max_steps', parseInt(e.target.value, 10) || 1)}
            className={inputCls('w-28')}
          />
        </div>

        {/* Golden response */}
        <div>
          <FieldLabel>Golden Response <span className="text-slate-500 font-normal">(optional)</span></FieldLabel>
          <textarea
            rows={2}
            placeholder="The ideal response for semantic scoring…"
            value={tc.golden_response}
            onChange={(e) => onChange(tc.id, 'golden_response', e.target.value)}
            className={inputCls('resize-none')}
          />
        </div>
      </div>
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function BuilderPage() {
  const router = useRouter()

  const [suiteName, setSuiteName] = useState('')
  const [multiModelTest, setMultiModelTest] = useState(false)
  const [modelsToTest, setModelsToTest] = useState<string[]>(['gemini'])
  const [testCases, setTestCases] = useState<DraftTestCase[]>([emptyTestCase()])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // ── Model selection helpers ────────────────────────────────────────────────

  function handleModeSelect(multi: boolean) {
    setMultiModelTest(multi)
    setModelsToTest(multi ? [...AVAILABLE_MODELS] : ['gemini'])
  }

  function toggleModel(model: string) {
    setModelsToTest((prev) =>
      prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model]
    )
  }

  // ── Test case helpers ──────────────────────────────────────────────────────

  function addTestCase() {
    setTestCases((prev) => [...prev, emptyTestCase()])
  }

  function removeTestCase(id: string) {
    setTestCases((prev) => prev.filter((tc) => tc.id !== id))
  }

  function updateTestCase(id: string, field: keyof DraftTestCase, value: string | number) {
    setTestCases((prev) => prev.map((tc) => (tc.id === id ? { ...tc, [field]: value } : tc)))
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  async function handleSave() {
    setError('')

    // Validation
    if (!suiteName.trim()) {
      setError('Suite name is required.')
      return
    }
    if (testCases.length === 0) {
      setError('Add at least one test case.')
      return
    }
    for (let i = 0; i < testCases.length; i++) {
      const tc = testCases[i]
      if (!tc.prompt.trim()) {
        setError(`Test case ${i + 1}: prompt is required.`)
        return
      }
      if (!tc.expected_tools.trim()) {
        setError(`Test case ${i + 1}: expected tool sequence is required.`)
        return
      }
    }
    if (multiModelTest && modelsToTest.length === 0) {
      setError('Select at least one model for multi-model comparison.')
      return
    }

    setSaving(true)
    try {
      await api.createSuite({
        name: suiteName.trim(),
        multi_model_test: multiModelTest,
        models_to_test: modelsToTest,
        test_cases: testCases.map((tc) => ({
          prompt: tc.prompt.trim(),
          expected_tools: tc.expected_tools
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean),
          max_steps: tc.max_steps,
          golden_response: tc.golden_response.trim() || null,
        })),
      })
      router.push('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save suite.')
    } finally {
      setSaving(false)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Top bar */}
      <div className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push('/')}
            className="text-slate-400 hover:text-white transition-colors text-lg leading-none"
            aria-label="Back to dashboard"
          >
            ←
          </button>
          <h1 className="text-white font-semibold text-lg">New Test Suite</h1>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors"
        >
          {saving ? 'Saving…' : 'Save Suite'}
        </button>
      </div>

      {/* Form */}
      <main className="max-w-3xl mx-auto px-6 mt-8 pb-20">

        {/* Error */}
        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 mb-6 text-sm">
            {error}
          </div>
        )}

        {/* Section 1 — Suite Name */}
        <section>
          <h2 className="text-white font-semibold text-base mb-3">Suite Name</h2>
          <input
            type="text"
            placeholder="e.g. Invoice Agent Tests"
            value={suiteName}
            onChange={(e) => setSuiteName(e.target.value)}
            className={inputCls()}
          />
        </section>

        {/* Section 2 — Test Mode */}
        <section className="mt-6">
          <h2 className="text-white font-semibold text-base mb-3">Test Mode</h2>

          {/* Mode cards */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            {[
              { multi: false, label: 'Single Model', desc: 'Test with one model' },
              { multi: true, label: 'Multi-Model Comparison', desc: 'Test across all models' },
            ].map(({ multi, label, desc }) => (
              <button
                key={String(multi)}
                onClick={() => handleModeSelect(multi)}
                className={`text-left p-4 rounded-xl border transition-colors ${
                  multiModelTest === multi
                    ? 'border-blue-500 bg-blue-900/20'
                    : 'border-slate-700 bg-slate-900 hover:border-slate-600'
                }`}
              >
                <p className="text-white font-medium text-sm">{label}</p>
                <p className="text-slate-400 text-xs mt-0.5">{desc}</p>
              </button>
            ))}
          </div>

          {/* Model selector */}
          {!multiModelTest ? (
            <div>
              <FieldLabel>Model</FieldLabel>
              <select
                value={modelsToTest[0]}
                onChange={(e) => setModelsToTest([e.target.value])}
                className={inputCls('cursor-pointer')}
              >
                {AVAILABLE_MODELS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <FieldLabel>Models to test</FieldLabel>
              <div className="flex gap-3">
                {AVAILABLE_MODELS.map((m) => (
                  <label
                    key={m}
                    className="flex items-center gap-2 cursor-pointer select-none"
                  >
                    <input
                      type="checkbox"
                      checked={modelsToTest.includes(m)}
                      onChange={() => toggleModel(m)}
                      className="w-4 h-4 accent-blue-500"
                    />
                    <span className="text-slate-300 text-sm">{m}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Section 3 — Test Cases */}
        <section className="mt-8">
          <h2 className="text-white font-semibold text-base mb-4">Test Cases</h2>

          {testCases.map((tc, i) => (
            <TestCaseCard
              key={tc.id}
              tc={tc}
              index={i}
              onChange={updateTestCase}
              onRemove={removeTestCase}
            />
          ))}

          <button
            onClick={addTestCase}
            className="w-full border border-dashed border-slate-700 hover:border-slate-500 text-slate-400 hover:text-slate-300 rounded-xl py-4 text-sm transition-colors"
          >
            + Add Test Case
          </button>
        </section>
      </main>
    </div>
  )
}
