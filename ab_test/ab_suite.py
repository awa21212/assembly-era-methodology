"""ab_suite.py — 双 AI 互殴 vs 单 AI 的对照实验（扩展版）

设计：
  - 8 个代码任务，每个都有确定性断言（不是打分、不是感觉）
  - 2 个实验臂：solo（一次成型） / critic（弱红队审 → 生成器改）
  - 3 次重复，temperature=0.7（0 就测不出方差）
  - 记录：是否全通过、耗时、红队是否点出关键用例

用法：
  python ab_suite.py --reps 3 --workers 2
  python ab_suite.py --reps 1 --tasks 2 --arms solo     # 冒烟
"""

import argparse
import json
import os
import re
import statistics
import sys
import threading
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/generate"
GEN_MODEL = "qwen2.5:7b-instruct"
CRITIC_MODEL = "shiro-soft:v2"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ask(model, prompt, seed=0, temperature=0.7, timeout=180):
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "seed": seed, "num_predict": 700},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data.get("response", ""), time.time() - t0


FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.S)


def extract_code(text):
    m = FENCE.search(text)
    if m:
        return m.group(1).strip()
    # 没有围栏：从第一个 def/import 开始
    i = min([p for p in (text.find("def "), text.find("import ")) if p >= 0], default=-1)
    return text[i:].strip() if i >= 0 else text.strip()


GEN_PROMPT = """写一个 Python 函数，满足下面的需求。只输出代码，不要解释。

需求：{spec}

以上输入全部通过**函数参数**传入，不接受标准输入。函数签名必须严格写成：

{sig}

禁止 input()、print()、sys.stdin，禁止写 main() 或 if __name__。
"""

CRITIC_PROMPT = """你是一位极度刻薄、以抓 bug 为乐的代码审查者。不要鼓励，不要客套。

需求：{spec}

待审代码：
```python
{code}
```

请只做一件事：找出上面代码在真实输入下会出错的具体情况，每条给出 1 个可执行的反例输入（例如 solve("1h30m") 返回 90 而不是 0）。
不要重写代码，不要谈风格、命名、注释、性能。
如果确实找不到会出错的情况，只回复：找不到。
"""

REVISE_PROMPT = """这是你的代码和审查意见。请修正所有真实缺陷，输出最终代码。

需求：{spec}

原代码：
```python
{code}
```

审查意见：
{critique}

只输出修正后的完整代码。
"""


# ---------------- 任务 ----------------

