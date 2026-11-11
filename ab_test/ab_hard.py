"""ab_hard.py — 加难：GLM-5.3 强对强，三个硬任务

任务（比之前那批难一档）：
  parse_csv     引号包裹、内嵌逗号、双引号转义
  eval_expr     四则运算 + 括号 + 一元负号 + 除零返回 None
  topo_sort     拓扑排序，可为任意合法顺序；有环返回 None

臂：
  glm_solo      GLM-5.3 一次成型
  glm_critic    GLM-5.3 写 → GLM-5.3 审 → GLM-5.3 改
  qwen_solo     qwen3.8-max 一次成型（横向对照）

用法：
  python ab_hard.py --reps 2 --arms glm_solo,glm_critic,qwen_solo
"""

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.request

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
BASE = "https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions"
KEY = os.environ.get("QWENCLOUD_API_KEY", "").strip()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GEN_PROMPT = """写一个 Python 函数，满足下面的需求。只输出代码，不要解释。

需求：{spec}

以上输入全部通过**函数参数**传入，不接受标准输入。函数签名必须严格写成：

{sig}

禁止 input()、print()、sys.stdin，禁止写 main() 或 if __name__ == "__main__"。
"""

CRITIC_PROMPT = """你是以抓 bug 为乐的代码审查者。不要客套，不要谈风格。

需求：{spec}

待审代码：
```python
{code}
```

只做一件事：列出它在真实输入下会出错的具体情况，每条附一个**可执行的反例输入**。
不要重写代码。找不到就只回复：找不到。
"""

REVISE_PROMPT = """修正下面代码里的所有真实缺陷，输出最终完整代码。只输出代码。

需求：{spec}

原代码：
```python
{code}
```

审查意见：
{critique}
"""


# ---------- 三个硬任务 ----------

def check_parse_csv(case, got):
    exp = case["exp"]
    return got == exp, f"{case['input'][:24]!r} → {got!r}"


def check_eval(case, got):
    exp = case["exp"]
    if exp is None:
        return got is None, f"{case['input']!r} → {got!r}，期望 None"
    if not isinstance(got, (int, float)):
        return False, f"{case['input']!r} → {got!r}（不是数字）"
    return abs(got - exp) < 1e-6, f"{case['input']!r} → {got!r}，期望 {exp}"


def check_topo(case, got):
    n, edges = case["n"], case["edges"]
    if case.get("cycle"):
        return got is None, f"有环却返回 {got!r}"
    if not isinstance(got, (list, tuple)) or sorted(got) != list(range(n)):
        return False, f"不是 0..{n-1} 的排列：{got!r}"
    pos = {v: i for i, v in enumerate(got)}
    for u, v in edges:
        if pos[u] > pos[v]:
            return False, f"边 {u}->{v} 顺序反了：{got!r}"
    return True, ""


TASKS = [
    dict(
        name="parse_csv",
        sig="def solve(text: str):",
        spec='''把类 CSV 文本解析成 list[list[str]]。规则：
1) 字段用逗号分隔，行用 \\n 分隔；
2) 字段可以被双引号包裹，包裹后其中可以包含逗号和换行；
3) 引号内的两个连续双引号 "" 表示一个字面双引号；
4) 未被引号包裹的字段，两侧空格要去掉；
5) 空行跳过；空字符串输入返回 []。''',
        cases=[
            dict(input='a,b\nc,d', exp=[["a", "b"], ["c", "d"]]),
            dict(input='a,b\n"x,1",2', exp=[["a", "b"], ["x,1", "2"]]),
            dict(input='"he said ""hi""",3', exp=[['he said "hi"', "3"]]),
            dict(input='a, b \n\nc,d', exp=[["a", "b"], ["c", "d"]]),
            dict(input='', exp=[]),
        ],
        check=check_parse_csv,
    ),
    dict(
        name="eval_expr",
        sig="def solve(s: str):",
        spec='''计算算术表达式，返回 float。支持 + - * /、括号、一元负号、小数、空格。
除零返回 None；任何非法表达式（括号不配对、字符非法、空串）返回 None。
不要用 eval/exec。''',
        cases=[
            dict(input="1+2*3", exp=7.0),
            dict(input="(1+2)*3", exp=9.0),
            dict(input="-3+5", exp=2.0),
            dict(input="10/4", exp=2.5),
            dict(input="2*(3+4)-5/2", exp=11.5),
            dict(input="1/0", exp=None),
            dict(input="(1+2", exp=None),
            dict(input="", exp=None),
        ],
        check=check_eval,
    ),
    dict(
        name="topo_sort",
        sig="def solve(n: int, edges: list):",
        spec='''拓扑排序。n 个节点编号 0..n-1，edges 是 [(u,v)] 表示 u 必须先于 v。
返回任意一个合法的拓扑序列 list；若存在环则返回 None。
重复边要忽略，自环视为环。''',
        cases=[
            dict(n=4, edges=[(0, 1), (1, 2), (2, 3)], cycle=False,
                 exp=["0 1 2 3 的任意拓扑序"]),
            dict(n=3, edges=[(0, 1), (1, 2), (2, 0)], cycle=True, exp=None),
            dict(n=2, edges=[(0, 0)], cycle=True, exp=None),
            dict(n=3, edges=[], cycle=False, exp="任意顺序"),
            dict(n=3, edges=[(0, 1), (0, 1), (1, 2)], cycle=False, exp="任意"),
        ],
        check=check_topo,
    ),
]


