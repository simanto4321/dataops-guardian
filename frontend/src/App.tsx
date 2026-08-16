import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type CheckDef,
  type CheckResult,
  type Dataset,
  type Incident,
  type LineageEdge,
  type Summary,
} from "./api";

interface Bundle {
  summary: Summary;
  datasets: Dataset[];
  checks: CheckDef[];
  results: CheckResult[];
  incidents: Incident[];
  lineage: LineageEdge[];
}

function useDashboard() {
  const [data, setData] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [summary, datasets, checks, results, incidents, lineage] = await Promise.all([
        api.summary(),
        api.datasets(),
        api.checks(),
        api.latestResults(),
        api.incidents(),
        api.lineage(),
      ]);
      setData({ summary, datasets, checks, results, incidents, lineage });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runChecks = useCallback(async () => {
    setRunning(true);
    try {
      await api.triggerRun();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }, [load]);

  const setIncident = useCallback(
    async (id: number, status: string) => {
      await api.updateIncident(id, status);
      await load();
    },
    [load]
  );

  return { data, error, running, runChecks, setIncident, reload: load };
}

function ScoreRing({ score }: { score: number }) {
  const color = score >= 90 ? "var(--pass)" : score >= 70 ? "var(--warn)" : "var(--fail)";
  return (
    <div className="ring" style={{ ["--v" as string]: score, background: `conic-gradient(${color} calc(${score} * 1%), #22304d 0)` }}>
      <span>{score.toFixed(0)}</span>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function StatusPill({ status }: { status: CheckResult["status"] }) {
  return (
    <span className={`pill ${status}`}>
      <span className={`dot ${status}`} />
      {status}
    </span>
  );
}

export default function App() {
  const { data, error, running, runChecks, setIncident } = useDashboard();

  const checkById = useMemo(() => {
    const map = new Map<number, CheckDef>();
    data?.checks.forEach((c) => map.set(c.id, c));
    return map;
  }, [data]);

  const datasetById = useMemo(() => {
    const map = new Map<number, Dataset>();
    data?.datasets.forEach((d) => map.set(d.id, d));
    return map;
  }, [data]);

  if (error) {
    return (
      <div className="app">
        <div className="error-state">
          <p>Could not reach the API: {error}</p>
          <p className="muted">Start the backend with <code>uvicorn app.main:app --port 8000</code> and seed it first.</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="app">
        <div className="loading">
          <div className="spinner" />
          Loading control plane…
        </div>
      </div>
    );
  }

  const { summary, results, incidents, lineage, datasets } = data;
  const openIncidents = incidents.filter((i) => i.status !== "resolved");

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">
          <div className="logo">🛡️</div>
          <div>
            <h1>DataOps Guardian</h1>
            <p>Data quality &amp; governance control center</p>
          </div>
        </div>
        <button className="btn btn-primary" onClick={runChecks} disabled={running}>
          {running ? "Running checks…" : "▶ Run all checks"}
        </button>
      </div>

      <div className="grid kpis">
        <div className="card">
          <div className="score-wrap">
            <ScoreRing score={summary.quality_score} />
            <div>
              <div className="label muted">Overall quality score</div>
              <div className="sub">
                {summary.passing_checks} passing · {summary.failing_checks} failing
              </div>
              <div className="sub">
                Last run: {summary.last_run_at ? new Date(summary.last_run_at).toLocaleString() : "never"}
              </div>
            </div>
          </div>
        </div>
        <Kpi label="Datasets monitored" value={summary.total_datasets} sub="across 4 domains" />
        <Kpi label="Active checks" value={summary.total_checks} sub="7 check types" />
        <Kpi
          label="Open incidents"
          value={summary.open_incidents}
          sub={summary.open_incidents ? "needs triage" : "all clear"}
        />
      </div>

      <div className="grid columns">
        <div className="card">
          <h2>Latest check results</h2>
          {results.length === 0 ? (
            <p className="muted">No runs yet. Click “Run all checks”.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Dataset</th>
                  <th>Check</th>
                  <th>Detail</th>
                  <th>ms</th>
                </tr>
              </thead>
              <tbody>
                {[...results]
                  .sort((a, b) => (a.status === "pass" ? 1 : 0) - (b.status === "pass" ? 1 : 0))
                  .map((r) => {
                    const check = checkById.get(r.check_id);
                    const ds = datasetById.get(r.dataset_id);
                    return (
                      <tr key={r.id}>
                        <td><StatusPill status={r.status} /></td>
                        <td>{ds?.name ?? r.dataset_id}</td>
                        <td>
                          {check?.name ?? r.check_id}
                          {check && <span className={`sev ${check.severity}`} style={{ marginLeft: 8 }}>{check.severity}</span>}
                        </td>
                        <td className="mono muted">{r.message}</td>
                        <td className="mono">{r.duration_ms.toFixed(1)}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h2>Open incidents ({openIncidents.length})</h2>
          {openIncidents.length === 0 ? (
            <p className="muted">No open incidents. Data is healthy. 🎉</p>
          ) : (
            openIncidents.map((inc) => (
              <div className="incident" key={inc.id}>
                <div className="row">
                  <div className="title">{inc.title}</div>
                  <span className={`sev ${inc.severity}`}>{inc.severity}</span>
                </div>
                <div className="sub muted mono" style={{ margin: "6px 0" }}>{inc.details}</div>
                <div className="row">
                  <span className="tag">seen {inc.occurrences}×</span>
                  <div className="actions">
                    {inc.status !== "acknowledged" && (
                      <button className="mini-btn" onClick={() => setIncident(inc.id, "acknowledged")}>
                        Acknowledge
                      </button>
                    )}
                    <button className="mini-btn" onClick={() => setIncident(inc.id, "resolved")}>
                      Resolve
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="grid columns" style={{ marginTop: 18 }}>
        <div className="card">
          <h2>Dataset catalog</h2>
          <table>
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Domain</th>
                <th>Owner</th>
                <th>Freshness SLA</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((d) => (
                <tr key={d.id}>
                  <td>
                    {d.name}
                    <div className="sub muted">{d.description}</div>
                  </td>
                  <td><span className="tag">{d.domain}</span></td>
                  <td className="muted">{d.owner}</td>
                  <td className="mono">{d.freshness_sla_minutes} min</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2>Lineage</h2>
          <div className="lineage">
            {lineage.map((e, i) => (
              <div key={i} style={{ display: "flex", gap: 8, width: "100%", alignItems: "center" }}>
                <span className="node">{e.upstream}</span>
                <span className="edge">→ {e.transformation} →</span>
                <span className="node">{e.downstream}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="footer">
        DataOps Guardian · built by{" "}
        <a href="https://github.com/simanto4321" target="_blank" rel="noreferrer">
          Mehedi Ashraf Simanto
        </a>
      </div>
    </div>
  );
}
