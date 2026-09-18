"""Mine TechDeck's plugin_runs.log + plugin_detail.log for step-level timing.

Reads (per machine):
  - plugin_runs.log      -> run windows: RUN START <id> ... RUN OK/CANCELLED/ERROR/PAUSED <id>
  - plugin_detail.log    -> ms-timestamped per-step lines: "<ts> <plugin_id> | <message>"
  - usage_log.csv        -> total durations per version (successful runs only)

Sources:
  - local machine: %LOCALAPPDATA%\\TechDeck\\logs (+ usage\\usage_log.csv)
  - colleagues:    C:\\Dev\\Samples\\colleague_logs\\<name>\\  (raw logs OR TechDeck_DebugReport_*.txt)

Writes: C:\\Dev\\Samples\\TechDeck Run Profile.md
"""

from __future__ import annotations

import csv
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TS_RE = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d\d\d"
RUN_RE = re.compile(
    rf"^(?P<ts>{TS_RE}) (?P<lvl>\w+)\s+RUN (?P<ev>START|OK|CANCELLED|ERROR|PAUSED|REFUSED|TIMEOUT|WARNING)\s+(?P<pid>\S+)(?P<rest>.*)$"
)
# Old format: "<ts> <pid> | <msg>"; new (2026-08-21+): "<ts> <pid> [token] | <msg>"
# plus console prompt markers "<ts> prompt | open" / "closed after N.Ns".
DETAIL_RE = re.compile(
    rf"^(?P<ts>{TS_RE}) (?P<pid>\S+)(?: \[(?P<tok>[0-9a-f]{{6}})\])? \| (?P<msg>.*)$"
)
VER_RE = re.compile(r"\(v([^)]+)\)")
DUR_RE = re.compile(r"(?:in|after) (\d+(?:\.\d+)?)s")

SAMPLES = Path(r"C:\Dev\Samples")
OUT_PATH = SAMPLES / "TechDeck Run Profile.md"
COLLEAGUE_DIR = SAMPLES / "colleague_logs"
LOCAL_LOGS = Path(os.environ["LOCALAPPDATA"]) / "TechDeck" / "logs"
LOCAL_USAGE = Path(os.environ["LOCALAPPDATA"]) / "TechDeck" / "usage" / "usage_log.csv"


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S,%f")


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- sources

def gather_sources():
    """Yield (machine_label, runs_text, detail_text, usage_rows)."""
    sources = []

    def rotated(base: Path):
        # oldest first so line order stays chronological
        parts = sorted(base.parent.glob(base.name + ".*"), reverse=True)
        texts = [read_text(p) for p in parts if p.suffix[1:].isdigit()]
        if base.is_file():
            texts.append(read_text(base))
        return "\n".join(texts)

    if LOCAL_LOGS.is_dir():
        usage = []
        if LOCAL_USAGE.is_file():
            with LOCAL_USAGE.open(newline="", encoding="utf-8", errors="replace") as fh:
                usage = list(csv.DictReader(fh))
        sources.append((
            "This machine (%s)" % os.environ.get("COMPUTERNAME", "local"),
            rotated(LOCAL_LOGS / "plugin_runs.log"),
            rotated(LOCAL_LOGS / "plugin_detail.log"),
            usage,
        ))

    if COLLEAGUE_DIR.is_dir():
        for d in sorted(COLLEAGUE_DIR.iterdir()):
            if not d.is_dir():
                continue
            runs_t, detail_t, usage = "", "", []
            rl = d / "plugin_runs.log"
            dl = d / "plugin_detail.log"
            if rl.is_file():
                runs_t = read_text(rl)
            if dl.is_file():
                detail_t = read_text(dl)
            uc = d / "usage_log.csv"
            if uc.is_file():
                with uc.open(newline="", encoding="utf-8", errors="replace") as fh:
                    usage = list(csv.DictReader(fh))
            # debug reports: extract embedded log sections (tails only)
            for rep in sorted(d.glob("TechDeck_DebugReport_*.txt")):
                text = read_text(rep)
                runs_t += "\n" + extract_section(text, "plugin_runs.log")
                detail_t += "\n" + extract_section(text, "plugin_detail.log")
            if runs_t.strip() or detail_t.strip():
                sources.append((f"Colleague: {d.name}", runs_t, detail_t, usage))
    return sources


def extract_section(report_text: str, name: str) -> str:
    lines = report_text.splitlines()
    out, in_sec = [], False
    for ln in lines:
        if ln.startswith(f"--- {name}"):
            in_sec = True
            continue
        if in_sec and (ln.startswith("--- ") or ln.startswith("=== ")):
            break
        if in_sec:
            out.append(ln)
    return "\n".join(out)


