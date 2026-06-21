"use client";
import { useEffect, useRef, useState } from "react";
import { Ev, Phase, Run, WS, getRun, selectScenarios, abortRun } from "@/lib/api";
import { PhaseTimeline } from "@/components/PhaseTimeline";
import { LoopStream } from "@/components/LoopStream";
import { MetricsPanel } from "@/components/MetricsPanel";
import { StatusPanel } from "@/components/StatusPanel";
import { ScenarioChecklist } from "@/components/ScenarioChecklist";
import { Badge } from "@/components/Badge";
import { saveRun, loadRun } from "@/lib/store";

export default function RunPage({ params }: { params: { id: string } }) {
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [phases, setPhases] = useState<Phase[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [aborting, setAborting] = useState(false);
  const [fromLocal, setFromLocal] = useState(false);

  async function abortThisRun() {
    if (!run || !confirm("Abort this run? It will stop and no PR will be opened.")) return;
    setAborting(true);
    try { await abortRun(run.id); } finally { setAborting(false); }
  }
  const initSel = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);

  // When the run pauses for selection, pre-check every candidate (once).
  useEffect(() => {
    if (run?.awaiting_selection && run.candidates?.length && !initSel.current) {
      setPicked(new Set(run.candidates.map((c) => c.id)));
      initSel.current = true;
    }
    if (!run?.awaiting_selection) initSel.current = false;
  }, [run?.awaiting_selection, run?.candidates]);

  async function submitSelection() {
    if (!run) return;
    setSubmitting(true);
    try {
      await selectScenarios(run.id, [...picked]);
      setRun({ ...run, awaiting_selection: false });
    } finally { setSubmitting(false); }
  }

  useEffect(() => {
    // Apply a server fetch; if the server has forgotten the run (restarted),
    // fall back to the locally-saved snapshot so results never vanish.
    const apply = (r: Run, initial = false) => {
      if (r && r.repo_url) {
        setRun(r); setFromLocal(false); saveRun(r);
        if (initial) setPhases(r.phases);
      } else {
        const local = loadRun(params.id);
        if (local) { setRun(local); setPhases(local.phases); setFromLocal(true); }
        else if (initial) setRun(r);     // genuine not-found
      }
    };
    getRun(params.id).then((r) => apply(r, true))
      .catch(() => { const l = loadRun(params.id); if (l) { setRun(l); setPhases(l.phases); setFromLocal(true); } });

    const ws = new WebSocket(`${WS}/api/runs/${params.id}/events`);
    ws.onmessage = (m) => {
      const ev: Ev = JSON.parse(m.data);
      setEvents((prev) => [...prev, ev]);
      if (ev.type === "phase") {
        setPhases((prev) => prev.map((p) =>
          p.key === ev.key ? { ...p, state: ev.state!, detail: ev.detail ?? p.detail } : p));
      }
      if (ev.type === "run" || ev.type === "tests" || ev.type === "metrics" ||
          ev.type === "awaiting_selection")
        getRun(params.id).then((r) => apply(r));
    };
    return () => ws.close();
  }, [params.id]);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [events]);

  if (!run) return <p className="text-muted">Loading…</p>;
  if (!run.repo_url)
    return (
      <div className="card p-8 text-center">
        <p className="font-serif text-lg">Run not found</p>
        <p className="text-sm text-muted mt-1">
          It may have expired (the server keeps runs in memory and was restarted).
        </p>
        <a href="/" className="btn-primary mt-4">← Start a new run</a>
      </div>
    );
  const generated = run.tests ?? [];

  return (
    <div className="space-y-8">
      <div className="flex items-start gap-4">
        <div className="min-w-0">
          <a href="/" className="text-xs text-muted hover:underline">← all runs</a>
          <h1 className="font-serif text-2xl mt-1 truncate">
            {run.repo_url.replace("https://github.com/", "")}
          </h1>
          <div className="text-xs text-muted font-mono mt-1">{run.id} · {run.branch}</div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {run.status === "running" && (
            <button onClick={abortThisRun} disabled={aborting}
              className="btn-ghost !px-3 !py-1.5 text-xs !text-bad hover:!bg-bad/5 border-bad/30">
              {aborting ? "Aborting…" : "Abort run"}
            </button>
          )}
          {run.verdict && <Badge value={run.verdict} />}
          <Badge value={run.status} />
        </div>
      </div>

      {fromLocal && (
        <div className="rounded-xl border border-line bg-cream px-4 py-2.5 text-xs text-muted">
          Showing your locally-saved copy of this run — the server keeps runs in memory and was
          restarted, so live updates have stopped. The results below are preserved in your browser.
        </div>
      )}

      <StatusPanel run={run} phases={phases} events={events} />

      {run.status === "error" && (
        <div className="card p-4 border-bad/40 bg-bad/5">
          <div className="flex items-center gap-2 text-sm font-medium text-bad">
            <span>⚠</span> Run failed
          </div>
          <p className="text-sm text-ink/80 mt-1.5">
            {run.error
              || events.filter((e) => e.type === "error").slice(-1)[0]?.message
              || "Something went wrong during the run."}
          </p>
        </div>
      )}

      {run.pr_url && (
        <a href={run.pr_url} target="_blank" rel="noreferrer"
           className="card px-4 py-3 flex items-center gap-2 border-clay-soft bg-clay-wash/40">
          <span className="text-sm font-medium text-clay">Pull request opened</span>
          <span className="text-sm text-clay/80 truncate">{run.pr_url}</span>
          <span className="ml-auto text-clay">↗</span>
        </a>
      )}

      {run.awaiting_selection && run.candidates && run.candidates.length > 0 && (
        <section className="card p-5 border-clay-soft bg-clay-wash/20">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h2 className="font-serif text-lg">Choose scenarios to verify</h2>
            <span className="pill bg-clay-wash text-clay">Human in the loop</span>
            <span className="ml-auto text-sm text-muted">{picked.size}/{run.candidates.length} selected</span>
          </div>
          <p className="text-sm text-muted mb-3">
            These are the auto-generated scenarios. Pick the ones Kane should verify on the live app —
            the rest are skipped.
          </p>
          <div className="flex gap-3 mb-3 text-xs">
            <button className="text-clay hover:underline"
              onClick={() => setPicked(new Set(run.candidates!.map((c) => c.id)))}>Select all</button>
            <button className="text-clay hover:underline" onClick={() => setPicked(new Set())}>Clear</button>
          </div>
          <ul className="space-y-2">
            {run.candidates.map((c) => {
              const on = picked.has(c.id);
              return (
                <li key={c.id}>
                  <label className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors ${
                    on ? "border-clay-soft bg-panel" : "border-line bg-cream hover:border-clay-soft"}`}>
                    <input type="checkbox" checked={on} className="mt-1 h-4 w-4 accent-clay"
                      onChange={() => setPicked((p) => {
                        const n = new Set(p); on ? n.delete(c.id) : n.add(c.id); return n; })} />
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{c.title}</div>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {c.feature && <span className="pill bg-line text-muted">{c.feature}</span>}
                        {c.scenario_type && <span className="pill bg-line text-muted">{c.scenario_type}</span>}
                        {c.criticality && <span className="pill bg-line text-muted">{c.criticality}</span>}
                      </div>
                      {c.objective && <div className="text-xs text-muted mt-1.5">{c.objective}</div>}
                    </div>
                  </label>
                </li>
              );
            })}
          </ul>
          <div className="mt-4 flex items-center gap-3">
            <button className="btn-primary" onClick={submitSelection} disabled={submitting || picked.size === 0}>
              {submitting ? "Starting…" : `Verify ${picked.size} selected →`}
            </button>
            <span className="text-xs text-muted">Only the selected scenarios run through Kane.</span>
          </div>
        </section>
      )}

      {run.metrics?.summary && <MetricsPanel m={run.metrics} />}

      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-6 items-start">
        <div className="space-y-6 md:sticky md:top-20 self-start">
          <PhaseTimeline phases={phases} />

          {run.existing_tests?.length > 0 && (
            <div className="card p-5">
              <h3 className="font-serif text-base mb-3">Existing tests</h3>
              <ul className="space-y-2">
                {run.existing_tests.map((t, i) => {
                  // Kane exports `async def test`, so the function name is a
                  // useless "test" — fall back to the scenario directory name.
                  const dir = t.file.split("/").slice(-2, -1)[0] || "";
                  const label = t.name && t.name !== "test"
                    ? t.name
                    : (dir ? dir.replace(/[_-]+/g, " ") : t.name);
                  return (
                    <li key={i} className="text-sm min-w-0">
                      <div className="truncate" title={label}>{label}</div>
                      <div className="text-xs text-muted font-mono truncate" title={t.file}>
                        {t.file} · {t.framework}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        <div className="space-y-8 min-w-0">
          {generated.some((t) => t.status === "pending" || t.status === "verifying") && (
            <ScenarioChecklist runId={run.id} tests={generated} />
          )}

          <section>
            <h2 className="font-serif text-lg mb-3">Agent ⇄ Kane loop</h2>
            <LoopStream events={events} />
            <div ref={bottom} />
          </section>

          {generated.filter((t) => t.authentic).length > 0 && (
            <section>
              <h2 className="font-serif text-lg mb-3">
                Verified tests
                <span className="text-sm text-muted font-sans ml-2">
                  {generated.filter((t) => t.authentic).length} committed
                </span>
              </h2>
              <div className="space-y-3">
                {generated.filter((t) => t.authentic).map((t) => (
                  <div key={t.scenario_id} className="card p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-mono text-xs text-muted">{t.scenario_id}</span>
                      <span className="text-sm font-medium">{t.title}</span>
                      {t.kane_test_url && (
                        <a href={t.kane_test_url} target="_blank" rel="noreferrer"
                           className="text-xs text-clay hover:underline">session ↗</a>
                      )}
                      <span className="ml-auto"><Badge value="pass" /></span>
                    </div>
                    {t.repair_iterations > 0 && (
                      <div className="text-xs text-muted mb-2">
                        self-corrected in {t.repair_iterations} repair iteration(s)
                      </div>
                    )}
                    {t.code && (
                      <pre className="text-xs font-mono bg-cream rounded-lg p-3 overflow-x-auto border border-line">{t.code}</pre>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {generated.filter((t) => !t.authentic).length > 0 && (
            <section>
              <h2 className="font-serif text-lg mb-3">
                Not verified
                <span className="text-sm text-muted font-sans ml-2">
                  {generated.filter((t) => !t.authentic).length} not committed — shown for visibility
                </span>
              </h2>
              <div className="space-y-2">
                {generated.filter((t) => !t.authentic).map((t) => (
                  <div key={t.scenario_id} className="card p-3 border-l-2 border-clay-soft">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted">{t.scenario_id}</span>
                      <span className="text-sm">{t.title}</span>
                      <span className="ml-auto"><Badge value={t.status} /></span>
                    </div>
                    {t.reason && (
                      <div className="text-xs text-clay/80 mt-1.5">
                        {t.status === "failed" ? "Failed: " : "Why: "}{t.reason}
                      </div>
                    )}
                    {t.kane_test_url && (
                      <a href={t.kane_test_url} target="_blank" rel="noreferrer"
                         className="inline-block text-xs text-clay hover:underline mt-1.5">
                        View Kane session ↗
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
