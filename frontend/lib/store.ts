// Local-browser persistence (no login). Snapshots each run to localStorage so
// history + completed results survive server restarts and page reloads.
import { Run } from "./api";

const INDEX = "atf:runs";
const runKey = (id: string) => `atf:run:${id}`;

export interface RunMeta {
  id: string; repo_url: string; status: string; verdict: string;
  created_at: number; pr_url?: string;
}

export function saveRun(run: Run): void {
  if (typeof window === "undefined" || !run?.id || !run.repo_url) return;
  try {
    localStorage.setItem(runKey(run.id), JSON.stringify(run));
    const meta: RunMeta = {
      id: run.id, repo_url: run.repo_url, status: run.status,
      verdict: run.verdict, created_at: run.created_at, pr_url: run.pr_url,
    };
    const next = [meta, ...listLocal().filter((r) => r.id !== run.id)].slice(0, 50);
    localStorage.setItem(INDEX, JSON.stringify(next));
  } catch { /* quota / disabled — ignore */ }
}

export function loadRun(id: string): Run | null {
  if (typeof window === "undefined") return null;
  try {
    const s = localStorage.getItem(runKey(id));
    return s ? (JSON.parse(s) as Run) : null;
  } catch { return null; }
}

export function listLocal(): RunMeta[] {
  if (typeof window === "undefined") return [];
  try {
    const a = JSON.parse(localStorage.getItem(INDEX) || "[]");
    return Array.isArray(a) ? a : [];
  } catch { return []; }
}