# ---------------------------------------------------------------- parsing

class Run:
    __slots__ = ("pid", "version", "start", "end", "status", "reported", "steps")

    def __init__(self, pid, version, start):
        self.pid = pid
        self.version = version
        self.start = start
        self.end = None
        self.status = "UNKNOWN"       # crashed / log truncated
        self.reported = None          # seconds from the RUN OK/... line
        self.steps = []               # (ts, msg)


def parse_runs(runs_text: str):
    runs, open_runs = [], {}
    for ln in runs_text.splitlines():
        m = RUN_RE.match(ln)
        if not m:
            continue
        ts = parse_ts(m["ts"])
        pid, ev, rest = m["pid"], m["ev"], m["rest"]
        if ev == "START":
            if pid in open_runs:            # previous run never closed (crash?)
                runs.append(open_runs.pop(pid))
            vm = VER_RE.search(rest)
            open_runs[pid] = Run(pid, vm.group(1) if vm else "?", ts)
        else:
            r = open_runs.pop(pid, None)
            if r is None:
                continue
            r.end, r.status = ts, ev
            dm = DUR_RE.search(rest)
            r.reported = float(dm.group(1)) if dm else (ts - r.start).total_seconds()
            runs.append(r)
    runs.extend(open_runs.values())
    return runs


def attach_detail(runs, detail_text: str):
    by_pid = defaultdict(list)
    for r in runs:
        by_pid[r.pid].append(r)
    for lst in by_pid.values():
        lst.sort(key=lambda r: r.start)
    unmatched = 0
    for ln in detail_text.splitlines():
        m = DETAIL_RE.match(ln)
        if not m:
            continue
        ts = parse_ts(m["ts"])
        pid = m["pid"]
        msg = m["msg"]
        if pid == "prompt":
            # Console prompt marker — attach to whichever run window contains it.
            candidates = runs
            msg = "[prompt] " + msg
        else:
            candidates = by_pid.get(pid, ())
        hit = None
        for r in candidates:
            end = r.end or r.start
            if (ts - r.start).total_seconds() >= -1.5 and (ts - end).total_seconds() <= 1.5:
                hit = r
                break
        if hit is None:
            unmatched += 1
        else:
            hit.steps.append((ts, msg))
    return unmatched


# ---------------------------------------------------------------- analysis

def normalize(msg: str) -> str:
    s = msg.strip()
    if s.startswith("[prompt] open"):
        return "(user at a prompt — human time)"
    if s.startswith("[progress]"):
        return "[progress] update"
    s = re.sub(r"^\[\d+/\d+\]\s*\S.*$", "[#/#] (per-item loop)", s)
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"\s+", " ", s)
    return s[:72]


def gaps_of(run: Run):
    """(seconds, raw_msg) pairs — each gap attributed to the line ANNOUNCING the work."""
    if not run.steps:
        return []
    out = []
    steps = sorted(run.steps)
    lead = (steps[0][0] - run.start).total_seconds()
    if lead > 0.05:
        out.append((lead, "(startup: before first log line)"))
    for (t1, m1), (t2, _m2) in zip(steps, steps[1:]):
        out.append(((t2 - t1).total_seconds(), m1))
    if run.end:
        tail = (run.end - steps[-1][0]).total_seconds()
        if tail > 0.05:
            out.append((tail, "(wrap-up after: %s)" % steps[-1][1].strip()[:60]))
    return out


def fmt_s(x: float) -> str:
    return f"{x:,.1f}s" if x < 120 else f"{x/60:,.1f}m"


