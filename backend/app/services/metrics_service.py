from __future__ import annotations

from ..models import Run


def _labels(crawl: dict) -> list[str]:
    """Discovered interactive/visible surface of the live app."""
    out = list(crawl.get("buttons", [])) + list(crawl.get("headings", []))
    out += [l["text"] for l in crawl.get("links", [])]
    seen, uniq = set(), []
    for x in out:
        k = " ".join(x.split()).strip()
        if k and len(k) > 2 and k.lower() not in seen:
            seen.add(k.lower()); uniq.append(k)
    return uniq[:40]


def build(run: Run, crawl: dict, proposed: list[dict], gate_dropped: list[dict]) -> dict:
    """Functional-coverage + quality metrics for the repo under test.

    NOTE: this is functional/scenario coverage of the live app's discovered
    surface — not source-line coverage (we test a deployed app from outside)."""
    tests = run.tests
    verified = [t for t in tests if t.authentic]
    discarded = [t for t in tests if t.status == "discarded"]
    failed = [t for t in tests if t.status == "failed"]
    verified_ids = {t.scenario_id for t in verified}

    # Per-feature + per-criticality + per-scenario-type breakdown (from proposed).
    feat: dict[str, dict] = {}
    crit: dict[str, dict] = {"HIGH": {"proposed": 0, "verified": 0},
                             "MEDIUM": {"proposed": 0, "verified": 0},
                             "LOW": {"proposed": 0, "verified": 0}}
    stype: dict[str, dict] = {"HAPPY": {"proposed": 0, "verified": 0},
                              "NEGATIVE": {"proposed": 0, "verified": 0},
                              "EDGE": {"proposed": 0, "verified": 0}}
    # feature × scenario-type matrix: which kinds of coverage each feature has.
    matrix: dict[str, dict] = {}
    for sc in proposed:
        f = sc.get("feature", "GENERAL")
        c = sc.get("criticality", "MEDIUM").upper()
        t = str(sc.get("scenario_type", "HAPPY")).upper()
        feat.setdefault(f, {"proposed": 0, "verified": 0})
        feat[f]["proposed"] += 1
        crit.setdefault(c, {"proposed": 0, "verified": 0})
        crit[c]["proposed"] += 1
        stype.setdefault(t, {"proposed": 0, "verified": 0})
        stype[t]["proposed"] += 1
        matrix.setdefault(f, {"HAPPY": 0, "NEGATIVE": 0, "EDGE": 0})
        matrix[f][t] = matrix[f].get(t, 0) + 1
        if sc["id"] in verified_ids:
            feat[f]["verified"] += 1
            crit[c]["verified"] += 1
            stype[t]["verified"] += 1

    # Features lacking negative/edge coverage — the gaps a gap-fill run targets.
    missing_types = {f: [k for k in ("NEGATIVE", "EDGE") if not row.get(k)]
                     for f, row in matrix.items()}
    missing_types = {f: ks for f, ks in missing_types.items() if ks}

    # Surface coverage: which discovered elements are exercised by a verified test
    verified_text = " ".join(
        f"{sc.get('title','')} {sc.get('objective','')}".lower()
        for sc in proposed if sc["id"] in verified_ids)
    labels = _labels(crawl)
    exercised = [l for l in labels if l.lower() in verified_text]
    uncovered = [l for l in labels if l.lower() not in verified_text]

    durations = {p.key: round((p.ended_at - p.started_at), 1)
                 for p in run.phases if p.started_at and p.ended_at}

    from ..config import get_settings
    greenfield = len(run.existing_tests) <= get_settings().greenfield_max_existing
    kept = len(proposed) - len(gate_dropped)
    return {
        "note": "Functional/scenario coverage of the live app surface — not source-line coverage.",
        "mode": "greenfield" if greenfield else "gapfill",
        "summary": {
            "existing_tests": len(run.existing_tests),
            "scenarios_proposed": len(proposed),
            "gate_kept": kept,
            "gate_dropped": len(gate_dropped),
            "verified": len(verified),
            "discarded": len(discarded),
            "failed": len(failed),
            "new_tests_committed": len(verified),
            "verify_rate_pct": round(100 * len(verified) / kept, 1) if kept else 0.0,
        },
        "surface_coverage": {
            "elements_found": len(labels),
            "elements_exercised": len(exercised),
            "pct": round(100 * len(exercised) / len(labels), 1) if labels else 0.0,
            "uncovered": uncovered[:20],
        },
        "feature_coverage": [
            {"feature": k, **v} for k, v in sorted(feat.items(), key=lambda x: -x[1]["proposed"])],
        "criticality": crit,
        "scenario_types": stype,
        "coverage_matrix": matrix,
        "missing_types": missing_types,
        "phase_durations_s": durations,
        "total_duration_s": round(sum(durations.values()), 1),
    }


