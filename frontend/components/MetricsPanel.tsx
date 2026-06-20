"use client";
import { Metrics } from "@/lib/api";

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: "ok" | "bad" | "warn" }) {
  const color = tone === "ok" ? "text-ok" : tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "";
  return (
    <div className="rounded-xl border border-line bg-cream px-3 py-2">
      <div className={`text-lg font-serif ${color}`}>{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}

function Bar({ pct }: { pct: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-line overflow-hidden">
      <div className="h-full bg-clay" style={{ width: `${Math.min(100, pct)}%` }} />
    </div>
  );
}

export function MetricsPanel({ m }: { m: Metrics }) {
  const s = m.summary ?? {};
  const sc = m.surface_coverage;
  return (
    <div className="card p-5 space-y-5">
      <div className="flex items-baseline justify-between">
        <h3 className="font-serif text-base">Coverage &amp; metrics</h3>
        {m.total_duration_s ? <span className="text-xs text-muted">{m.total_duration_s}s</span> : null}
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        <Stat label="proposed" value={s.scenarios_proposed ?? 0} />
        <Stat label="verified" value={s.verified ?? 0} tone="ok" />
        <Stat label="failed" value={s.failed ?? 0} tone={s.failed ? "bad" : undefined} />
        <Stat label="discarded" value={s.discarded ?? 0} tone={s.discarded ? "warn" : undefined} />
        <Stat label="verify rate" value={`${s.verify_rate_pct ?? 0}%`} />
      </div>

      {sc && (
        <div>
          <div className="flex items-center justify-between text-sm mb-1.5">
            <span>Functional surface coverage</span>
            <span className="text-muted">{sc.elements_exercised}/{sc.elements_found} · {sc.pct}%</span>
          </div>
          <Bar pct={sc.pct} />
          {sc.uncovered?.length > 0 && (
            <div className="text-xs text-muted mt-2">
              not covered: {sc.uncovered.slice(0, 8).join(", ")}
            </div>
          )}
        </div>
      )}

      {m.feature_coverage && m.feature_coverage.length > 0 && (
        <div>
          <div className="text-sm mb-2">By feature</div>
          <div className="space-y-2.5">
            {m.feature_coverage.map((f) => (
              <div key={f.feature}>
                <div className="flex items-center justify-between gap-2 text-xs mb-1">
                  <span className="truncate text-muted" title={f.feature}>{f.feature}</span>
                  <span className="shrink-0 text-muted tabular-nums">{f.verified}/{f.proposed}</span>
                </div>
                <Bar pct={f.proposed ? (100 * f.verified) / f.proposed : 0} />
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-muted">{m.note}</p>
    </div>
  );
}
