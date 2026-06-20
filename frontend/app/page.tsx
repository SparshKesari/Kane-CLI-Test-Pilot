"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createRun } from "@/lib/api";
// Run history — commented out for now (restore alongside the section below):
// import { useEffect } from "react";
// import { Run, listRuns, abortAllRuns } from "@/lib/api";
// import { listLocal, RunMeta } from "@/lib/store";
// import { Badge } from "@/components/Badge";

export default function Home() {
  const router = useRouter();
  const [repo, setRepo] = useState("");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"auto" | "human">("auto");
  const [busy, setBusy] = useState(false);

  // Run history — commented out for now (restore alongside the section below):
  // const [runs, setRuns] = useState<Run[]>([]);
  // const [local, setLocal] = useState<RunMeta[]>([]);
  // useEffect(() => {
  //   setLocal(listLocal());
  //   listRuns().then(setRuns).catch(() => {});
  // }, []);
  // // Merge server (fresh) + locally-saved (survives restarts), de-duped by id.
  // const recent = (() => {
  //   const byId = new Map<string, RunMeta>();
  //   for (const m of local) byId.set(m.id, m);
  //   for (const r of runs) byId.set(r.id, {
  //     id: r.id, repo_url: r.repo_url, status: r.status,
  //     verdict: r.verdict, created_at: r.created_at, pr_url: r.pr_url,
  //   });
  //   return [...byId.values()].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0));
  // })();

  async function start() {
    if (!repo.trim() || !url.trim()) return;
    setBusy(true);
    try {
      const run = await createRun(repo, url, 0, mode);   // 0 = auto budget (mode-based)
      router.push(`/runs/${run.id}`);
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-12">
      <section className="text-center max-w-2xl mx-auto pt-6">
        <h1 className="font-serif text-4xl leading-tight tracking-tight">
          Stronger tests for <span className="text-clay">open source.</span>
        </h1>
        <p className="mt-4 text-muted">
          Automatically generate browser-verified tests for any GitHub project. TestPilot learns
          how the app works, creates meaningful scenarios, validates them with the{" "}
          <a href="https://www.testmuai.com/kane-cli/" target="_blank" rel="noreferrer"
             className="text-clay hover:underline">KaneCLI</a>{" "}
          verification loop, and opens a pull request upstream.
        </p>
        <a href="/how-it-works" className="inline-block mt-3 text-sm text-clay hover:underline">
          See how it works →
        </a>
      </section>

      <section className="card p-6 max-w-2xl mx-auto">
        <label className="block text-sm font-medium mb-1.5">GitHub repository</label>
        <input className="input" value={repo} onChange={(e) => setRepo(e.target.value)}
               placeholder="https://github.com/owner/repo" />
        <label className="block text-sm font-medium mb-1.5 mt-4">Public Website URL</label>
        <input className="input" value={url} onChange={(e) => setUrl(e.target.value)}
               placeholder="https://staging.yourapp.com" />

        <label className="block text-sm font-medium mb-1.5 mt-4">Verification mode</label>
        <div className="grid sm:grid-cols-2 gap-2">
          {([
            ["auto", "Auto", "Verify every meaningful scenario, then open a PR — fully hands-off."],
            ["human", "Human in the loop", "Review the auto-generated scenarios and pick which ones Kane verifies."],
          ] as const).map(([val, label, desc]) => (
            <button key={val} type="button" onClick={() => setMode(val)}
              className={`text-left rounded-xl border p-3 transition-colors ${
                mode === val ? "border-clay bg-clay-wash/40" : "border-line hover:border-clay-soft"}`}>
              <div className="flex items-center gap-2 text-sm font-medium">
                <span className={`h-3.5 w-3.5 rounded-full border ${
                  mode === val ? "border-clay bg-clay" : "border-line"}`} />
                {label}
              </div>
              <div className="text-xs text-muted mt-1 ml-5.5">{desc}</div>
            </button>
          ))}
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button className="btn-primary" onClick={start} disabled={busy || !repo.trim() || !url.trim()}>
            {busy ? "Starting…" : "Start run →"}
          </button>
          <span className="text-xs text-muted">Forks to your profile · opens a PR upstream</span>
        </div>
      </section>

      {/* Run history — hidden for now (free tier loses server state on idle).
          To restore, uncomment this section.
      <section className="max-w-2xl mx-auto">
        <div className="flex items-center mb-3">
          <h2 className="font-serif text-lg">Recent runs</h2>
          {recent.some((r) => r.status === "running") && (
            <button onClick={async () => { await abortAllRuns(); listRuns().then(setRuns).catch(() => {}); }}
              className="btn-ghost !px-3 !py-1.5 text-xs ml-auto !text-bad border-bad/30 hover:!bg-bad/5">
              Abort all running
            </button>
          )}
        </div>
        {!recent.length && <p className="text-sm text-muted">No runs yet.</p>}
        <ul className="space-y-2">
          {recent.map((r) => (
            <li key={r.id}>
              <a href={`/runs/${r.id}`}
                 className="card px-4 py-3 flex items-center gap-3 hover:border-clay-soft transition-colors">
                <div className="min-w-0">
                  <div className="text-sm truncate">{r.repo_url.replace("https://github.com/", "")}</div>
                  <div className="text-xs text-muted font-mono">{r.id}</div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  {r.verdict && <Badge value={r.verdict} />}
                  <Badge value={r.status} />
                </div>
              </a>
            </li>
          ))}
        </ul>
      </section>
      */}
    </div>
  );
}