def to_markdown(m: dict, run: Run) -> str:
    s = m["summary"]; sc = m["surface_coverage"]
    mode_blurb = ("greenfield — broad first-time coverage"
                  if m.get("mode") == "greenfield" else "gap-fill — adding the missing cases")
    lines = [
        "# End-to-End Test Coverage", "",
        f"> {m['note']}", "",
        f"**Mode:** {mode_blurb}", "",
        "## Summary", "",
        f"- Existing tests in repo: **{s['existing_tests']}**",
        f"- Candidate scenarios: **{s['scenarios_proposed']}** → "
        f"kept after filtering: **{s['gate_kept']}** (dropped {s['gate_dropped']})",
        f"- Verified live & committed: **{s['verified']}** · "
        f"discarded {s['discarded']} · failed {s['failed']}",
        f"- Verify rate: **{s['verify_rate_pct']}%**",
        "",
        "## Functional surface coverage", "",
        f"- Discovered interactive elements: **{sc['elements_found']}**",
        f"- Exercised by a verified test: **{sc['elements_exercised']}** "
        f"(**{sc['pct']}%**)",
    ]
    if sc["uncovered"]:
        lines += ["", "**Not yet covered:** " + ", ".join(sc["uncovered"])]
    lines += ["", "## Coverage by feature", "",
              "| Feature | Proposed | Verified |", "|---|---|---|"]
    for f in m["feature_coverage"]:
        lines.append(f"| {f['feature']} | {f['proposed']} | {f['verified']} |")
    lines += ["", "## Coverage by criticality", "",
              "| Criticality | Proposed | Verified |", "|---|---|---|"]
    for k in ("HIGH", "MEDIUM", "LOW"):
        c = m["criticality"].get(k, {"proposed": 0, "verified": 0})
        lines.append(f"| {k} | {c['proposed']} | {c['verified']} |")
    st = m.get("scenario_types", {})
    lines += ["", "## Coverage by scenario type", "",
              "| Type | Proposed | Verified |", "|---|---|---|"]
    for k in ("HAPPY", "NEGATIVE", "EDGE"):
        c = st.get(k, {"proposed": 0, "verified": 0})
        lines.append(f"| {k} | {c['proposed']} | {c['verified']} |")
    missing = m.get("missing_types", {})
    if missing:
        lines += ["", "**Coverage gaps (no scenario of this type yet):**"]
        lines += [f"- {f}: missing {', '.join(ks)}" for f, ks in sorted(missing.items())]
    not_verified = [t for t in run.tests if not t.authentic]
    if not_verified:
        lines += ["", "## Scenarios not verified (not committed as tests)", "",
                  "These flows were proposed but could not be turned into a trustworthy "
                  "test — surfaced here for visibility, not silently dropped.", "",
                  "| Scenario | Status | Why |", "|---|---|---|"]
        for t in not_verified:
            why = (t.reason or "—").replace("|", "\\|").replace("\n", " ")[:140]
            lines.append(f"| {t.scenario_id} · {t.title} | {t.status} | {why} |")
    lines += ["", f"## Run timing", "",
              f"Total: **{m['total_duration_s']}s** — " +
              ", ".join(f"{k} {v}s" for k, v in m["phase_durations_s"].items())]
    return "\n".join(lines) + "\n"
