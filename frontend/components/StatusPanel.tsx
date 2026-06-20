"use client";
import { useEffect, useState } from "react";
import { Ev, Phase, Run } from "@/lib/api";

// What each phase is doing, in plain English — so the user always understands
// what the app has done and is doing.
const PHASE_WHAT: Record<string, string> = {
  P1: "Forking the repo to your profile and cloning it",
  P2: "Reading the app's framework, routes and page source",
  P3: "Indexing the repo's existing tests",
  P4: "Crawling the live app and proposing meaningful scenarios",
  P5: "Filtering out duplicates and low-value scenarios",
  P6: "Driving the live app in a real browser (Kane) to verify each scenario",
  P7: "Generating a GitHub Actions workflow to re-verify the tests with Kane CLI",
  P8: "Committing the verified tests and opening a pull request",
};

function fmt(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  return `${m}m ${sec % 60}s`;
}

export function StatusPanel({ run, phases, events }: { run: Run; phases: Phase[]; events: Ev[] }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  const terminal = ["passed", "failed", "error", "aborted"].includes(run.status);
  useEffect(() => {
    if (terminal) return;
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, [terminal]);

  // While running, tick wall-clock. Once finished, FREEZE at the true run
  // duration (from metrics or the last phase end) — otherwise reopening an old
  // run shows time-since-created (e.g. 313m), not how long it actually ran.
  const lastEnded = phases.reduce((mx, p) => (p.ended_at && p.ended_at > mx ? p.ended_at : mx), 0);
  const frozen = run.metrics?.total_duration_s
    ?? (lastEnded ? lastEnded - (run.created_at || lastEnded) : null);
  const elapsed = Math.max(0, Math.round(
    terminal && frozen != null ? frozen : now - (run.created_at || now)
  ));
  const doneCount = phases.filter((p) => p.state === "done").length;
  const totalPhases = phases.length;
  const current = phases.find((p) => p.state === "running");
  const lastLoop = [...events].reverse().find((e) => e.type === "loop");

  // headline + status word
  let headline = "> Run in progress…";
  let statusWord = "running";
  let statusColor = "text-clay-soft";
  if (run.awaiting_selection) { headline = "> Paused — waiting for your selection"; statusWord = "awaiting you"; }
  else if (run.status === "passed") {
    headline = "> Run complete"; statusWord = run.verdict || "done";
    statusColor = run.verdict === "GREEN" ? "text-ok" : "text-warn";
  } else if (run.status === "error" || run.status === "failed") {
    headline = "> Run ended with errors"; statusWord = "error"; statusColor = "text-bad";
  }

  const activity = run.awaiting_selection
    ? "Review the proposed scenarios below and choose which to verify."
    : current
      ? `${PHASE_WHAT[current.key] ?? current.name}${current.detail ? ` — ${current.detail}` : ""}`
      : terminal ? (run.pr_url ? "Pull request opened. Tests committed." : "Finished.")
        : "Starting…";

  return (
    <div className="rounded-xl2 bg-term text-termfg/90 font-mono text-xs shadow-soft overflow-hidden">
      <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-white/10">
        <span className="h-2.5 w-2.5 rounded-full bg-bad/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-warn/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-ok/80" />
        <span className="ml-2 text-termfg/50">kane · {run.branch || run.id}</span>
        {!terminal && !run.awaiting_selection &&
          <span className="ml-auto inline-flex gap-1">
            <span className="dot-pulse">●</span><span className="text-termfg/50">live</span>
          </span>}
      </div>
      <div className="px-4 py-3 space-y-1.5 leading-relaxed">
        <div className="text-termfg">{headline}</div>
        <div className="text-termfg/75">{activity}</div>
        {lastLoop?.scenario && !run.awaiting_selection && current?.key === "P6" && (
          <div className="text-termfg/55">
            ↳ {lastLoop.scenario} · {lastLoop.step} · {lastLoop.detail?.slice(0, 80)}
          </div>
        )}
        <div className="pt-1 text-termfg/60">
          Phase <span className="text-termfg">{current ? current.key : `${doneCount}/${totalPhases}`}</span>
          {current && <span className="text-termfg/50"> ({current.name})</span>}
          {"  ·  "}Elapsed <span className="text-termfg">{fmt(elapsed)}</span>
          {"  ·  "}Status <span className={statusColor}>{statusWord}</span>
        </div>
      </div>
    </div>
  );
}
