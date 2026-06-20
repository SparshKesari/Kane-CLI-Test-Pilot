"use client";
import { useState } from "react";
import { TestArtifact, abortScenario } from "@/lib/api";

// Live, per-scenario status during the Kane loop — so you can see exactly which
// scenarios are being driven right now, which are queued, how each settled, and
// abort any that are slow or hung.
const ST: Record<string, { icon: string; label: string; cls: string; pulse?: boolean }> = {
  verifying: { icon: "●", label: "verifying…", cls: "text-clay", pulse: true },
  pending:   { icon: "○", label: "queued",     cls: "text-muted" },
  authentic: { icon: "✓", label: "verified",   cls: "text-ok" },
  failed:    { icon: "✕", label: "failed",      cls: "text-bad" },
  discarded: { icon: "!", label: "discarded",   cls: "text-warn" },
  aborted:   { icon: "⊘", label: "aborted",     cls: "text-muted" },
};
const ORDER: Record<string, number> = {
  verifying: 0, pending: 1, failed: 2, discarded: 3, aborted: 4, authentic: 5,
};

export function ScenarioChecklist({ runId, tests }: { runId: string; tests: TestArtifact[] }) {
  const [aborting, setAborting] = useState<Set<string>>(new Set());
  if (!tests.length) return null;
  const verified = tests.filter((t) => t.authentic).length;
  const live = tests.filter((t) => t.status === "verifying").length;
  const sorted = [...tests].sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9));

  async function abort(id: string) {
    setAborting((p) => new Set(p).add(id));
    try { await abortScenario(runId, id); } catch { /* ignore */ }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="font-serif text-base">Scenarios</h3>
        <span className="text-xs text-muted">
          {verified}/{tests.length} verified{live ? ` · ${live} running` : ""}
        </span>
      </div>
      <ul className="space-y-1.5">
        {sorted.map((t) => {
          const s = ST[t.status] ?? ST.pending;
          const cancellable = t.status === "verifying" || t.status === "pending";
          const isAborting = aborting.has(t.scenario_id);
          return (
            <li key={t.scenario_id} className="flex items-center gap-2.5 text-sm">
              <span className={`w-4 text-center ${s.cls} ${s.pulse ? "dot-pulse" : ""}`}>{s.icon}</span>
              <span className="truncate">{t.title}</span>
              {t.kane_test_url && (
                <a href={t.kane_test_url} target="_blank" rel="noreferrer"
                   className="text-xs text-clay/70 hover:underline shrink-0">session ↗</a>
              )}
              {cancellable ? (
                <button onClick={() => abort(t.scenario_id)} disabled={isAborting}
                  className="ml-auto text-xs text-muted hover:text-bad shrink-0 disabled:opacity-50"
                  title="Abort this scenario">
                  {isAborting ? "aborting…" : "✕ abort"}
                </button>
              ) : (
                <span className={`ml-auto text-xs shrink-0 ${s.cls}`}>{s.label}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
