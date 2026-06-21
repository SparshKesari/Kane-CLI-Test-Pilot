export const API = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";
export const WS = API.replace(/^http/, "ws");

export type PhaseState = "pending" | "running" | "done" | "skipped" | "failed";

export interface Phase {
  key: string; name: string; state: PhaseState; detail: string;
  started_at: number | null; ended_at: number | null;
}
export interface ExistingTest { file: string; name: string; framework: string; target: string; }
export interface TestArtifact {
  scenario_id: string; title: string; framework: string; code: string;
  status: string; authentic: boolean; repair_iterations: number;
  kane_session: string; reason: string;
  kane_test_url?: string;   // LambdaTest session URL (cloud-grid runs only)
}
export interface Metrics {
  note?: string;
  summary?: Record<string, number>;
  surface_coverage?: { elements_found: number; elements_exercised: number; pct: number; uncovered: string[] };
  feature_coverage?: { feature: string; proposed: number; verified: number }[];
  criticality?: Record<string, { proposed: number; verified: number }>;
  total_duration_s?: number;
}
export interface Candidate {
  id: string; title: string; objective?: string; expected?: string;
  feature?: string; criticality?: string; scenario_type?: string; rationale?: string;
}
export interface Run {
  id: string; repo_url: string; target_url: string; status: string;
  verdict: string; error?: string; fork_url: string; branch: string; pr_url: string;
  mode?: string; awaiting_selection?: boolean; candidates?: Candidate[];
  created_at: number; phases: Phase[]; existing_tests: ExistingTest[]; tests: TestArtifact[];
  metrics?: Metrics;
}
export interface Ev {
  type: string; ts: number;
  // loop
  scenario?: string; iteration?: number; step?: string; status?: string;
  detail?: string; code?: string; error?: string; kane_session?: string; steps?: string[];
  // phase
  key?: string; state?: PhaseState; name?: string;
  // run
  verdict?: string; pr_url?: string; message?: string;
  existing?: ExistingTest[]; generated?: TestArtifact[]; phase?: string;
}

export async function listRuns(): Promise<Run[]> {
  return (await fetch(`${API}/api/runs`, { cache: "no-store" })).json();
}
export async function getRun(id: string): Promise<Run> {
  return (await fetch(`${API}/api/runs/${id}`, { cache: "no-store" })).json();
}
export async function createRun(
  repo_url: string, target_url: string, max_scenarios: number, mode: string = "auto",
): Promise<Run> {
  return (await fetch(`${API}/api/runs`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url, target_url, max_scenarios, mode }),
  })).json();
}

export async function selectScenarios(runId: string, scenario_ids: string[]) {
  return (await fetch(`${API}/api/runs/${runId}/select`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario_ids }),
  })).json();
}

export async function abortScenario(runId: string, scenario_id: string) {
  return (await fetch(`${API}/api/runs/${runId}/abort`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario_id }),
  })).json();
}

export async function abortRun(runId: string) {
  return (await fetch(`${API}/api/runs/${runId}/abort_run`, { method: "POST" })).json();
}

export async function abortAllRuns() {
  return (await fetch(`${API}/api/runs/abort_all`, { method: "POST" })).json();
}
