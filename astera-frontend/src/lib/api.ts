import type { ModelComparison, Run, RunStatus, TestSuite } from './types'

const BASE = process.env.NEXT_PUBLIC_API_URL

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${init?.method ?? 'GET'} ${path} → ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

export const api = {
  getSuites(): Promise<TestSuite[]> {
    return request('/api/suites')
  },

  createSuite(data: {
    name: string
    multi_model_test: boolean
    models_to_test: string[]
    test_cases: unknown[]
  }): Promise<TestSuite> {
    return request('/api/suites', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(data),
    })
  },

  getSuite(id: string): Promise<TestSuite> {
    return request(`/api/suites/${id}`)
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  deleteSuite(id: string): Promise<any> {
    return request(`/api/suites/${id}`, { method: 'DELETE' })
  },

  startRun(
    suiteId: string,
    modelsToTest: string[],
  ): Promise<{ run_ids: string[]; status: string }> {
    return request('/api/runs', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({
        suite_id: suiteId,
        models_to_test: modelsToTest,
        multi_model_test: modelsToTest.length > 1,
      }),
    })
  },

  getRunStatus(runId: string): Promise<RunStatus> {
    return request(`/api/runs/${runId}/status`)
  },

  getRunReport(runId: string): Promise<Run> {
    return request(`/api/runs/${runId}/report`)
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getRunReplay(runId: string): Promise<any> {
    return request(`/api/runs/${runId}/replay`)
  },

  getRunCompare(runId: string): Promise<ModelComparison> {
    return request(`/api/runs/${runId}/compare`)
  },

  getRecentRuns(limit?: number): Promise<Run[]> {
    return request(`/api/runs?limit=${limit ?? 10}`)
  },
}
