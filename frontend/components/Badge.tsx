const MAP: Record<string, string> = {
  pass: "bg-ok/10 text-ok", done: "bg-ok/10 text-ok", passed: "bg-ok/10 text-ok",
  authentic: "bg-ok/10 text-ok", GREEN: "bg-ok/10 text-ok",
  fail: "bg-bad/10 text-bad", failed: "bg-bad/10 text-bad", error: "bg-bad/10 text-bad",
  RED: "bg-bad/10 text-bad",
  running: "bg-clay-wash text-clay", info: "bg-clay-wash text-clay",
  YELLOW: "bg-warn/10 text-warn", discarded: "bg-warn/10 text-warn",
  skipped: "bg-line text-muted", queued: "bg-line text-muted", pending: "bg-line text-muted",
  aborted: "bg-line text-muted",
};

export function Badge({ value }: { value: string }) {
  const cls = MAP[value] ?? "bg-line text-muted";
  return <span className={`pill ${cls}`}>{value}</span>;
}
