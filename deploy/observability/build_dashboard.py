"""
Generate grafana/dashboards/nexadesk.json (run after changing panels):

    python deploy/observability/build_dashboard.py

Every panel is a PromQL query over metrics the application emits — no static
numbers. Colours: the validated categorical order (dark-surface steps, Grafana's
default theme) assigned in fixed order per panel; status colours only on
thresholds. One y-axis per panel.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "grafana" / "dashboards" / "nexadesk.json"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
DS = {"type": "prometheus", "uid": "prometheus"}

_id = 0


def _next_id():
    global _id
    _id += 1
    return _id


def ts(title, targets, unit, x, y, w=12, h=8, names=None, description=""):
    """Time series: thin 2px lines, legend table, fixed colours by series name."""
    overrides = []
    for i, name in enumerate(names or []):
        overrides.append({"matcher": {"id": "byName", "options": name},
                          "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": SERIES[i]}}]})
    return {
        "id": _next_id(), "type": "timeseries", "title": title, "description": description, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": leg, "datasource": DS}
                    for i, (e, leg) in enumerate(targets)],
        "fieldConfig": {"defaults": {"unit": unit, "min": 0, "color": {"mode": "palette-classic"},
                                     "custom": {"lineWidth": 2, "fillOpacity": 0, "showPoints": "never",
                                                "axisPlacement": "left", "spanNulls": True}},
                        "overrides": overrides},
        "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def stat(title, expr, unit, x, y, thresholds=None, w=6, h=4, description="", decimals=None):
    steps = [{"color": GOOD, "value": None}] + [{"color": c, "value": v} for v, c in (thresholds or [])]
    return {
        "id": _next_id(), "type": "stat", "title": title, "description": description, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [{"refId": "A", "expr": expr, "datasource": DS}],
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals,
                                     "color": {"mode": "thresholds" if thresholds else "fixed",
                                               "fixedColor": "text"},
                                     "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value" if thresholds else "none",
                    "graphMode": "none", "textMode": "value"},
    }


def row(title, y):
    return {"id": _next_id(), "type": "row", "title": title, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
            "collapsed": False, "panels": []}


R = "[5m]"
panels = [
    row("Traffic", 0),
    stat("Requests / s", f"sum(rate(nexadesk_http_requests_total{R}))", "reqps", 0, 1, decimals=1),
    stat("Server errors (5xx share)",
         f'(sum(rate(nexadesk_http_requests_total{{status=~"5.."}}{R})) or vector(0)) / clamp_min(sum(rate(nexadesk_http_requests_total{R})), 1e-9)',
         "percentunit", 6, 1, thresholds=[(0.01, WARNING), (0.02, CRITICAL)], decimals=2,
         description="Alert NexaDeskHighErrorRate fires above 2% for 5 minutes."),
    stat("p95 latency, all routes",
         f"histogram_quantile(0.95, sum by (le) (rate(nexadesk_http_request_duration_seconds_bucket{R})))",
         "s", 12, 1, thresholds=[(0.5, WARNING), (1.0, CRITICAL)], decimals=3,
         description="Load-test SLO: p95 < 500 ms per endpoint group."),
    stat("Scrape targets up", 'sum(up{job=~"nexadesk-.*"})', "none", 18, 1),
    ts("p95 latency — five slowest routes",
       [(f"topk(5, histogram_quantile(0.95, sum by (le, route) (rate(nexadesk_http_request_duration_seconds_bucket{R}))))",
         "{{route}}")], "s", 0, 5),
    ts("Requests by status class",
       [(f'sum(rate(nexadesk_http_requests_total{{status=~"2..|3.."}}{R}))', "2xx/3xx"),
        (f'sum(rate(nexadesk_http_requests_total{{status=~"4.."}}{R}))', "4xx"),
        (f'sum(rate(nexadesk_http_requests_total{{status=~"5.."}}{R}))', "5xx")],
       "reqps", 12, 5, names=["2xx/3xx", "4xx", "5xx"]),
    row("Background work", 13),
    ts("Jobs by status (database)",
       [('sum by (status) (nexadesk_jobs{status=~"queued|running|failed|dead"})', "{{status}}")],
       "none", 0, 14, names=["queued", "running", "failed", "dead"]),
    stat("Oldest due job waiting", "nexadesk_jobs_oldest_due_age_seconds", "s", 12, 14,
         thresholds=[(120, WARNING), (600, CRITICAL)], description="Alert NexaDeskJobBacklog fires above 10 min."),
    stat("Dead jobs (last 24 h)", 'sum(increase(nexadesk_jobs_total{status="dead"}[24h])) or vector(0)', "none", 18, 14,
         thresholds=[(1, CRITICAL)], decimals=0),
    stat("Email outbox waiting", 'sum(nexadesk_email_outbox{status=~"queued|failed"}) or vector(0)', "none", 12, 18,
         thresholds=[(50, WARNING), (200, CRITICAL)], decimals=0),
    stat("KB documents indexing", "nexadesk_kb_documents_processing", "none", 18, 18, decimals=0),
    ts("Jobs finished per second, by kind",
       [(f"sum by (kind) (rate(nexadesk_jobs_total{R}))", "{{kind}}")], "ops", 0, 22, w=24,
       names=["ai.triage", "kb.ingest", "ai.reindex_tenant"]),
    row("AI assistance", 30),
    ts("Triage agent run time",
       [(f"histogram_quantile(0.5, sum by (le) (rate(nexadesk_agent_run_duration_seconds_bucket{R})))", "p50"),
        (f"histogram_quantile(0.95, sum by (le) (rate(nexadesk_agent_run_duration_seconds_bucket{R})))", "p95")],
       "s", 0, 31, names=["p50", "p95"]),
    ts("Agent step outcomes",
       [(f"sum by (outcome) (rate(nexadesk_ai_steps_total{{outcome!=\"recorded\"}}{R}))", "{{outcome}}")],
       "ops", 12, 31, names=["proposed", "auto_applied", "no_change", "invalid", "failed_verification"],
       description="invalid = blocked by validation; failed_verification = rolled back after an automatic change."),
    stat("Accepted share of human decisions (range)",
         'sum(increase(nexadesk_ai_decisions_total{decision="accept"}[$__range])) / '
         'clamp_min(sum(increase(nexadesk_ai_decisions_total[$__range])), 1)',
         "percentunit", 0, 39, decimals=1,
         description="accept ÷ (accept + edit + reject) in the selected time range. Per-organization figures: "
                     "Dashboard → AI recommendations in the app."),
    stat("Recommendations awaiting a person", "nexadesk_ai_recommendations_awaiting_decision", "none", 6, 39,
         decimals=0),
    stat("LLM tokens (range)", "sum(increase(nexadesk_llm_tokens_total[$__range])) or vector(0)", "none", 12, 39, decimals=0,
         description="Zero while no text-generation provider is configured."),
    stat("LLM call failures (range)", 'sum(increase(nexadesk_llm_calls_total{status!="ok"}[$__range])) or vector(0)', "none",
         18, 39, thresholds=[(1, WARNING), (10, CRITICAL)], decimals=0),
    ts("Knowledge-base queries by outcome",
       [(f"sum by (outcome) (rate(nexadesk_kb_queries_total{R}))", "{{outcome}}")], "ops", 0, 43, w=24,
       names=["results", "no_results", "answered", "no_answer"]),
]

dashboard = {
    "uid": "nexadesk-overview", "title": "NexaDesk — service overview", "tags": ["nexadesk"],
    "timezone": "browser", "schemaVersion": 39, "version": 1, "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"}, "panels": panels,
    "description": "Operational metrics from the API (/metrics) and worker. Organization-level business metrics "
                   "live in the app's dashboards.",
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
print(f"wrote {OUT} ({len(panels)} panels)")