def analyze(machine, runs, usage, out):
    ok = [r for r in runs if r.status in ("OK", "WARNING")]
    out.append(f"\n# {machine}\n")
    if not runs:
        out.append("_No runs found._\n")
        return
    t0 = min(r.start for r in runs).date()
    t1 = max(r.start for r in runs).date()
    total_time = sum(r.reported or 0 for r in runs)
    out.append(
        f"**{len(runs)} runs** ({len(ok)} completed) across {t0} → {t1}. "
        f"Total plugin wall-time: **{fmt_s(total_time)}**.\n"
    )

    per = defaultdict(list)
    for r in runs:
        per[r.pid].append(r)

    # ---- per-plugin summary table
    out.append("\n## Per-plugin totals (all statuses)\n")
    out.append("| Plugin | Runs | OK | Median OK | Max OK | Total time |")
    out.append("|---|---:|---:|---:|---:|---:|")
    rows = sorted(per.items(), key=lambda kv: -sum(r.reported or 0 for r in kv[1]))
    for pid, rs in rows:
        oks = [r.reported for r in rs if r.status in ("OK", "WARNING") and r.reported]
        med = fmt_s(statistics.median(oks)) if oks else "-"
        mx = fmt_s(max(oks)) if oks else "-"
        tot = fmt_s(sum(r.reported or 0 for r in rs))
        out.append(f"| `{pid}` | {len(rs)} | {len(oks)} | {med} | {mx} | {tot} |")

    # ---- where the time goes, per plugin (top step-buckets)
    out.append("\n## Where the time goes (aggregated step gaps)\n")
    out.append(
        "_Each gap between two consecutive log lines is charged to the line that "
        "announced the work. `[#/#] (per-item loop)` = the plugin's per-file/order loop._\n"
    )
    coverage_notes = []
    for pid, rs in rows[:10]:
        buckets = defaultdict(lambda: [0.0, 0, 0.0, ""])  # key -> [total, count, max, example]
        stepped = [r for r in rs if r.steps and r.reported]
        if not stepped:
            continue
        cov_num = cov_den = 0.0
        for r in stepped:
            g = gaps_of(r)
            cov_num += sum(x for x, _ in g)
            cov_den += r.reported or 0
            for sec, msg in g:
                b = buckets[normalize(msg)]
                b[0] += sec
                b[1] += 1
                if sec > b[2]:
                    b[2], b[3] = sec, msg.strip()[:90]
        plugin_total = sum(b[0] for b in buckets.values())
        coverage_notes.append((pid, cov_num, cov_den))
        out.append(f"\n### `{pid}` — {len(stepped)} runs with step data, {fmt_s(plugin_total)} accounted\n")
        out.append("| Step (normalized) | Total | Share | Hits | Worst single | Example |")
        out.append("|---|---:|---:|---:|---:|---|")
        top = sorted(buckets.items(), key=lambda kv: -kv[1][0])[:8]
        for key, (tot, cnt, mx, ex) in top:
            share = 100.0 * tot / plugin_total if plugin_total else 0
            out.append(
                f"| {key} | {fmt_s(tot)} | {share:.0f}% | {cnt} | {fmt_s(mx)} | {ex} |"
            )

    # ---- black boxes: biggest single silent gaps anywhere
    out.append("\n## Biggest single silent gaps (the black boxes)\n")
    out.append("| When | Plugin | Gap | Line that announced it |")
    out.append("|---|---|---:|---|")
    all_gaps = []
    for r in runs:
        for sec, msg in gaps_of(r):
            all_gaps.append((sec, r, msg))
    for sec, r, msg in sorted(all_gaps, key=lambda x: -x[0])[:15]:
        out.append(
            f"| {r.start:%Y-%m-%d %H:%M} | `{r.pid}` | {fmt_s(sec)} | {msg.strip()[:90]} |"
        )

    # ---- usage trend
    if usage:
        out.append("\n## Duration trend by version (usage_log.csv, successful runs)\n")
        tr = defaultdict(list)
        for row in usage:
            try:
                tr[(row["Plugin ID"], row["TechDeck Version"])].append(float(row["Duration (s)"]))
            except (KeyError, ValueError):
                continue
        out.append("| Plugin | Version | Runs | Median |")
        out.append("|---|---|---:|---:|")
        for (pid, ver), ds in sorted(tr.items()):
            out.append(f"| `{pid}` | {ver} | {len(ds)} | {fmt_s(statistics.median(ds))} |")

    # ---- sanity
    out.append("\n## Sanity check (step-gap sum vs reported run time)\n")
    for pid, num, den in coverage_notes:
        if den:
            out.append(f"- `{pid}`: gaps account for {100*num/den:.0f}% of reported wall time")


def main():
    sources = gather_sources()
    if not sources:
        print("No log sources found.")
        return 1
    COLLEAGUE_DIR.mkdir(exist_ok=True)
    out = [
        "# TechDeck Run Profile",
        "",
        f"_Mined from real run logs on {datetime.now():%Y-%m-%d %H:%M}. "
        "No instrumentation added — this is what TechDeck already recorded._",
        "",
        "Drop colleague logs (plugin_runs.log + plugin_detail.log, or a "
        "TechDeck_DebugReport_*.txt) into `C:\\Dev\\Samples\\colleague_logs\\<name>\\` "
        "and re-run to fold them in.",
    ]
    for machine, runs_t, detail_t, usage in sources:
        runs = parse_runs(runs_t)
        unmatched = attach_detail(runs, detail_t)
        analyze(machine, runs, usage, out)
        if unmatched:
            out.append(f"\n_({unmatched} detail lines fell outside any known run window "
                       "— logging outside runs or clock skew; ignored.)_")
    OUT_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