def api(prompt, model, temperature=0.5, max_tokens=8000, timeout=420, effort="low"):
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
    return data["choices"][0]["message"]["content"] or "", time.time() - t0


FENCE_MARK = "```"


def extract_code(text):
    parts = text.split(FENCE_MARK)
    if len(parts) >= 3:
        block = parts[1]
        if block.lstrip().startswith("python"):
            block = block.lstrip()[6:]
        return block.strip()
    i = text.find("def solve")
    return text[i:].strip() if i >= 0 else text.strip()


def run_task(task, code):
    env = {}
    try:
        exec(compile(code, "<cand>", "exec"), env)
        fn = env.get("solve")
        if fn is None:
            return False, "没有 solve 函数"
    except Exception as e:
        return False, f"编译失败 {type(e).__name__}: {e}"

    for case in task["cases"]:
        args = [case[k] for k in ("input",) if k in case] or [case["n"], case["edges"]]
        try:
            got = fn(*args)
        except Exception as e:
            return False, f"{args!r} 抛异常 {type(e).__name__}: {e}"
        ok, why = task["check"](case, got)
        if not ok:
            return False, why
    return True, ""


def one(task, arm, rep, model_glm="glm-5.3", model_qwen="qwen3.8-max"):
    rec = dict(task=task["name"], arm=arm, rep=rep, ok=False, why="", seconds=0.0)
    t0 = time.time()
    try:
        gen_model = model_qwen if arm.startswith("qwen") else model_glm
        text, _ = api(GEN_PROMPT.format(spec=task["spec"], sig=task["sig"]), gen_model, temperature=0.5)
        code = extract_code(text)
        ok, why = run_task(task, code)
        rec.update(ok=ok, why=why)

        if arm.endswith("critic") and not ok:
            crit, _ = api(CRITIC_PROMPT.format(spec=task["spec"], code=code), model_glm, temperature=0.2)
            rec["critique"] = crit.strip()[:900]
            rev, _ = api(REVISE_PROMPT.format(spec=task["spec"], code=code, critique=crit),
                         model_glm, temperature=0.2)
            ok2, why2 = run_task(task, extract_code(rev))
            rec.update(ok=ok2, why=why2, first_why=why, revised=True)
        rec["seconds"] = round(time.time() - t0, 1)
    except Exception as e:
        rec["why"] = f"{type(e).__name__}: {e}"
        rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="glm_solo,glm_critic,qwen_solo")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    if not KEY:
        raise SystemExit("缺少 QWENCLOUD_API_KEY")
    arms = [a for a in args.arms.split(",") if a]
    jobs = [(t, a, r) for a in arms for t in TASKS for r in range(args.reps)]
    path = os.path.join(OUT_DIR, "hard_results.jsonl")
    open(path, "w", encoding="utf-8").close()
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
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"[{len(results):>2}/{len(jobs)}] {rec['task']:<12} {a:<11} r{r} "
                      f"{'PASS' if rec['ok'] else 'FAIL'} {rec['seconds']:>5.1f}s {rec['why'][:55]}", flush=True)

    th = [threading.Thread(target=work, args=(jobs,), daemon=True) for _ in range(args.workers)]
    [t.start() for t in th]
    while any(t.is_alive() for t in th):
        time.sleep(2)

    lines = ["| 任务 | " + " | ".join(arms) + " |", "|---" * (len(arms) + 1) + "|"]
    for t in TASKS:
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
    md = "\n".join(lines)
    open(os.path.join(OUT_DIR, "hard_table.md"), "w", encoding="utf-8").write(md + "\n")
    print("\n" + md)


if __name__ == "__main__":
    main()

