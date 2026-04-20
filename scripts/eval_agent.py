"""
舆镜 Tool-Calling Agent · 批量评测脚本。

用法：
    python scripts/eval_agent.py                         # 跑全部 20 query
    python scripts/eval_agent.py --limit 3               # 只跑前 3 条（快速验证脚本）
    python scripts/eval_agent.py --resume                # 跳过已在 raw.jsonl 里有结果的 id
    python scripts/eval_agent.py --categories single_event,digest_overview  # 只跑指定类别

产出：
    runtime/eval/agent_eval_raw.jsonl   · 每条 query 一行原始 trajectory（JSON）
    runtime/eval/agent_eval_summary.md  · 汇总 markdown 报告（本脚本**不**覆盖手写的
                                            runtime/eval/agent_eval.md，避免答辩文档被冲掉）

设计要点：
    - 走 `POST /api/agent/chat` 的**非流式**分支拿完整 trajectory（stream=false），
      这样每个 query 一次 HTTP 请求返回最终结构化结果，脚本不关心 SSE 解析。
    - 指标计算全部基于 trajectory 字段，可 reproduce、可追溯。
    - 人工评分留 `manual_notes` 字段空位，生成报告时不产生 task_completion_rate，
      由人工填 runtime/eval/agent_eval.md 后再汇总。
    - 全程不依赖 LLM 评分（避免自验自评套娃）。

依赖：仅 requests + PyYAML，无其他运行时依赖。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUERIES_YAML = PROJECT_ROOT / "runtime" / "eval" / "agent_queries.yaml"
RAW_JSONL = PROJECT_ROOT / "runtime" / "eval" / "agent_eval_raw.jsonl"
SUMMARY_MD = PROJECT_ROOT / "runtime" / "eval" / "agent_eval_summary.md"

DEFAULT_API = "http://localhost:8000/api/agent/chat"
DEFAULT_TIMEOUT = 180  # DeepSeek 调用链 + 多步 tool，最长留 3 分钟


def load_queries(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("queries") or []


def load_existing_ids(path: Path) -> Set[str]:
    """从 raw.jsonl 读已跑过的 query id，支持 --resume。"""
    if not path.exists():
        return set()
    seen: Set[str] = set()
    for line in path.open("r", encoding="utf-8"):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        qid = row.get("id")
        if qid:
            seen.add(qid)
    return seen


def run_one(api: str, query: str, timeout: int) -> Dict[str, Any]:
    """调一次 /api/agent/chat（非流式）；异常统一捕获成 error dict。"""
    t0 = time.time()
    try:
        resp = requests.post(
            api,
            json={"message": query, "stream": False},
            timeout=timeout,
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        if resp.status_code != 200:
            return {
                "ok": False,
                "http_status": resp.status_code,
                "error": resp.text[:300],
                "client_elapsed_ms": elapsed_ms,
            }
        body = resp.json()
        body["ok"] = True
        body["client_elapsed_ms"] = elapsed_ms
        return body
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": f"requests error: {exc}",
            "client_elapsed_ms": int((time.time() - t0) * 1000),
        }


def extract_tool_names(trajectory: Dict[str, Any]) -> List[str]:
    """从 trajectory.steps 里提取调用过的工具名列表（保留调用顺序，允许重复）。"""
    names: List[str] = []
    for step in trajectory.get("steps") or []:
        for tc in step.get("tool_calls") or []:
            nm = tc.get("name")
            if nm:
                names.append(nm)
    return names


def summarize_one(
    spec: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """从 /api/agent/chat 返回里抽 review 需要的结构化字段。"""
    base = {
        "id": spec["id"],
        "category": spec["category"],
        "query": spec["query"],
        "expected_tools": spec.get("expected_tools") or [],
    }
    if not result.get("ok"):
        base.update({
            "ok": False,
            "error": result.get("error"),
            "client_elapsed_ms": result.get("client_elapsed_ms", 0),
        })
        return base

    trajectory = result.get("trajectory") or {}
    tools_called = extract_tool_names(trajectory)
    tools_called_set = set(tools_called)
    expected_set = set(base["expected_tools"])
    # 宽松指标：expected_tools ⊆ tools_called 算 pass（允许 Agent 追加辅助工具）
    recall_hit = expected_set.issubset(tools_called_set) if expected_set else True

    base.update({
        "ok": True,
        "finished": trajectory.get("finished", False),
        "terminated_reason": trajectory.get("terminated_reason", ""),
        "total_latency_ms": trajectory.get("total_latency_ms", 0),
        "client_elapsed_ms": result.get("client_elapsed_ms", 0),
        "step_count": len(trajectory.get("steps") or []),
        "tools_called": tools_called,
        "tools_called_unique": sorted(tools_called_set),
        "expected_tools_recall": recall_hit,
        # HTTP body 顶层字段叫 "final"（见 app/api/agent_routes.py:_blocking_chat）
        "final_answer": (result.get("final") or "").strip(),
        "final_answer_length": len(result.get("final") or ""),
    })
    return base


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_raw(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.open("r", encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按类别 + 全局算指标。"""
    if not rows:
        return {}

    ok_rows = [r for r in rows if r.get("ok")]
    latencies = [r.get("total_latency_ms", 0) for r in ok_rows if r.get("total_latency_ms")]
    steps = [r.get("step_count", 0) for r in ok_rows]
    recall_hits = [1 if r.get("expected_tools_recall") else 0 for r in ok_rows]
    finished = [1 if r.get("finished") else 0 for r in ok_rows]
    tool_usage = Counter()
    for r in ok_rows:
        tool_usage.update(r.get("tools_called_unique") or [])

    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    def _stats(xs: List[int]) -> Dict[str, float]:
        if not xs:
            return {"avg": 0.0, "p50": 0, "p95": 0, "max": 0, "min": 0}
        xs_sorted = sorted(xs)
        p95_idx = max(0, int(round(0.95 * (len(xs_sorted) - 1))))
        return {
            "avg": round(statistics.mean(xs_sorted), 1),
            "p50": xs_sorted[len(xs_sorted) // 2],
            "p95": xs_sorted[p95_idx],
            "max": xs_sorted[-1],
            "min": xs_sorted[0],
        }

    overall = {
        "total": len(rows),
        "ok": len(ok_rows),
        "finished_rate": round(sum(finished) / len(ok_rows), 3) if ok_rows else 0.0,
        "tool_recall_rate": round(sum(recall_hits) / len(ok_rows), 3) if ok_rows else 0.0,
        "latency_ms": _stats(latencies),
        "step_count": _stats(steps),
        "tool_usage": dict(sorted(tool_usage.items(), key=lambda kv: -kv[1])),
    }

    by_category_summary: Dict[str, Any] = {}
    for cat, cat_rows in by_cat.items():
        cat_ok = [r for r in cat_rows if r.get("ok")]
        cat_recall = [1 if r.get("expected_tools_recall") else 0 for r in cat_ok]
        cat_finished = [1 if r.get("finished") else 0 for r in cat_ok]
        cat_lat = [r.get("total_latency_ms", 0) for r in cat_ok if r.get("total_latency_ms")]
        cat_steps = [r.get("step_count", 0) for r in cat_ok]
        by_category_summary[cat] = {
            "total": len(cat_rows),
            "ok": len(cat_ok),
            "finished_rate": round(sum(cat_finished) / len(cat_ok), 3) if cat_ok else 0.0,
            "tool_recall_rate": round(sum(cat_recall) / len(cat_ok), 3) if cat_ok else 0.0,
            "latency_ms": _stats(cat_lat),
            "step_count": _stats(cat_steps),
        }

    return {"overall": overall, "by_category": by_category_summary}


CATEGORY_LABELS = {
    "single_event": "单事件查询",
    "multi_event_compare": "多事件对比",
    "sentiment_trend": "情绪趋势分析",
    "cross_platform": "跨平台差异",
    "digest_overview": "早报/聚合概览",
}


def render_summary_md(rows: List[Dict[str, Any]], agg: Dict[str, Any]) -> str:
    if not agg:
        return "# Agent 评测汇总（空）\n\n尚未产生任何评测结果。\n"

    overall = agg["overall"]
    by_cat = agg["by_category"]
    lines: List[str] = []
    lines.append("# 舆镜 Tool-Calling Agent · 评测汇总")
    lines.append("")
    lines.append("> **自动生成** by `scripts/eval_agent.py`。")
    lines.append("> 人工精读结论与答辩脚本请看同目录的 `agent_eval.md`。")
    lines.append("")
    lines.append(f"- 样本总数：**{overall['total']}** 条（其中成功 {overall['ok']} 条）")
    lines.append(f"- 完成率（finished=true）：**{overall['finished_rate'] * 100:.1f}%**")
    lines.append(f"- 工具召回（expected ⊆ called）：**{overall['tool_recall_rate'] * 100:.1f}%**")
    lines.append("")
    lines.append("## 延迟与步数")
    lines.append("")
    lines.append("| 指标 | 均值 | P50 | P95 | Max | Min |")
    lines.append("|:---|---:|---:|---:|---:|---:|")
    ms = overall["latency_ms"]
    lines.append(f"| Total latency (ms) | {ms['avg']} | {ms['p50']} | {ms['p95']} | {ms['max']} | {ms['min']} |")
    sc = overall["step_count"]
    lines.append(f"| Step count | {sc['avg']} | {sc['p50']} | {sc['p95']} | {sc['max']} | {sc['min']} |")
    lines.append("")

    lines.append("## 工具调用分布")
    lines.append("")
    lines.append("| 工具名 | 被调用次数 |")
    lines.append("|:---|---:|")
    for tool, cnt in overall["tool_usage"].items():
        lines.append(f"| `{tool}` | {cnt} |")
    lines.append("")

    lines.append("## 按类别聚合")
    lines.append("")
    lines.append("| 类别 | 总数 | 完成率 | 工具召回 | Avg latency | Avg steps |")
    lines.append("|:---|---:|---:|---:|---:|---:|")
    for cat, stats in by_cat.items():
        label = CATEGORY_LABELS.get(cat, cat)
        lines.append(
            f"| {label} | {stats['total']} | {stats['finished_rate'] * 100:.0f}% | "
            f"{stats['tool_recall_rate'] * 100:.0f}% | "
            f"{stats['latency_ms']['avg']:.0f}ms | {stats['step_count']['avg']:.1f} |"
        )
    lines.append("")

    lines.append("## 每条 query 明细")
    lines.append("")
    lines.append("| id | 类别 | 查询 | 完成 | 步数 | 延迟 | 调用工具 | 工具召回 |")
    lines.append("|:---|:---|:---|:---:|---:|---:|:---|:---:|")
    for r in rows:
        if not r.get("ok"):
            lines.append(
                f"| {r['id']} | {CATEGORY_LABELS.get(r['category'], r['category'])} | "
                f"{r['query'][:24]}… | ❌ | - | - | - | - |"
            )
            continue
        fin_mark = "✅" if r.get("finished") else "⚠️"
        tools = ", ".join(r.get("tools_called_unique") or []) or "-"
        recall_mark = "✅" if r.get("expected_tools_recall") else "❌"
        lines.append(
            f"| {r['id']} | {CATEGORY_LABELS.get(r['category'], r['category'])} | "
            f"{r['query'][:24]}… | {fin_mark} | {r.get('step_count', 0)} | "
            f"{r.get('total_latency_ms', 0)}ms | {tools} | {recall_mark} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tool-Calling Agent 批量评测")
    parser.add_argument("--api", default=DEFAULT_API, help="Agent chat 接口 URL")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单次 HTTP 超时秒数")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0 = 全部）")
    parser.add_argument("--categories", default="", help="逗号分隔，只跑指定类别")
    parser.add_argument("--resume", action="store_true", help="跳过 raw.jsonl 里已有 id")
    parser.add_argument("--no-write", action="store_true", help="只跑不写文件（调试）")
    parser.add_argument("--summary-only", action="store_true", help="只根据现有 raw.jsonl 重新生成 summary")
    args = parser.parse_args()

    if args.summary_only:
        rows = load_raw(RAW_JSONL)
        agg = aggregate(rows)
        summary = render_summary_md(rows, agg)
        SUMMARY_MD.write_text(summary, encoding="utf-8")
        print(f"[eval_agent] summary regenerated · {len(rows)} rows → {SUMMARY_MD}")
        return 0

    queries = load_queries(QUERIES_YAML)
    if args.categories:
        wanted = {c.strip() for c in args.categories.split(",") if c.strip()}
        queries = [q for q in queries if q["category"] in wanted]
    if args.limit > 0:
        queries = queries[: args.limit]

    seen_ids: Set[str] = load_existing_ids(RAW_JSONL) if args.resume else set()
    to_run = [q for q in queries if q["id"] not in seen_ids]
    print(f"[eval_agent] 计划跑 {len(to_run)} 条 · 跳过已完成 {len(queries) - len(to_run)} 条")

    for idx, spec in enumerate(to_run, 1):
        print(f"\n[{idx}/{len(to_run)}] {spec['id']} ({spec['category']}) · {spec['query']}")
        result = run_one(args.api, spec["query"], args.timeout)
        summary = summarize_one(spec, result)
        if summary.get("ok"):
            # 纯 ASCII console 输出，兼容 Windows GBK 终端
            print(
                f"    [OK] finished={summary['finished']} "
                f"steps={summary['step_count']} "
                f"latency={summary['total_latency_ms']}ms "
                f"tools={summary['tools_called_unique']}"
            )
        else:
            print(f"    [FAIL] error: {summary.get('error', '?')}")

        if not args.no_write:
            append_jsonl(RAW_JSONL, summary)

    # 最后刷新 summary
    if not args.no_write:
        rows = load_raw(RAW_JSONL)
        agg = aggregate(rows)
        summary_md = render_summary_md(rows, agg)
        SUMMARY_MD.write_text(summary_md, encoding="utf-8")
        print(f"\n[eval_agent] summary → {SUMMARY_MD}")
        print(f"[eval_agent] raw    → {RAW_JSONL}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
