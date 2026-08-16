// Typed API client for the DataOps Guardian control plane.

export interface Summary {
  quality_score: number;
  total_datasets: number;
  total_checks: number;
  passing_checks: number;
  failing_checks: number;
  open_incidents: number;
  last_run_at: string | null;
}

export interface Dataset {
  id: number;
  name: string;
  source_table: string;
  domain: string;
  owner: string;
  description: string;
  freshness_sla_minutes: number;
}

export interface CheckResult {
  id: number;
  check_id: number;
  dataset_id: number;
  status: "pass" | "fail" | "error";
  observed_value: number | null;
  rows_scanned: number;
  rows_failed: number;
  message: string;
  duration_ms: number;
  created_at: string;
}

export interface CheckDef {
  id: number;
  dataset_id: number;
  name: string;
  check_type: string;
  column_name: string | null;
  config: Record<string, unknown>;
  severity: string;
  enabled: boolean;
}

export interface Incident {
  id: number;
  dataset_id: number;
  check_id: number;
  title: string;
  severity: string;
  status: "open" | "acknowledged" | "resolved";
  details: string;
  first_seen: string;
  last_seen: string;
  resolved_at: string | null;
  occurrences: number;
}

export interface CheckRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  total_checks: number;
  passed: number;
  failed: number;
  errored: number;
  trigger: string;
}

export interface LineageEdge {
  upstream: string;
  downstream: string;
  transformation: string;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  summary: () => fetch("/api/summary").then(json<Summary>),
  datasets: () => fetch("/api/datasets").then(json<Dataset[]>),
  checks: () => fetch("/api/checks").then(json<CheckDef[]>),
  latestResults: () => fetch("/api/results/latest").then(json<CheckResult[]>),
  incidents: () => fetch("/api/incidents").then(json<Incident[]>),
  runs: () => fetch("/api/runs").then(json<CheckRun[]>),
  lineage: () => fetch("/api/lineage").then(json<LineageEdge[]>),
  triggerRun: () => fetch("/api/runs", { method: "POST" }).then(json<CheckRun>),
  updateIncident: (id: number, status: string) =>
    fetch(`/api/incidents/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }).then(json<Incident>),
};
