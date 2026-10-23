#!/usr/bin/env python3
"""Conservative HTTP benchmark for EduNexus or another HTTP application.

Stdlib only. Deployed resource metrics must come from Render and are never
replaced with local machine CPU/RAM. This is a client-side benchmark, not a profiler.
"""
from __future__ import annotations

import argparse
import csv
import concurrent.futures
import json
import math
import os
import platform
import statistics
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urljoin, urlparse


def percentile(values: list[float], p: float):
    if not values:
        return None
    s = sorted(values)
    i = (len(s) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return round(s[lo] + (s[hi] - s[lo]) * (i - lo), 3)


def request(url: str, timeout: float):
    started = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EduNexusBenchmark/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(65536)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
        elapsed = (time.perf_counter() - started) * 1000
        expected = 200 <= status < 400
        if "json" in content_type.lower():
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
                path = urlparse(url).path.rstrip("/")
                if path == "/api/ping":
                    expected = expected and isinstance(data, dict) and data.get("status") == "ok"
                elif path == "/api/health":
                    expected = expected and isinstance(data, dict) and data.get("status") == "ok" and data.get("db") == "connected" and data.get("pgvector") == "ok"
            except (ValueError, UnicodeError):
                expected = False
        return {"latency_ms": round(elapsed, 3), "status": status, "ok": expected,
                "error": None if expected else "unexpected_response"}
    except urllib.error.HTTPError as e:
        return {"latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "status": e.code, "ok": False, "error": "http_error"}
    except Exception as e:
        name = type(e).__name__
        return {"latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "status": None, "ok": False,
                "error": "timeout" if isinstance(e, TimeoutError) or "timeout" in str(e).lower() else name}


def sample_resources(pid: int | None):
    # Host CPU and RAM are not meaningful evidence about the target service.
    # This helper intentionally reports only a local process when explicitly requested.
    if pid is None:
        return None
    try:
        import psutil  # optional dependency
        proc = psutil.Process(pid)
        result = {"process_rss_mb": round(proc.memory_info().rss / 1048576, 2),
                  "process_cpu_percent": proc.cpu_percent(interval=None)}
        return result
    except ImportError:
        return None
    except Exception as e:
        return {"sample_error": type(e).__name__}


def run_stage(urls, rate, concurrency, duration, timeout, pid):
    results = []
    lock = threading.Lock()
    wall_started = datetime.now(timezone.utc).isoformat()
    started, deadline = time.monotonic(), time.monotonic() + duration
    interval = 1.0 / rate
    next_due = started
    resources = []
    stop_sampler = threading.Event()

    def sampler():
        while not stop_sampler.wait(1):
            snap = sample_resources(pid)
            if snap:
                resources.append({"elapsed_seconds": round(time.monotonic() - started, 2), **snap})

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending = set()
        future_urls = {}
        issued = 0
        while time.monotonic() < deadline or pending:
            now = time.monotonic()
            while now < deadline and len(pending) < concurrency and now >= next_due:
                url = urls[issued % len(urls)]
                issued += 1
                future = pool.submit(request, url, timeout)
                pending.add(future)
                future_urls[future] = url
                next_due += interval
                now = time.monotonic()
            if pending:
                done, pending = concurrent.futures.wait(
                    pending, timeout=max(0.001, min(0.05, next_due - time.monotonic())),
                    return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    with lock:
                        result = future.result()
                        result["completed_seconds"] = round(time.monotonic() - started, 4)
                        result["endpoint"] = future_urls.pop(future, None)
                        results.append(result)
            elif time.monotonic() < deadline:
                time.sleep(min(0.01, max(0, next_due - time.monotonic())))
    stop_sampler.set()
    sampler_thread.join(timeout=1)
    elapsed = time.monotonic() - started
    latencies = [x["latency_ms"] for x in results]
    errors = Counter(x["error"] for x in results if x["error"])
    statuses = Counter(str(x["status"]) for x in results if x["status"] is not None)
    chronological = sorted(results, key=lambda x: x["completed_seconds"])
    midpoint = len(chronological) // 2
    early = [x["latency_ms"] for x in chronological[:midpoint]]
    late = [x["latency_ms"] for x in chronological[midpoint:]]
    early_p50, late_p50 = percentile(early, .5), percentile(late, .5)
    degradation = round((late_p50 - early_p50) / early_p50 * 100, 2) if early_p50 else None
    per_endpoint = {}
    for url in urls:
        subset = [x for x in results if x.get("endpoint") == url]
        values = [x["latency_ms"] for x in subset]
        per_endpoint[url] = {"requests": len(subset), "successes": sum(x["ok"] for x in subset),
            "failures": sum(not x["ok"] for x in subset),
            "error_counts": dict(Counter(x["error"] for x in subset if x["error"])),
            "http_status_counts": dict(Counter(str(x["status"]) for x in subset if x["status"] is not None)),
            "latency_ms": {"p50": percentile(values, .5), "p95": percentile(values, .95), "p99": percentile(values, .99)}}
    return {"target_rps": rate, "concurrency_limit": concurrency, "duration_seconds": round(elapsed, 3),
            "started_at": wall_started, "ended_at": datetime.now(timezone.utc).isoformat(),
            "requests": len(results), "throughput_rps": round(len(results) / elapsed, 3) if elapsed else 0,
            "successes": sum(x["ok"] for x in results), "failures": sum(not x["ok"] for x in results),
            "error_counts": dict(errors), "http_status_counts": dict(statuses),
            "per_endpoint": per_endpoint,
            "stability": {"early_half_p50_ms": early_p50, "late_half_p50_ms": late_p50,
                          "p50_change_percent": degradation,
                          "note": "Compared first and second halves of completed requests; descriptive only, not a causal diagnosis."},
            "latency_ms": {"min": round(min(latencies), 3) if latencies else None,
                           "mean": round(statistics.mean(latencies), 3) if latencies else None,
                           "p50": percentile(latencies, .50), "p95": percentile(latencies, .95),
                           "p99": percentile(latencies, .99), "max": round(max(latencies), 3) if latencies else None},
            "resource_samples": resources}


def run_concurrency_stage(urls, concurrency, duration, timeout, per_user_rps):
    """Closed-loop synthetic users; each user waits between sequential GETs."""
    wall_started = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    stop_at = started + duration
    results = []
    lock = threading.Lock()
    spacing = 1.0 / per_user_rps if per_user_rps > 0 else 0

    def user(user_id):
        own, index = [], user_id
        while time.monotonic() < stop_at:
            u = urls[index % len(urls)]
            result = request(u, timeout)
            result["completed_seconds"] = round(time.monotonic() - started, 4)
            result["endpoint"] = u
            own.append(result)
            index += 1
            remaining = stop_at - time.monotonic()
            if spacing and remaining > 0:
                time.sleep(min(spacing, remaining))
        with lock:
            results.extend(own)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(user, range(concurrency)))
    elapsed = time.monotonic() - started
    latencies = [x["latency_ms"] for x in results]
    errors = Counter(x["error"] for x in results if x["error"])
    statuses = Counter(str(x["status"]) for x in results if x["status"] is not None)
    chronological = sorted(results, key=lambda x: x["completed_seconds"])
    midpoint = len(chronological) // 2
    early = [x["latency_ms"] for x in chronological[:midpoint]]
    late = [x["latency_ms"] for x in chronological[midpoint:]]
    early_p50, late_p50 = percentile(early, .5), percentile(late, .5)
    endpoint_summary = {}
    for endpoint in urls:
        subset = [x for x in results if x["endpoint"] == endpoint]
        times = [x["latency_ms"] for x in subset]
        endpoint_summary[endpoint] = {"requests": len(subset),
            "failures": sum(not x["ok"] for x in subset),
            "p50_ms": percentile(times, .5), "p95_ms": percentile(times, .95),
            "p99_ms": percentile(times, .99),
            "http_status_counts": dict(Counter(str(x["status"]) for x in subset if x["status"] is not None))}
    return {
        "concurrent_users": concurrency, "duration_seconds": round(elapsed, 3),
        "started_at": wall_started, "ended_at": datetime.now(timezone.utc).isoformat(),
        "per_user_max_rps": per_user_rps, "requests": len(results),
        "throughput_rps": round(len(results) / elapsed, 3) if elapsed else 0,
        "successes": sum(x["ok"] for x in results), "failures": sum(not x["ok"] for x in results),
        "error_counts": dict(errors), "http_status_counts": dict(statuses),
        "latency_ms": {"min": round(min(latencies), 3) if latencies else None,
                       "mean": round(statistics.mean(latencies), 3) if latencies else None,
                       "p50": percentile(latencies, .5), "p95": percentile(latencies, .95),
                       "p99": percentile(latencies, .99), "max": round(max(latencies), 3) if latencies else None},
        "stability": {"early_half_p50_ms": early_p50, "late_half_p50_ms": late_p50,
                      "p50_change_percent": round((late_p50 - early_p50) / early_p50 * 100, 2)
                      if early_p50 else None},
        "endpoint_counts": dict(Counter(x["endpoint"] for x in results)),
        "per_endpoint": endpoint_summary,
    }


def discover_get_endpoints(base_url, timeout):
    """Read OpenAPI metadata only; never invoke discovered application routes."""
    url = urljoin(base_url.rstrip("/") + "/", "api/openapi.json")
    result = request(url, timeout)
    if not result["ok"]:
        return {"available": False, "url": url, "reason": result.get("error") or result.get("status")}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            spec = json.loads(response.read().decode("utf-8"))
        safe = {"/api/ping", "/api/health"}
        discovered = []
        for path, methods in spec.get("paths", {}).items():
            if "get" not in methods:
                continue
            auth = bool(methods["get"].get("security", spec.get("security", [])))
            discovered.append({"path": path, "authentication_declared": auth,
                               "safe_for_automatic_probe": path in safe})
        return {"available": True, "url": url, "get_routes": discovered,
                "note": "OpenAPI discovery is metadata only; discovered routes are not called. Authenticated/data-dependent routes need explicit endpoint selection and credentials, which this script does not collect."}
    except Exception as e:
        return {"available": False, "url": url, "reason": type(e).__name__}


def read_render_metrics_csv(path):
    """Read documented manual evidence format. Blank values remain unavailable."""
    samples = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            sample = {}
            for key in ("timestamp", "phase", "cpu_percent", "cpu_cores", "memory_mb", "restart_count", "event", "message", "source"):
                if row.get(key, "").strip():
                    value = row[key].strip()
                    if key in {"cpu_percent", "cpu_cores", "memory_mb", "restart_count"}:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                    sample[key] = value
            if sample:
                samples.append(sample)
    numeric_mem = [x["memory_mb"] for x in samples if isinstance(x.get("memory_mb"), (int, float))]
    numeric_cpu = [x["cpu_percent"] for x in samples if isinstance(x.get("cpu_percent"), (int, float))]
    numeric_cores = [x["cpu_cores"] for x in samples if isinstance(x.get("cpu_cores"), (int, float))]
    restarts = [x["restart_count"] for x in samples if isinstance(x.get("restart_count"), (int, float))]
    by_phase = {}
    for phase in sorted({str(x.get("phase")) for x in samples if x.get("phase")}):
        phase_rows = [x for x in samples if str(x.get("phase")) == phase]
        phase_mem = [x["memory_mb"] for x in phase_rows if isinstance(x.get("memory_mb"), (int, float))]
        phase_cpu = [x["cpu_percent"] for x in phase_rows if isinstance(x.get("cpu_percent"), (int, float))]
        by_phase[phase] = {"samples": len(phase_rows), "peak_memory_mb": max(phase_mem) if phase_mem else None,
                           "mean_memory_mb": round(statistics.mean(phase_mem), 2) if phase_mem else None,
                           "peak_cpu_percent": max(phase_cpu) if phase_cpu else None}
    stable_rows = [x for x in samples if str(x.get("phase", "")).lower() in {"stability", "sustained"}]
    stable_mem = [x["memory_mb"] for x in stable_rows if isinstance(x.get("memory_mb"), (int, float))]
    startup_messages = [x for x in samples if x.get("message")]
    embedding_start = next((x for x in startup_messages if "Loading embedding model" in x["message"]), None)
    app_ready = next((x for x in startup_messages if "EduNexus AI ready" in x["message"]), None)
    startup_seconds = None
    if embedding_start and app_ready:
        try:
            a = datetime.fromisoformat(embedding_start["timestamp"].replace("Z", "+00:00"))
            b = datetime.fromisoformat(app_ready["timestamp"].replace("Z", "+00:00"))
            startup_seconds = round((b - a).total_seconds(), 3)
        except (ValueError, TypeError, KeyError):
            pass
    observed_events = [x for x in samples if x.get("event") or x.get("message")]
    has_resource_data = bool(numeric_mem or numeric_cpu or numeric_cores)
    return {"source": "user-supplied Render Metrics/Logs evidence", "status": "available" if has_resource_data else "partial_or_unavailable", "samples": samples,
            "sample_count": len(samples), "peak_memory_mb": max(numeric_mem) if numeric_mem else None,
            "peak_cpu_percent": max(numeric_cpu) if numeric_cpu else None,
            "peak_cpu_cores": max(numeric_cores) if numeric_cores else None,
            "peak_cpu_allocation_percent": max(numeric_cpu) if numeric_cpu else round(max(numeric_cores) / .1 * 100, 2) if numeric_cores else None,
            "memory_limit_mb": 512,
            "peak_memory_percent_of_512_mb": round(max(numeric_mem) / 512 * 100, 2) if numeric_mem else None,
            "restart_count_values": restarts, "by_phase": by_phase,
            "stability_memory_change_mb": round(stable_mem[-1] - stable_mem[0], 2) if len(stable_mem) >= 2 else None,
            "startup_embedding_interval_seconds": startup_seconds,
            "restart_events": [x for x in observed_events if "restart" in str(x.get("event", "") + " " + x.get("message", "")).lower()],
            "event_log_rows": [x for x in observed_events if "log" in str(x.get("source", "")).lower() or "event" in str(x.get("source", "")).lower()],
            "warning": "CSV values are treated as source evidence; verify the selected Render service and time window."}


def _render_metric_series(endpoint, service_id, api_key, start_time, end_time, timeout):
    params = urlencode({"resource": service_id, "startTime": start_time,
                        "endTime": end_time, "resolutionSeconds": 30})
    req = urllib.request.Request(
        f"https://api.render.com/v1/metrics/{endpoint}?{params}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload


def read_render_api_metrics(service_id, api_key, start_time, end_time, timeout):
    """Read-only Render API metrics; caller supplies API key through environment."""
    names = {"cpu": "cpu", "cpu_limit": "cpu-limit", "memory": "memory", "memory_limit": "memory-limit"}
    raw, errors = {}, {}
    for name, endpoint in names.items():
        try:
            raw[name] = _render_metric_series(endpoint, service_id, api_key, start_time, end_time, timeout)
        except urllib.error.HTTPError as exc:
            errors[name] = f"HTTP {exc.code}"
        except Exception as exc:
            errors[name] = type(exc).__name__

    def flatten(series):
        out = []
        for group in series or []:
            labels = {x.get("field"): x.get("value") for x in group.get("labels", [])}
            for point in group.get("values", []):
                out.append({"timestamp": point.get("timestamp"), "value": point.get("value"),
                            "unit": group.get("unit"), "labels": labels})
        return out

    cpu, cpu_limit = flatten(raw.get("cpu")), flatten(raw.get("cpu_limit"))
    memory, memory_limit = flatten(raw.get("memory")), flatten(raw.get("memory_limit"))
    def mb(point):
        value, unit = point["value"], str(point.get("unit", "")).lower()
        if "byte" in unit or unit == "b": return value / 1048576
        if unit in {"gb", "gib"}: return value * (1000 if unit == "gb" else 1024)
        if unit in {"mb", "mib"}: return value * (1 if unit == "mb" else 1.048576)
        return None
    # Preserve units; derive allocation share only when usage/limit units agree.
    cpu_by_time = {x["timestamp"]: x for x in cpu_limit}
    for point in cpu:
        limit = cpu_by_time.get(point["timestamp"])
        point["allocation_percent"] = (round(point["value"] / limit["value"] * 100, 2)
            if limit and point.get("unit") == limit.get("unit") and limit.get("value") else None)
    mem_limit_values = [mb(x) for x in memory_limit if mb(x) is not None]
    return {"source": "Render Public API (read-only metrics endpoints)", "service_id": service_id,
            "window": {"start": start_time, "end": end_time, "resolution_seconds": 30},
            "cpu_samples": cpu, "cpu_limit_samples": cpu_limit,
            "memory_samples": [{**x, "memory_mb": mb(x)} for x in memory],
            "memory_limit_samples": [{**x, "memory_mb": mb(x)} for x in memory_limit],
            "peak_cpu_raw": max((x["value"] for x in cpu), default=None),
            "peak_cpu_unit": cpu[0].get("unit") if cpu else None,
            "peak_cpu_allocation_percent": max((x["allocation_percent"] for x in cpu if x.get("allocation_percent") is not None), default=None),
            "peak_memory_mb": max((mb(x) for x in memory if mb(x) is not None), default=None),
            "memory_limit_mb_from_api": max(mem_limit_values, default=None),
            "errors": errors, "status": "available" if memory or cpu else "unavailable",
            "note": "CPU allocation percentage is calculated only where Render usage and limit samples have identical units and timestamps. Unknown units remain raw and are not compared."}


def build_status_report(args, stages, concurrency_stages, stability, render_metrics, cold_start, csv_evidence):
    concurrency_by_level = {x["concurrent_users"]: x for x in concurrency_stages}
    desired_levels = args.concurrency_levels or [1, 2, 5, 10]
    load_checks = {}
    for level in desired_levels:
        row = concurrency_by_level.get(level)
        load_checks[str(level)] = {"status": ("NOT MEASURED" if row is None else "FAIL" if row["failures"] else "PASS"),
            "measured": row, "units": {"throughput": "requests/second", "latency": "milliseconds"}}
    endpoint_checks = {}
    for endpoint, result in (stages[0].get("per_endpoint", {}) if stages else {}).items():
        endpoint_checks[endpoint] = {"status": "NOT MEASURED" if not result["requests"] else "FAIL" if result["failures"] else "PASS", "measured": result}
    latest_render_metrics = render_metrics or {}
    mem_peak = latest_render_metrics.get("peak_memory_mb")
    mem_limit = latest_render_metrics.get("memory_limit_mb_from_api") or latest_render_metrics.get("memory_limit_mb") or 512
    mem_status = "NOT MEASURED" if mem_peak is None else "FAIL" if mem_peak >= mem_limit else "PASS"
    cpu_ratio = latest_render_metrics.get("peak_cpu_allocation_percent")
    cpu_status = "NOT MEASURED" if cpu_ratio is None else "FAIL" if cpu_ratio > 100 else "PASS"
    phases_present = latest_render_metrics.get("by_phase", {})
    required_phases = ["startup", "idle", "normal_load", "peak_load", "sustained_load"]
    phase_checks = {phase: {"status": "NOT MEASURED" if phase not in phases_present else "PASS",
                            "sample": phases_present.get(phase)} for phase in required_phases}
    if latest_render_metrics.get("phase_samples"):
        phase_checks = {}
        for phase in required_phases:
            sample = latest_render_metrics["phase_samples"].get(phase, {})
            has_both = bool(sample.get("memory_sample_count") and sample.get("cpu_sample_count"))
            over_mem = sample.get("peak_memory_mb") is not None and sample["peak_memory_mb"] >= mem_limit
            over_cpu = sample.get("peak_cpu_allocation_percent") is not None and sample["peak_cpu_allocation_percent"] > 100
            phase_checks[phase] = {"status": "NOT MEASURED" if not has_both else "FAIL" if (over_mem or over_cpu) else "PASS", "sample": sample}
    startup_interval = (csv_evidence or {}).get("startup_embedding_interval_seconds")
    cold_status = "NOT MEASURED" if not cold_start.get("verified_by_render") else "FAIL" if not cold_start.get("first_request", {}).get("ok") else "PASS"
    startup_status = "NOT MEASURED" if startup_interval is None else "PASS"
    sustained_samples = latest_render_metrics.get("phase_samples", {}).get("sustained_load", {})
    sustained_status = ("NOT MEASURED" if stability is None or sustained_samples.get("memory_sample_count", 0) < 2
                        else "FAIL" if stability["failures"] else "PASS")
    restart_evidence = (csv_evidence or {}).get("restart_events", [])
    logs_complete = bool(args.render_logs_complete and csv_evidence and csv_evidence.get("event_log_rows"))
    observed_restart_count = max((x for x in (csv_evidence or {}).get("restart_count_values", []) if isinstance(x, (int, float))), default=None)
    restart_status = "NOT MEASURED" if not logs_complete else "WARNING" if restart_evidence or (observed_restart_count is not None and observed_restart_count > 0) else "PASS"
    highest_tested_clean_users = max((x["concurrent_users"] for x in concurrency_stages if x["failures"] == 0), default=None)
    checks = {
        "baseline_http": {"status": "NOT MEASURED" if not stages else "FAIL" if stages[0]["failures"] else "PASS",
            "requests": stages[0]["requests"] if stages else 0,
            "failures": stages[0]["failures"] if stages else None,
            "note": "PASS/FAIL here means the measured baseline requests returned expected responses; it does not assert a latency SLO."},
        "resource_memory": {"status": mem_status, "peak_mb": mem_peak, "limit_mb": mem_limit,
            "headroom_mb": round(mem_limit - mem_peak, 2) if mem_peak is not None else None,
            "headroom_percent": round((mem_limit - mem_peak) / mem_limit * 100, 2) if mem_peak is not None and mem_limit else None},
        "resource_cpu": {"status": cpu_status, "peak_raw": latest_render_metrics.get("peak_cpu_raw"),
            "unit": latest_render_metrics.get("peak_cpu_unit"), "peak_percent_of_allocation": cpu_ratio,
            "allocation_cores": 0.1},
        "resource_phases": phase_checks,
        "startup_and_cold_start": {"status": "FAIL" if cold_status == "FAIL" else "NOT MEASURED" if "NOT MEASURED" in (cold_status, startup_status) else "PASS",
            "cold_start_status": cold_status, "application_startup_log_interval_status": startup_status,
            "cold_start": cold_start, "embedding_startup_interval_seconds": startup_interval,
            "startup_interval_definition": "Render log timestamp from '[STARTUP] Loading embedding model...' to '[STARTUP] EduNexus AI ready.'; includes intervening app lifespan work and is not an isolated model-only duration."},
        "concurrency": load_checks,
        "endpoints": endpoint_checks,
        "highest_tested_clean_concurrency": {"status": "NOT MEASURED" if highest_tested_clean_users is None else "WARNING",
            "users": highest_tested_clean_users,
            "note": "Highest tested level with zero request failures only; not a capacity guarantee or universal RPS limit."},
        "maximum_sustainable_rps": {"status": "NOT MEASURED" if len(stages) < 2 else "WARNING",
            "estimate_rps": (max((x["target_rps"] for x in stages if x["failures"] == 0 and x["throughput_rps"] >= x["target_rps"] * .9), default=None) if len(stages) >= 2 else None),
            "note": "A bounded estimate across tested rate steps only; not a universal or guaranteed service limit."},
        "sustained_stability": {"status": sustained_status, "result": stability},
        "service_restarts": {"status": restart_status, "events": restart_evidence,
            "max_imported_restart_count": observed_restart_count, "logs_coverage_asserted_complete": logs_complete},
        "workspace_usage_limits": {"status": "NOT MEASURED", "note": "Check current free instance-hours, bandwidth, and build-minute consumption in Render Dashboard billing/usage."},
        "fastembed_inference": {"status": "NOT MEASURED", "reason": "No safe authorized inference endpoint was supplied."},
    }
    statuses = [x["status"] for x in checks.values() if "status" in x]
    statuses.extend(x["status"] for x in phase_checks.values())
    statuses.extend(x["status"] for x in load_checks.values())
    overall = "FAIL" if "FAIL" in statuses else "WARNING" if "WARNING" in statuses else "PASS" if statuses and all(s == "PASS" for s in statuses) else "NOT MEASURED"
    if any(s == "NOT MEASURED" for s in statuses):
        overall = "NOT MEASURED" if "FAIL" not in statuses else "FAIL"
    return {"overall_status": overall, "checks": checks,
            "status_semantics": {"PASS": "Evidence was collected and meets a documented platform limit or explicit check rule.",
                "WARNING": "Evidence is incomplete or noteworthy; no universal latency/RPS threshold is implied.",
                "FAIL": "A measured error or documented resource limit breach occurred.",
                "NOT MEASURED": "Required source data or test run was absent; never treated as passing."}}


def add_phase_summaries(metrics, stages, concurrency_stages, stability, csv_evidence, cold_window=None, idle_window=None):
    """Summarize timestamped service metrics against benchmark stage windows."""
    windows = []
    for index, stage in enumerate(stages):
        windows.append((stage["started_at"], stage["ended_at"], "normal_load" if index == 0 else "peak_load"))
    peak_level = max((x["concurrent_users"] for x in concurrency_stages), default=None)
    for stage in concurrency_stages:
        phase = "peak_load" if stage["concurrent_users"] == peak_level else "normal_load"
        windows.append((stage["started_at"], stage["ended_at"], phase))
    if stability:
        windows.append((stability["started_at"], stability["ended_at"], "sustained_load"))
    if cold_window:
        windows.append((cold_window[0], cold_window[1], "startup"))
    if idle_window:
        windows.append((idle_window[0], idle_window[1], "idle"))
    phases = {p: {"memory": [], "cpu": []} for p in ("startup", "idle", "normal_load", "peak_load", "sustained_load")}
    for collection, kind in ((metrics.get("memory_samples", []), "memory"), (metrics.get("cpu_samples", []), "cpu")):
        for point in collection:
            phase = point.get("phase")
            stamp = point.get("timestamp")
            try:
                t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                for start, end, candidate in windows:
                    if datetime.fromisoformat(start.replace("Z", "+00:00")) <= t <= datetime.fromisoformat(end.replace("Z", "+00:00")):
                        phase = candidate
            except (ValueError, TypeError, AttributeError):
                pass
            if phase in phases:
                phases[phase][kind].append(point)
    for point in (csv_evidence or {}).get("samples", []):
        phase = str(point.get("phase", "")).lower()
        if phase not in phases:
            continue
        if point.get("memory_mb") is not None: phases[phase]["memory"].append(point)
        if point.get("cpu_percent") is not None or point.get("cpu_cores") is not None: phases[phase]["cpu"].append(point)
    metrics["phase_samples"] = {
        phase: {"memory_sample_count": len(values["memory"]), "cpu_sample_count": len(values["cpu"]),
                "peak_memory_mb": max((x.get("memory_mb") for x in values["memory"] if x.get("memory_mb") is not None), default=None),
                "peak_cpu_raw": max((x.get("value", x.get("cpu_cores", x.get("cpu_percent"))) for x in values["cpu"] if x.get("value", x.get("cpu_cores", x.get("cpu_percent"))) is not None), default=None),
                "peak_cpu_allocation_percent": max((x.get("allocation_percent", x.get("cpu_percent", (x.get("cpu_cores") / .1 * 100) if x.get("cpu_cores") is not None else None)) for x in values["cpu"] if x.get("allocation_percent", x.get("cpu_percent", x.get("cpu_cores"))) is not None), default=None)}
        for phase, values in phases.items()}
    sustained_mem = [x.get("memory_mb") for x in phases["sustained_load"]["memory"] if x.get("memory_mb") is not None]
    metrics["stability_memory_change_mb"] = round(sustained_mem[-1] - sustained_mem[0], 2) if len(sustained_mem) >= 2 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="Application origin")
    ap.add_argument("--endpoints", nargs="+", default=["/api/ping", "/api/health"], help="GET paths (or full URLs); defaults include ping and DB/vector health")
    ap.add_argument("--rps", type=float, default=1, help="Scheduled request rate; default 1 RPS")
    ap.add_argument("--concurrency", type=int, default=2, help="Maximum in-flight requests; default 2")
    ap.add_argument("--duration", type=float, default=15, help="Sustained test seconds; default 15")
    ap.add_argument("--timeout", type=float, default=10, help="Per-request timeout seconds")
    ap.add_argument("--warm-requests", type=int, default=3, help="Warm requests after cold-start probe")
    ap.add_argument("--max-rps", type=float, help="Optional step-up test ceiling; run extra stages from --rps to this rate")
    ap.add_argument("--step-rps", type=float, default=1, help="Rate increments for --max-rps")
    ap.add_argument("--concurrency-levels", nargs="+", type=int, help="Run closed-loop user stages, e.g. 1 2 5 10")
    ap.add_argument("--per-user-rps", type=float, default=0.2, help="Max request pace per synthetic user; default 0.2 RPS")
    ap.add_argument("--stability-duration", type=float, default=0, help="Optional sustained stage; use 900-1800 seconds")
    ap.add_argument("--stability-concurrency", type=int, default=1, help="Synthetic users during sustained stage")
    ap.add_argument("--cold-start-idle-minutes", type=float, default=0, help="Optionally wait silently before first request; minimum 15 minutes for Render Free spin-down test")
    ap.add_argument("--cold-start-evidence", help="Operator note referencing Render event/log evidence after >=15 min idle; without it first request is unverified")
    ap.add_argument("--render-service-id", help="Render service ID (srv-...) for read-only Render API metrics; set RENDER_API_KEY in environment")
    ap.add_argument("--render-api-key-env", default="RENDER_API_KEY", help="Environment variable name holding the Render API key")
    ap.add_argument("--render-metrics-csv", help="Render metrics/log evidence CSV; headers: timestamp,phase,cpu_percent,cpu_cores,memory_mb,restart_count,event,message,source")
    ap.add_argument("--render-logs-complete", action="store_true", help="Assert imported Render logs/events CSV covers the entire benchmark window (allows clean-run restart check)")
    ap.add_argument("--print-csv-template", action="store_true", help="Print the required Render evidence CSV format and exit")
    ap.add_argument("--confirm-intensive", action="store_true", help="Required for deployed concurrency >2, stages >60 sec, load ramps, or stability runs")
    ap.add_argument("--allow-deployed", action="store_true", help="Explicitly allow non-local targets (required for all deployed tests)")
    ap.add_argument("--pid", type=int, help="Local application PID to sample (requires psutil)")
    ap.add_argument("--output", default="benchmark-report.json", help="JSON report path")
    args = ap.parse_args()
    if args.print_csv_template:
        print("timestamp,phase,cpu_percent,cpu_cores,memory_mb,restart_count,event,message,source")
        print("<UTC timestamp>,<phase>,<CPU percent of allocation>,<CPU cores>,<memory MB>,<restart count>,<event>,<message>,<source>")
        print("Use cpu_percent as percent of the service's 0.1 CPU allocation, OR cpu_cores as cores; leave the unused column blank.")
        print("memory_mb must be MiB/MB as displayed by Render. Include source=Render Logs/Render Events for event evidence.")
        return
    if args.rps <= 0 or args.concurrency < 1 or args.duration <= 0 or args.timeout <= 0 or args.step_rps <= 0 or args.per_user_rps <= 0:
        ap.error("rates, duration, timeout and step must be positive; concurrency must be at least 1")
    if args.stability_duration and not 900 <= args.stability_duration <= 1800:
        ap.error("--stability-duration must be 900-1800 seconds (15-30 minutes)")
    if args.cold_start_idle_minutes and args.cold_start_idle_minutes < 15:
        ap.error("--cold-start-idle-minutes must be at least 15")
    if args.stability_concurrency < 1 or args.warm_requests < 0:
        ap.error("stability concurrency must be >=1 and warm requests >=0")
    if args.concurrency_levels and any(x < 1 or x > 10 for x in args.concurrency_levels):
        ap.error("concurrency levels must be between 1 and 10")
    base = args.base_url.rstrip("/") + "/"
    urls = [e if urlparse(e).scheme else urljoin(base, e.lstrip("/")) for e in args.endpoints]
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    deployed = any(urlparse(u).hostname not in local_hosts for u in urls)
    if deployed and not args.allow_deployed:
        ap.error("non-local target refused; pass --allow-deployed to confirm you control it")
    intensive = (args.duration > 60 or args.max_rps is not None or args.stability_duration > 0 or
                 (args.concurrency_levels is not None and max(args.concurrency_levels, default=1) > 2) or
                 args.concurrency > 2 or args.rps > 2)
    if deployed and intensive and not args.confirm_intensive:
        ap.error("deployed load is intensive; rerun with --confirm-intensive only if you control this service and accept the free-tier impact")
    if args.max_rps is not None and args.max_rps < args.rps:
        ap.error("--max-rps must be >= --rps")

    report_started = datetime.now(timezone.utc)
    idle_window = None
    if args.cold_start_idle_minutes:
        print(f"Cold-start idle window: waiting {args.cold_start_idle_minutes:g} minutes without requests; ensure no other traffic reaches the service.")
        idle_start = datetime.now(timezone.utc)
        deadline = time.monotonic() + args.cold_start_idle_minutes * 60
        while time.monotonic() < deadline:
            time.sleep(min(30, deadline - time.monotonic()))
        idle_window = (idle_start.isoformat(), datetime.now(timezone.utc).isoformat())
    print("EduNexus HTTP benchmark - client-side measurements")
    print("Target:", ", ".join(urls))
    print("First-request probe (genuine cold start is not assumed)...")
    cold_window_start = datetime.now(timezone.utc).isoformat()
    cold = request(urls[0], args.timeout)
    warms = [request(urls[0], args.timeout) for _ in range(args.warm_requests)]
    warm_times = [x["latency_ms"] for x in warms]
    print(f"  first={cold['latency_ms']:.1f} ms; warm mean={statistics.mean(warm_times):.1f} ms" if warm_times else f"  first={cold['latency_ms']:.1f} ms")
    cold_window = (cold_window_start, datetime.now(timezone.utc).isoformat())
    discovery = discover_get_endpoints(base, args.timeout)
    print(f"OpenAPI GET route discovery: {'available' if discovery['available'] else 'unavailable'} (metadata only)")
    stages = []
    rates = [args.rps]
    if args.max_rps is not None:
        rate = args.rps + args.step_rps
        while rate <= args.max_rps + 1e-9:
            rates.append(round(rate, 5)); rate += args.step_rps
    for rate in rates:
        print(f"Running {rate:g} RPS for {args.duration:g}s (concurrency cap {args.concurrency})...")
        stage = run_stage(urls, rate, args.concurrency, args.duration, args.timeout,
                          None if deployed else args.pid)
        stages.append(stage)
        print(f"  {stage['requests']} requests; {stage['throughput_rps']} achieved RPS; errors {stage['failures']}; p95 {stage['latency_ms']['p95']} ms")

    concurrency_stages = []
    for users in args.concurrency_levels or []:
        print(f"Running {users} synthetic users for {args.duration:g}s...")
        stage = run_concurrency_stage(urls, users, args.duration, args.timeout, args.per_user_rps)
        concurrency_stages.append(stage)
        print(f"  {stage['requests']} requests; {stage['throughput_rps']} achieved RPS; failures {stage['failures']}; timeouts {stage['error_counts'].get('timeout', 0)}; p95 {stage['latency_ms']['p95']} ms")

    stability = None
    if args.stability_duration:
        print(f"Running sustained stage for {args.stability_duration:g}s at {args.stability_concurrency} user(s)...")
        stability = run_concurrency_stage(urls, args.stability_concurrency, args.stability_duration,
                                          args.timeout, args.per_user_rps)
        print(f"  {stability['requests']} requests; failures {stability['failures']}; p95 {stability['latency_ms']['p95']} ms; p50 change {stability['stability']['p50_change_percent']}%")

    first = stages[0]
    max_sustainable = None
    if len(stages) > 1:
        # Operational heuristic, explicitly not a platform capacity guarantee.
        viable = [s["target_rps"] for s in stages if s["failures"] == 0 and
                  s["throughput_rps"] >= s["target_rps"] * .9]
        max_sustainable = max(viable) if viable else None
    csv_evidence = read_render_metrics_csv(args.render_metrics_csv) if args.render_metrics_csv else None
    render_api_key = os.environ.get(args.render_api_key_env)
    render_metrics = None
    api_error = None
    if args.render_service_id and render_api_key:
        try:
            render_metrics = read_render_api_metrics(args.render_service_id, render_api_key,
                report_started.isoformat(), datetime.now(timezone.utc).isoformat(), args.timeout)
        except Exception as exc:
            api_error = type(exc).__name__
    elif args.render_service_id:
        api_error = f"missing environment variable {args.render_api_key_env}"
    if render_metrics and csv_evidence:
        # Preserve both sources and let CSV provide phase labels/log events.
        render_metrics["csv_evidence"] = csv_evidence
        render_metrics["peak_memory_mb"] = max([x for x in (render_metrics.get("peak_memory_mb"), csv_evidence.get("peak_memory_mb")) if x is not None], default=None)
        render_metrics["peak_cpu_raw"] = render_metrics.get("peak_cpu_raw") if render_metrics.get("peak_cpu_raw") is not None else csv_evidence.get("peak_cpu_percent")
        render_metrics["peak_cpu_allocation_percent"] = render_metrics.get("peak_cpu_allocation_percent") if render_metrics.get("peak_cpu_allocation_percent") is not None else csv_evidence.get("peak_cpu_allocation_percent")
    elif csv_evidence:
        render_metrics = csv_evidence
        render_metrics["memory_limit_mb"] = 512
        render_metrics["peak_cpu_allocation_percent"] = csv_evidence.get("peak_cpu_percent")
        render_metrics["peak_cpu_raw"] = csv_evidence.get("peak_cpu_percent")
        render_metrics["peak_cpu_unit"] = "percent_of_allocated_cpu_from_CSV" if csv_evidence.get("peak_cpu_percent") is not None else None
    evidence_events = (csv_evidence or {}).get("event_log_rows", [])
    verified_cold = bool(args.cold_start_idle_minutes >= 15 and csv_evidence and any(
        any(term in str(x.get("event", "") + " " + x.get("message", "")).lower() for term in ("spin up", "spin-up", "instance started", "cold start"))
        for x in evidence_events))
    if render_metrics:
        add_phase_summaries(render_metrics, stages, concurrency_stages, stability, csv_evidence,
                            cold_window if verified_cold else None, idle_window)
    cold_record = {"first_request": cold, "warm_mean_ms": round(statistics.mean(warm_times), 3) if warm_times else None,
        "warm_p50_ms": percentile(warm_times, .5), "warm_samples": warms,
        "classification": "render_log_confirmed_after_15m_idle" if verified_cold else "ordinary_first_request_unverified",
        "idle_wait_minutes": args.cold_start_idle_minutes or None,
        "operator_evidence_note": args.cold_start_evidence,
        "verified_by_render": verified_cold,
        "note": "Confirmed only when the script waited at least 15 minutes and imported Render event/log evidence has a startup marker. Otherwise this is not a verified cold start."}
    assessment = build_status_report(args, stages, concurrency_stages, stability, render_metrics, cold_record, csv_evidence)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "application": "EduNexus (FastAPI backend + Next.js frontend)",
        "measurement_scope": "HTTP timings and outcomes are measured at this client. For deployed runs, no local CPU/RAM samples are used as a proxy for Render. Render resource metrics appear only when supplied through --render-metrics-csv.",
        "configuration": {"urls": urls, "timeout_seconds": args.timeout, "warm_requests": args.warm_requests,
                          "requested_rates_rps": rates, "concurrency": args.concurrency,
                          "stage_duration_seconds": args.duration, "concurrency_levels": args.concurrency_levels,
                          "per_user_rps": args.per_user_rps, "stability_duration_seconds": args.stability_duration,
                          "stability_concurrency": args.stability_concurrency,
                          "cold_start_idle_minutes": args.cold_start_idle_minutes,
                          "render_service_id": args.render_service_id,
                          "client_platform": platform.platform(), "target_is_deployed": deployed},
        "cold_start": cold_record,
        "stages": stages, "estimated_max_sustainable_rps": max_sustainable,
        "concurrency_stages": concurrency_stages, "stability_stage": stability,
        "endpoint_discovery": discovery,
        "endpoint_coverage": {
            "tested": urls,
            "safe_representative_choices": {"/api/ping": "lightweight process/HTTP health; Render health check route",
                "/api/health": "read-only database SELECT and pgvector operator plus embedding model loaded state",
                "/api/openapi.json": "metadata-only endpoint discovery; not a representative load endpoint"},
            "fastembed": "Health reports whether the FastEmbed model is loaded, but this app exposes no identified safe unauthenticated GET that executes embedding inference. Inference latency and CPU/RAM therefore remain unmeasured unless a separately authorized, non-destructive endpoint is supplied.",
            "authenticated_routes": "OpenAPI-discovered routes are listed, not automatically called. Select only read-only routes and provide credentials through a separately reviewed mechanism; this script does not accept or print secrets."},
        "sustainability_method": "Highest tested rate with zero failures and achieved throughput >=90% of target; estimate over tested rates and duration only." if len(stages) > 1 else "Not estimated: provide --max-rps for a rate ramp.",
        "render_metrics": render_metrics or {"status": "NOT MEASURED", "reason": api_error or "No Render API credentials/service ID or CSV evidence was supplied.",
            "how_to_collect": "Supply --render-service-id srv-... and RENDER_API_KEY, or collect Dashboard Metrics plus Events/logs into the documented CSV. Render API time series resolution is at least 30 seconds; short phases may have no datapoints."},
        "resource_measurements": render_metrics or {"status": "NOT MEASURED", "reason": api_error or "No Render CPU/RAM series supplied. Local machine metrics are never substituted.",
            "how_to_collect": "Render Dashboard > backend service > Metrics: record CPU and memory for startup, idle, normal load, peak load, and sustained load. Events/logs provide restarts and startup markers. CSV headers: timestamp,phase,cpu_percent,cpu_cores,memory_mb,restart_count,event,message,source."},
        "service_restart_detection": {"client_detection": "The script records request failures, timeouts, and latency shifts, which can be consistent with a restart but cannot identify a restart conclusively.",
            "status": "unavailable_without_render_event_or_log_samples", "check": "Compare the run window with Render service Events and logs; include restart_count in supplied metrics CSV if recorded."},
        "deployment_readiness": {
            "measured": {"latency_percentiles_ms": first["latency_ms"], "throughput_rps": first["throughput_rps"], "failures": first["failures"]},
            "render_free_constraints": {"measured_peak_memory_mb": render_metrics.get("peak_memory_mb") if render_metrics else None,
                "memory_limit_mb": (render_metrics.get("memory_limit_mb_from_api") or render_metrics.get("memory_limit_mb") or 512) if render_metrics else 512,
                "memory_headroom_mb": round((render_metrics.get("memory_limit_mb_from_api") or render_metrics.get("memory_limit_mb") or 512) - render_metrics["peak_memory_mb"], 2) if render_metrics and render_metrics.get("peak_memory_mb") is not None else None,
                "peak_cpu_raw": render_metrics.get("peak_cpu_raw") if render_metrics else None,
                "peak_cpu_unit": render_metrics.get("peak_cpu_unit") if render_metrics else None,
                "peak_cpu_percent_of_allocation": render_metrics.get("peak_cpu_allocation_percent") if render_metrics else None,
                "cpu": "Render free web service plan is 0.1 CPU and 512 MB RAM; shared-plan CPU contention can affect latency. This is plan metadata, not measured usage.",
                "spin_down": "Free services spin down after 15 consecutive minutes without inbound traffic and commonly take about one minute to spin back up.",
                "usage": "750 free instance hours per workspace/month; free services also count toward outbound bandwidth and build-pipeline included usage. Render may restart services; free web services are single-instance and not intended for production.",
                "rps_limit": "No guaranteed sustainable RPS is stated here; capacity is application-, dependency-, and traffic-dependent."},
            "other_constraints_and_notes": [
                "Vercel functions have plan-dependent duration, memory, and invocation constraints; this backend benchmark does not measure Vercel frontend quotas.",
                "EduNexus backend startup loads the FastEmbed embedding model, which can increase startup time and memory use. The configured Render health check uses /api/ping; /api/health additionally probes database/vector connectivity.",
                "Client measurements cannot isolate frontend, proxy, database, model, or provider latency. Test endpoints that are safe and representative; GET-only requests are used."
            ]},
        "assessment": assessment,
        "official_render_free_limits": {
            "status": "DOCUMENTED PLATFORM LIMITS; ACCOUNT USAGE REMAINS ACCOUNT-SPECIFIC",
            "web_service_compute": {"cpu_cores": 0.1, "memory_mb": 512, "source": "Render compute plans"},
            "spin_down": {"idle_minutes": 15, "typical_wake_seconds": 60},
            "monthly_instance_hours": 750,
            "bandwidth_and_build_minutes": "Count against workspace included usage; included amounts and current consumption must be checked in Render Dashboard. No universal bandwidth amount asserted.",
            "other": ["Free services may be restarted by Render.", "A Free web service is single-instance and cannot scale beyond one instance.", "Free services have ephemeral filesystem and no persistent disk.", "Free services are not recommended for production by Render.", "Free web services can be suspended after unusually high service-initiated public traffic.", "If using Render Free Postgres: 1 GB storage, 30-day expiry, no backups, and no managed connection pooling."],
            "no_universal_rps_or_latency_limit": True,
            "source_urls": ["https://render.com/docs/compute-plans", "https://render.com/docs/free", "https://render.com/docs/service-metrics", "https://api-docs.render.com/reference/get-cpu", "https://api-docs.render.com/reference/get-memory"]
        },
        "application_recommendations": [
            "No universal latency or RPS pass threshold is imposed. Set app-specific SLOs before interpreting performance as acceptable.",
            "Verify FastEmbed startup memory and cold-start effect from Render logs/metrics. A model-loaded health field is not embedding-inference latency.",
            "Use read-only authenticated GET routes only with explicit test credentials supplied through a secure process; this script does not accept credentials for EduNexus endpoints."
        ],
        "resource_measurement": "Deployed service CPU/RAM come only from Render Public API metrics or explicitly imported Render evidence; local psutil/process metrics are never substituted for deployed targets.",
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("\nSummary")
    print(f"Requests: {first['requests']} | success: {first['successes']} | failed: {first['failures']}")
    print(f"Latency ms: p50 {first['latency_ms']['p50']} | p95 {first['latency_ms']['p95']} | p99 {first['latency_ms']['p99']}")
    print(f"Throughput: {first['throughput_rps']} RPS | errors: {first['error_counts'] or 'none'}")
    print(f"Max sustainable estimate: {max_sustainable if max_sustainable is not None else 'not established'}")
    if concurrency_stages:
        print("Concurrency stages:", ", ".join(f"{s['concurrent_users']} users: {s['throughput_rps']} RPS, p95 {s['latency_ms']['p95']} ms, failures {s['failures']}" for s in concurrency_stages))
    print(f"Compatibility assessment: {assessment['overall_status']}")
    print("CPU/RAM phase metrics:", render_metrics.get("status", "NOT MEASURED") if render_metrics else "NOT MEASURED")
    if render_metrics:
        print(f"Peak RAM/headroom: {render_metrics.get('peak_memory_mb')} / {render_metrics.get('memory_limit_mb_from_api') or render_metrics.get('memory_limit_mb') or 512} MB; headroom {assessment['checks']['resource_memory']['headroom_mb']} MB")
        print(f"Peak CPU: {render_metrics.get('peak_cpu_raw')} {render_metrics.get('peak_cpu_unit')}; allocation use {render_metrics.get('peak_cpu_allocation_percent')}%")
    print("Required checks:", ", ".join(f"{k}={v['status']}" for k, v in assessment["checks"].items() if "status" in v))
    print("Concurrency checks:", ", ".join(f"{users} users={v['status']}" for users, v in assessment["checks"]["concurrency"].items()))
    print("Phase checks:", ", ".join(f"{k}={v['status']}" for k, v in assessment["checks"]["resource_phases"].items()))
    print(f"Detailed JSON: {os.path.abspath(args.output)}")
    if args.stability_duration:
        print("Stability: request trends measured; confirm restarts and CPU/RAM in Render Events, logs, and Metrics.")


if __name__ == "__main__":
    main()
