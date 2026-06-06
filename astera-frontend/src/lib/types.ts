export interface TestCase {
  id?: string
  prompt: string
  expected_tools: string[]
  max_steps: number
  golden_response?: string
  order_index?: number
}

export interface TestSuite {
  id: string
  name: string
  multi_model_test: boolean
  models_to_test: string[]
  test_case_count: number
  last_run_status: string
  created_at: string
}

export interface TraceStep {
  step: number
  tool: string
  params: Record<string, unknown>
  response?: Record<string, unknown>
  tokens_this_step?: number
  expected_tool?: string
  is_divergence?: boolean
  divergence_reason?: string | null
}

export interface TestResult {
  test_case_id: string
  prompt: string
  passed: boolean
  execution_trace: TraceStep[]
  divergence_step?: number | null
  semantic_score?: number | null
  judge_explanation?: string | null
  token_usage: number
  actual_response: string
  expected_tools: string[]
  model_used: string
}

export interface Run {
  run_id: string
  suite_id: string
  suite_name: string
  model_type: string
  status: string
  pass_count: number
  fail_count: number
  total_tokens: number
  started_at: string
  completed_at?: string
  results?: TestResult[]
}

export interface RunStatus {
  run_id: string
  status: string
  model_type: string
  pass_count: number
  fail_count: number
  total_tokens: number
  trace_logs: { test_case_id: string; passed: boolean; steps: number }[]
  started_at: string
}

export interface ModelComparison {
  suite_id: string
  models: Record<string, {
    run_id?: string
    pass_count: number
    fail_count: number
    pass_rate: string
    total_tokens: number
    avg_semantic_score: number | null
    status?: string
  }>
}
