"""ab_frontier.py — 前沿模型对照实验（强红队 × 弱蓝队）

三个臂：
  strong_solo        强模型一次成型（qwen3.8-max）
  weak+strong        弱蓝队(本地7B) 写 → 强红队(qwen3.8-max) 挑刺 → 弱蓝队改
  strong+strong      强模型写 → 强模型挑刺 → 强模型改

用 QWENCLOUD_API_KEY 调 https://maas.qianwenaiapi.com/compatible-mode/v1
结果写 out/frontier_results.jsonl，汇总写 out/frontier_table.md。
"""

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.request

import ab_suite as A

BASE = "https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions"
MODEL = "qwen3.8-max"
KEY = os.environ.get("QWENCLOUD_API_KEY", "").strip()
OUT = os.path.join(A.OUT_DIR, "frontier_results.jsonl")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_usage = {"in": 0, "out": 0}
_lock = threading.Lock()


def api(prompt, model=MODEL, temperature=0.7, max_tokens=3000, timeout=420, effort="low"):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning_effort": effort,
    }).encode()
    req = urllib.request.Request(BASE, data=body, headers={
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    u = data.get("usage", {})
    with _lock:
        _usage["in"] += u.get("prompt_tokens", 0)
        _usage["out"] += u.get("completion_tokens", 0)
    return data["choices"][0]["message"]["content"] or "", time.time() - t0


def local(prompt, seed=0):
    return A.ask(A.GEN_MODEL, prompt, seed=seed)


def one(task, arm, rep):
    seed = rep * 1000 + abs(hash(task["name"])) % 997
    spec, sig = task["spec"], task["sig"]
    rec = dict(task=task["name"], arm=arm, rep=rep, ok=False, why="", seconds=0.0,
               critique="", critique_hit=False)
    t0 = time.time()
    try:
        if arm == "strong_solo":
            text, _ = api(A.GEN_PROMPT.format(spec=spec, sig=sig), temperature=0.7)
            code = A.extract_code(text)
            ok, why = A.run_tests(task, code)
            rec.update(ok=ok, why=why)

        elif arm == "weak+strong":
            text, _ = local(A.GEN_PROMPT.format(spec=spec, sig=sig), seed=seed)
            code = A.extract_code(text)
            ok0, why0 = A.run_tests(task, code)
            if ok0:
                rec.update(ok=True)
            else:
                crit, _ = api(A.CRITIC_PROMPT.format(spec=spec, code=code), temperature=0.3)
                rec["critique"] = crit.strip()[:900]
                bad = why0.split("→")[0].strip()[:12]
                rec["critique_hit"] = bool(bad) and bad in crit
                rev, _ = local(A.REVISE_PROMPT.format(spec=spec, code=code, critique=crit), seed=seed + 13)
                ok2, why2 = A.run_tests(task, A.extract_code(rev))
                rec.update(ok=ok2, why=why2, first_why=why0)

        elif arm == "strong+strong":
            text, _ = api(A.GEN_PROMPT.format(spec=spec, sig=sig), temperature=0.7)
            code = A.extract_code(text)
            ok0, why0 = A.run_tests(task, code)
            if ok0:
                rec.update(ok=True)
            else:
                crit, _ = api(A.CRITIC_PROMPT.format(spec=spec, code=code), temperature=0.3)
                rec["critique"] = crit.strip()[:900]
                bad = why0.split("→")[0].strip()[:12]
                rec["critique_hit"] = bool(bad) and bad in crit
                rev, _ = api(A.REVISE_PROMPT.format(spec=spec, code=code, critique=crit), temperature=0.3)
                ok2, why2 = A.run_tests(task, A.extract_code(rev))
                rec.update(ok=ok2, why=why2, first_why=why0)
        rec["seconds"] = round(time.time() - t0, 1)
    except Exception as e:
        rec["why"] = f"{type(e).__name__}: {e}"
        rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="strong_solo,weak+strong")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--tasks", type=int, default=8)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    if not KEY:
        raise SystemExit("缺少 QWENCLOUD_API_KEY")
    arms = [a for a in args.arms.split(",") if a]
    tasks = A.TASKS[: args.tasks]
    jobs = [(t, a, r) for a in arms for t in tasks for r in range(args.reps)]
    open(OUT, "w", encoding="utf-8").close()

    results, lock = [], threading.Lock()

    def work(q):
        while True:
            with lock:
                if not q:
                    return
                t, a, r = q.pop(0)
            rec = one(t, a, r)
            with lock:
                results.append(rec)
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"[{len(results):>3}/{len(jobs)}] {rec['task']:<14} {a:<12} r{r} "
                      f"{'PASS' if rec['ok'] else 'FAIL'} {rec['seconds']:>5.1f}s {rec['why'][:50]}", flush=True)

    th = [threading.Thread(target=work, args=(jobs,), daemon=True) for _ in range(args.workers)]
    [t.start() for t in th]
    while any(t.is_alive() for t in th):
        time.sleep(2)

    lines = ["| 任务 | " + " | ".join(arms) + " |", "|---" * (len(arms) + 1) + "|"]
    for t in tasks:
        row = [t["name"]]
        for a in arms:
            rs = [r for r in results if r["task"] == t["name"] and r["arm"] == a]
            row.append(f"{sum(r['ok'] for r in rs)}/{len(rs)}" if rs else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    for a in arms:
        rs = [r for r in results if r["arm"] == a]
        lines.append(f"- **{a}**：{sum(r['ok'] for r in rs)}/{len(rs)}，"
                     f"平均 {statistics.mean([r['seconds'] for r in rs]):.0f} 秒")
    lines.append(f"- 用量：输入 {_usage['in']} / 输出 {_usage['out']} tokens")
    md = "\n".join(lines)
    open(os.path.join(A.OUT_DIR, "frontier_table.md"), "w", encoding="utf-8").write(md + "\n")
    print("\n" + md)


if __name__ == "__main__":
    main()
