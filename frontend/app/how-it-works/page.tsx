"use client";
import { useState } from "react";

function SectionHead({ n, title, sub }: { n: string; title: string; sub: string }) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-clay">{n}</span>
        <h2 className="font-serif text-2xl tracking-tight">{title}</h2>
      </div>
      <p className="text-muted mt-1.5 max-w-2xl">{sub}</p>
    </div>
  );
}

function CodeBlock({ code, label }: { code: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="rounded-xl2 bg-term text-termfg/90 font-mono text-xs overflow-hidden shadow-soft">
      <div className="flex items-center px-4 py-2 border-b border-white/10">
        <span className="text-termfg/50">{label ?? "shell"}</span>
        <button
          onClick={() => { navigator.clipboard?.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
          className="ml-auto text-termfg/60 hover:text-termfg">{copied ? "copied ✓" : "copy"}</button>
      </div>
      <pre className="px-4 py-3 overflow-x-auto whitespace-pre leading-relaxed">{code}</pre>
    </div>
  );
}

const LOOP = [
  ["Propose", "An LLM reads your live UI and page source, then proposes one tight, meaningful scenario with a concrete expected result."],
  ["Drive", "Kane CLI runs that scenario in a real Chrome browser against your live app — no selectors, no scripts, just the intent."],
  ["Observe", "Did the intended behavior actually happen? Kane reports each step pass/fail from the real session."],
  ["Synthesize", "Kane's real browser trace becomes a clean, deterministic Playwright test."],
  ["Gate", "Intent + assertion checks reject “false greens” before anything is committed."],
];

const PHASES = [
  ["P1", "Fork & clone", "Forks the repo to your profile and clones it."],
  ["P2", "Understand the app", "Detects the framework and reads routes, components and page source."],
  ["P3", "Inventory existing tests", "Indexes what's already covered so it only adds what's missing."],
  ["P4", "Propose scenarios", "Crawls the live app and proposes meaningful happy / negative / edge scenarios."],
  ["P5", "Meaningfulness gate", "Drops duplicates and anything without a concrete, observable assertion."],
  ["P6", "Verify with Kane", "Drives each scenario in a real browser — the verification loop above."],
  ["P7", "Kane CI workflow", "Commits a GitHub Actions workflow that re-verifies the tests with Kane CLI."],
  ["P8", "Commit & open PR", "Commits only the verified tests and opens a pull request."],
];

const GATES = [
  ["Live-verified", "Every committed test was performed in a real browser on your live app — not hallucinated from code."],
  ["No false greens", "If Kane does a different action than intended, or the test asserts nothing meaningful, it's rejected."],
  ["Fully transparent", "Scenarios that couldn't be verified are shown with the reason — never silently dropped."],
];

export default function HowItWorks() {
  return (
    <div className="space-y-16 pb-16">
      <section className="text-center max-w-2xl mx-auto pt-2">
        <a href="/" className="text-xs text-muted hover:underline">← back</a>
        <h1 className="font-serif text-4xl leading-tight tracking-tight mt-2">
          How <span className="text-clay">TestPilot</span> works
        </h1>
        <p className="mt-4 text-muted">
          Paste a repo. TestPilot understands the app, writes end-to-end tests, and proves each one
          works in a real browser with{" "}
          <a href="https://www.testmuai.com/kane-cli/" target="_blank" rel="noreferrer"
             className="text-clay hover:underline">Kane CLI</a> — then opens a
          pull request with a Kane-powered CI workflow included.
        </p>
      </section>

      {/* 01 — the verification loop */}
      <section>
        <SectionHead n="01" title="The verification loop"
          sub="The core difference: every test is proven real in a browser before it's committed. If Kane can't actually perform the flow, the test is never shipped — so you never get a green test for a broken feature." />
        <div className="grid md:grid-cols-5 gap-3">
          {LOOP.map(([t, d], i) => (
            <div key={t} className="relative card p-4">
              <div className="font-mono text-xs text-clay mb-1">{`0${i + 1}`}</div>
              <div className="font-serif text-base mb-1">{t}</div>
              <div className="text-xs text-muted leading-relaxed">{d}</div>
              {i < LOOP.length - 1 && (
                <span className="hidden md:block absolute -right-2.5 top-1/2 -translate-y-1/2 text-clay-soft">→</span>
              )}
            </div>
          ))}
        </div>
        <div className="mt-3 grid sm:grid-cols-2 gap-3">
          <div className="rounded-xl border border-ok/30 bg-ok/5 px-4 py-3 text-sm">
            <span className="text-ok font-medium">✓ Accepted</span>
            <span className="text-muted"> — committed to the PR as a verified test.</span>
          </div>
          <div className="rounded-xl border border-warn/30 bg-warn/5 px-4 py-3 text-sm">
            <span className="text-warn font-medium">↻ Retried, then surfaced</span>
            <span className="text-muted"> — flaky runs retry; what still can't be verified is shown, not hidden.</span>
          </div>
        </div>
      </section>

      {/* 02 — the pipeline */}
      <section>
        <SectionHead n="02" title="The 8-phase pipeline"
          sub="From a repo URL to an open pull request. You see exactly what's happening at every phase — the run view streams it live." />
        <ol className="space-y-2">
          {PHASES.map(([k, name, d]) => (
            <li key={k} className="card p-4 flex items-start gap-4">
              <span className="font-mono text-xs text-clay bg-clay-wash rounded-md px-2 py-1 mt-0.5">{k}</span>
              <div>
                <div className="font-medium text-sm">{name}</div>
                <div className="text-sm text-muted">{d}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* 03 — trust */}
      <section>
        <SectionHead n="03" title="Why you can trust the tests"
          sub="TestPilot is built to never ship a test that doesn't actually verify a behavior." />
        <div className="grid sm:grid-cols-3 gap-3">
          {GATES.map(([t, d]) => (
            <div key={t} className="card p-4">
              <div className="font-serif text-base mb-1">{t}</div>
              <div className="text-sm text-muted leading-relaxed">{d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 04 — how to use */}
      <section>
        <SectionHead n="04" title="How to use it" sub="Three steps from repo to reviewed pull request." />
        <div className="grid sm:grid-cols-3 gap-3">
          {[
            ["Paste a repo", "Give it a GitHub repo and the live app URL Kane should drive."],
            ["Pick a mode", "Auto runs hands-off. Human-in-the-loop lets you choose which scenarios to verify. Set the scenario budget."],
            ["Review the PR", "Watch each phase live, then review the opened pull request with the verified suite."],
          ].map(([t, d], i) => (
            <div key={t} className="card p-4">
              <div className="h-7 w-7 rounded-lg bg-clay text-white text-sm flex items-center justify-center font-medium mb-2">{i + 1}</div>
              <div className="font-medium text-sm mb-0.5">{t}</div>
              <div className="text-sm text-muted">{d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 05 — CI */}
      <section>
        <SectionHead n="05" title="Use the tests in your CI"
          sub="Every run commits a GitHub Actions workflow that re-verifies the suite with Kane CLI — the same tool that proved them — in a real browser on every push and PR. The same behavior, re-checked." />
        <div className="space-y-4">
          <ol className="space-y-2">
            {[
              ["Add two repo secrets", "Settings → Secrets and variables → Actions: LT_USERNAME and LT_ACCESS_KEY."],
              ["Enable Actions on the fork", "GitHub disables Actions on new forks — click the “I understand, enable them” banner."],
              ["Push or open a PR", "The committed .github/workflows/kane-tests.yml replays each test with Kane CLI automatically."],
            ].map(([t, d], i) => (
              <li key={t} className="card p-4 flex items-start gap-4">
                <span className="font-mono text-xs text-clay bg-clay-wash rounded-md px-2 py-1 mt-0.5">{i + 1}</span>
                <div><div className="font-medium text-sm">{t}</div><div className="text-sm text-muted">{d}</div></div>
              </li>
            ))}
          </ol>
          <div>
            <div className="text-sm font-medium mb-1.5">Replay a test locally</div>
            <CodeBlock label="bash" code={`npm install -g @testmuai/kane-cli
kane-cli testmd run tests/e2e/<test-name>/<test-name>.md \\
  --username "$LT_USERNAME" --access-key "$LT_ACCESS_KEY"`} />
          </div>
          <div>
            <div className="text-sm font-medium mb-1.5">The committed workflow (excerpt)</div>
            <CodeBlock label=".github/workflows/kane-tests.yml" code={`name: End-to-End Tests (Kane CLI)
on: [push, pull_request, workflow_dispatch]
jobs:
  kane:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm install -g @testmuai/kane-cli
      - name: Replay verified tests
        env:
          LT_USERNAME: \${{ secrets.LT_USERNAME }}
          LT_ACCESS_KEY: \${{ secrets.LT_ACCESS_KEY }}
        run: |
          find tests/e2e -name '*.md' ! -name 'README.md' ! -name 'COVERAGE.md' -print0 |
            while IFS= read -r -d '' t; do
              kane-cli testmd run "$t" --username "$LT_USERNAME" --access-key "$LT_ACCESS_KEY"
            done`} />
          </div>
        </div>
      </section>

      <div className="text-center pt-2">
        <a href="/" className="btn-primary">Start a run →</a>
      </div>
    </div>
  );
}
