"use client";
import { Ev } from "@/lib/api";
import { Badge } from "./Badge";

const STEP_LABEL: Record<string, string> = {
  kane_verify: "Kane · live verify",
  synthesize: "Agent · synthesize",
  execute: "Execute",
  repair: "Agent · repair",
  determinism: "Determinism check",
  accept: "Accept",
};

export function LoopStream({ events }: { events: Ev[] }) {
  const loop = events.filter((e) => e.type === "loop");
  if (!loop.length)
    return (
      <div className="card p-6 text-sm text-muted">
        The agent ⇄ Kane loop will stream here as it verifies each scenario.
      </div>
    );

  return (
    <div className="space-y-3">
      {loop.map((e, i) => (
        <div key={i} className="card p-4 fade-in min-w-0 overflow-hidden">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-muted">{e.scenario}</span>
            <span className="text-xs text-muted">iter {e.iteration}</span>
            <span className="text-sm font-medium ml-1 min-w-0 truncate">{STEP_LABEL[e.step ?? ""] ?? e.step}</span>
            <span className="ml-auto shrink-0"><Badge value={e.status ?? "info"} /></span>
          </div>
          {e.detail && <p className="text-sm text-ink/80 break-words">{e.detail}</p>}
          {e.steps && (
            <ul className="mt-2 text-xs text-muted space-y-0.5">
              {e.steps.map((s, j) => <li key={j} className="break-words">• {s}</li>)}
            </ul>
          )}
          {e.error && (
            <pre className="mt-2 text-xs bg-bad/5 text-bad rounded-lg p-2 overflow-x-auto">{e.error}</pre>
          )}
          {e.code && (
            <pre className="mt-2 text-xs font-mono bg-cream rounded-lg p-3 overflow-x-auto border border-line">{e.code}</pre>
          )}
          {e.kane_session && (
            <a href={e.kane_session} target="_blank" rel="noreferrer"
               className="mt-2 inline-block text-xs text-clay hover:underline">
              View browser session ↗
            </a>
          )}
        </div>
      ))}
    </div>
  );
}