def _t_median(text):
    try:
        rows = [r.split(",") for r in text.strip().splitlines()]
        vals = [float(r[1]) for r in rows]
        return sorted(vals)[len(vals) // 2] if len(vals) % 2 else (
            sorted(vals)[len(vals) // 2 - 1] + sorted(vals)[len(vals) // 2]) / 2
    except Exception:
        return "<error>"


TASKS = [
    dict(
        name="median_of_csv", sig="def solve(text: str):",
        spec='输入多行文本，每行形如 "name,value"（value 为数字）。返回所有 value 的中位数；偶数个取中间两个的平均值；空输入返回 None。',
        tests=[('a,1\nb,3\nc,2', 2.0), ('a,1\nb,2\nc,3\nd,4', 2.5), ('', None)],
    ),
    dict(
        name="parse_duration", sig="def solve(s: str):",
        spec='把时长字符串转成总秒数。支持 h/m/s 任意组合，例如 "1h30m" → 5400，"45s" → 45，"2h" → 7200，"1h30m20s" → 5420。非法输入返回 None。',
        tests=[("1h30m", 5400), ("45s", 45), ("2h", 7200), ("1h30m20s", 5420), ("abc", None)],
    ),
    dict(
        name="top_words", sig="def solve(text: str, k: int):",
        spec='输入一段英文文本，返回出现次数最多的前 k 个单词（小写、去掉标点、按次数降序；次数相同按字母升序）。返回 list，元素是单词。',
        tests=[("the cat the dog the", 2, ["the", "cat"]), ("b a b a c", 1, ["a"])],
    ),
    dict(
        name="chunk", sig="def solve(seq: list, n: int):",
        spec='把列表按固定长度切成若干块，最后一块可以不足。返回 list[list]。n<=0 时返回空列表。',
        tests=[([1, 2, 3, 4, 5], 2, [[1, 2], [3, 4], [5]]), ([], 2, []), ([1, 2], 0, [])],
    ),
    dict(
        name="merge_intervals", sig="def solve(intervals: list):",
        spec='输入区间列表 [(start,end), ...]，合并所有重叠或相邻的区间，按 start 升序返回。若 start>end 视为非法，直接跳过该区间。',
        tests=[([(1, 3), (2, 6), (8, 10)], [(1, 6), (8, 10)]),
               ([(5, 3), (1, 2)], [(1, 2)]),
               ([], [])],
    ),
    dict(
        name="slugify", sig="def solve(title: str):",
        spec='把标题转成 URL slug：转小写、非字母数字换成单连字符、去掉首尾连字符、连续连字符合并成一个。中文等非 ASCII 字符直接丢弃。',
        tests=[("Hello, World!", "hello-world"), ("  --A  B--  ", "a-b"), ("你好 World 2026", "world-2026")],
    ),
    dict(
        name="rle", sig="def solve(s: str):",
        spec='对字符串做游程编码，返回 "字符+次数" 拼接的字符串。例如 "aaab" → "a3b1"，"abc" → "a1b1c1"，空串返回 ""。',
        tests=[("aaab", "a3b1"), ("abc", "a1b1c1"), ("", "")],
    ),
    dict(
        name="safe_div", sig="def solve(a, b):",
        spec='返回 a/b 四舍五入到 2 位小数；b 为 0 时返回 None；a、b 可以是字符串数字，转换失败返回 None。',
        tests=[(1, 3, 0.33), ("10", "4", 2.5), (5, 0, None), ("x", 2, None)],
    ),
]


def _norm(v):
    """把 tuple / list 统一成 list，避免 [(1,2)] 与 [[1,2]] 的假失败。"""
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def run_tests(task, code):
    """执行候选代码并在断言上跑，返回 (是否全过, 失败说明)。"""
    env = {}
    try:
        exec(compile(code, "<cand>", "exec"), env)
        fn = env.get("solve")
        if fn is None:
            return False, "没有 solve 函数"
    except Exception as e:
        return False, f"编译失败: {type(e).__name__}: {e}"

    for case in task["tests"]:
        args, expect = case[:-1], case[-1]
        try:
            got = fn(*args)
        except Exception as e:
            return False, f"{args!r} 抛异常 {type(e).__name__}"
        if _norm(got) != _norm(expect):
            return False, f"{args!r} → {got!r}，期望 {expect!r}"
        elif False:
            return False, f"{args!r} → {got!r}，期望 {expect!r}"
    return True, ""


def one_run(task, arm, rep):
    seed = rep * 1000 + hash(task["name"]) % 997
    prompt = GEN_PROMPT.format(spec=task["spec"], sig=task["sig"])
    t_all = 0.0
    try:
        text, dt = ask(GEN_MODEL, prompt, seed=seed)
        t_all += dt
        code = extract_code(text)
        ok, why = run_tests(task, code)

        rec = dict(task=task["name"], arm=arm, rep=rep, ok=ok, why=why,
                   seconds=round(t_all, 1), critique="", critique_hit=False)

        if arm == "critic" and not ok:
            crit, dt2 = ask(CRITIC_MODEL, CRITIC_PROMPT.format(spec=task["spec"], code=code), seed=seed + 7)
            t_all += dt2
            rec["critique"] = crit.strip()[:800]
            # 红队是否点出"关键失败用例"：拿真实失败输入的首个参数做字符串匹配
            bad = why.split("→")[0].strip()
            rec["critique_hit"] = any(tok and tok in crit for tok in [bad[:12]])
            rev, dt3 = ask(GEN_MODEL, REVISE_PROMPT.format(spec=task["spec"], code=code, critique=crit),
                           seed=seed + 13)
            t_all += dt3
            code2 = extract_code(rev)
            ok2, why2 = run_tests(task, code2)
            rec.update(ok=ok2, why=why2, seconds=round(t_all, 1), revised=True)
        return rec
    except Exception as e:
        return dict(task=task["name"], arm=arm, rep=rep, ok=False,
                    why=f"运行异常 {type(e).__name__}: {e}", seconds=round(t_all, 1),
                    critique="", critique_hit=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--tasks", type=int, default=len(TASKS))
    ap.add_argument("--arms", default="solo,critic")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", default="", help="只跑某个任务名")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    tasks = TASKS[: args.tasks]
    if args.only:
        tasks = [t for t in tasks if t["name"] in args.only.split(",")]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    jobs = [(t, a, r) for t in tasks for a in arms for r in range(args.reps)]

    results, lock = [], threading.Lock()
    path = os.path.join(OUT_DIR, "suite_results.jsonl")
    open(path, "w", encoding="utf-8").close()

    def work(q):
        while True:
            with lock:
                if not q:
                    return
                task, arm, rep = q.pop(0)
            rec = one_run(task, arm, rep)
            with lock:
                results.append(rec)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                mark = "PASS" if rec["ok"] else "FAIL"
                print(f"[{len(results):>3}/{len(jobs)}] {rec['task']:<14} {arm:<6} r{rep} "
                      f"{mark} {rec['seconds']:>5.1f}s  {rec['why'][:60]}", flush=True)

    threads = [threading.Thread(target=work, args=(jobs,), daemon=True) for _ in range(args.workers)]
    [t.start() for t in threads]
    while any(t.is_alive() for t in threads):
        time.sleep(2)

    # 汇总
    lines = ["| 任务 | solo 通过/次数 | solo 平均秒 | critic 通过/次数 | critic 平均秒 | 红队点中失败用例 |",
             "|---|---|---|---|---|---|"]
    for t in tasks:
        row = [t["name"]]
        for arm in ("solo", "critic"):
            rs = [r for r in results if r["task"] == t["name"] and r["arm"] == arm]
            row.append(f"{sum(r['ok'] for r in rs)}/{len(rs)}" if rs else "-")
            row.append(f"{statistics.mean([r['seconds'] for r in rs]):.0f}" if rs else "-")
        hits = [r for r in results if r["task"] == t["name"] and r["arm"] == "critic" and r.get("critique_hit")]
        row.append(f"{len(hits)}" if hits else "0")
        lines.append("| " + " | ".join(row) + " |")

    tot = {a: [r for r in results if r["arm"] == a] for a in arms}
    summary = ["# 双 AI 对照实验：solo vs critic", ""]
    summary += lines
    summary.append("")
    for a in arms:
        rs = tot.get(a, [])
        if rs:
            summary.append(f"- **{a}**：全通过 {sum(r['ok'] for r in rs)}/{len(rs)}，"
                           f"平均 {statistics.mean([r['seconds'] for r in rs]):.0f} 秒/次")
    md = "\n".join(summary)
    with open(os.path.join(OUT_DIR, "suite_table.md"), "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print("\n" + md)


if __name__ == "__main__":
    main()
