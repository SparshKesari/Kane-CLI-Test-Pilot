"use client";
import { Phase } from "@/lib/api";

const ICON: Record<string, string> = {
  done: "✓", running: "●", failed: "✕", pending: "○", skipped: "–",
};

const WHAT: Record<string, string> = {
  P1: "Fork & clone the repo", P2: "Read framework, routes & source",
  P3: "Index existing tests", P4: "Crawl app & propose scenarios",
  P5: "Filter to meaningful scenarios", P6: "Verify each in a real browser (Kane)",
  P7: "Generate Kane CI workflow", P8: "Commit tests & open a PR",
};

export function PhaseTimeline({ phases }: { phases: Phase[] }) {
  return (
    <div className="card p-5">
      <h3 className="font-serif text-base mb-4">Pipeline</h3>
      <ol className="space-y-1">
        {phases.map((p) => {
          const active = p.state === "running";
          const color =
            p.state === "done" ? "text-ok" :
            p.state === "failed" ? "text-bad" :
            active ? "text-clay" : "text-muted";
          return (
            <li key={p.key} className="flex items-start gap-3 py-1.5">
              <span className={`mt-0.5 w-5 text-center ${color} ${active ? "dot-pulse" : ""}`}>
                {ICON[p.state]}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-muted">{p.key}</span>
                  <span className={`text-sm ${active ? "font-medium" : ""}`}>{p.name}</span>
                </div>
                <div className="text-xs text-muted/80">{WHAT[p.key]}</div>
                {p.detail && <div className="text-xs text-clay/80 truncate">{p.detail}</div>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
