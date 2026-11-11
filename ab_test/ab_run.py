"""跑对照实验：4 个任务 × 2 组 × 确定性断言。结果写 out/ab_results.json 与 out/ab_table.md。"""
import io
import json
import os
import time
import traceback

import ab_common as C

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
TMP = os.path.join(OUT, "tmp")
os.makedirs(TMP, exist_ok=True)

CSV_BOM = "\ufeffname,income\nA,100\nB,\nC,300\nD,N/A\nE,500\n"
CSV_PATH = os.path.join(TMP, "income.csv")
with io.open(CSV_PATH, "w", encoding="utf-8") as f:
    f.write(CSV_BOM)


# ---------- 任务与测试 ----------
def t_median(ns):
    f = ns["median_of_csv"]
    assert f(CSV_PATH, "income") == 300, "期望 300，得 %r" % (f(CSV_PATH, "income"),)
    empty = os.path.join(TMP, "empty.csv")
    with io.open(empty, "w", encoding="utf-8") as fh:
        fh.write("a\n")
    assert f(empty, "a") is None


def t_duration(ns):
    f = ns["parse_duration"]
    assert f("45s") == 45, f("45s -> {f('45s')}")
    assert f("1h30m") == 5400, f("1h30m -> {f('1h30m')}")
    assert f("2d") == 172800
    for bad in ["", "abc", "10x"]:
        try:
            f(bad)
            raise AssertionError(f"应抛 ValueError: {bad!r}")
        except ValueError:
            pass


def t_topwords(ns):
    f = ns["top_words"]
    r = f("Hello, world! hello HELLO world.  bye", 3)
    assert r[0] == ("hello", 3), r
    assert r[1] == ("world", 2), r
    assert r[2] == ("bye", 1), r
    assert f("", 5) == []


def t_chunk(ns):
    f = ns["chunk"]
    assert f([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert f([], 3) == []
    try:
        f([1], 0)
        raise AssertionError("size<=0 应抛 ValueError")
    except ValueError:
        pass


TASKS = [
    ("median_of_csv", """写一个函数 median_of_csv(path: str, column: str) -> float | None。
读取 CSV（utf-8-sig，可能带 BOM），返回该列的中位数（float）。
要求：
- 空字符串、仅空白、"N/A"、无法转 float 的值一律跳过；
- 没有任何有效数字时返回 None；
- 列不存在时抛 ValueError。""", [t_median]),
    ("parse_duration", """写一个函数 parse_duration(s: str) -> int，把时长字符串转成秒。
支持单位 d/h/m/s 且可组合，例如 "45s"=45, "1h30m"=5400, "2d"=172800。
要求：允许空格；非法输入（空串、未知单位、纯字母）抛 ValueError。""", [t_duration]),
    ("top_words", """写一个函数 top_words(text: str, n: int) -> list[tuple[str, int]]。
统计词频，忽略大小写，去掉标点，按次数降序；次数相同按单词字母升序。
返回前 n 个 (word, count)。空文本返回 []。""", [t_topwords]),
    ("chunk", """写一个函数 chunk(seq: list, size: int) -> list[list]。
把序列切成若干段，最后一段可以不足 size。size 小于等于 0 时抛 ValueError。空列表返回 []。""", [t_chunk]),
]


def score(code, tests):
    ns = {}
    err = None
    try:
        exec(compile(code, "<cand>", "exec"), ns)
    except Exception as e:
        err = f"语法/导入错误: {e.__class__.__name__}: {e}"
        return 0, len(tests), err
    passed = 0
    msgs = []
    for t in tests:
        try:
            t(ns)
            passed += 1
        except Exception as e:
            msgs.append(f"{e.__class__.__name__}: {e}")
    return passed, len(tests), "; ".join(msgs)[:400]


def main():
    rows = []
    for name, spec, tests in TASKS:
        for red in (False, True):
            tag = "B 双AI" if red else "A 单AI"
            t0 = time.time()
            try:
                res = C.run_once(spec, red=red)
            except Exception as e:
                print(f"[{name}][{tag}] 调用失败: {e}")
                traceback.print_exc()
                rows.append({"task": name, "arm": tag, "pass": 0, "total": len(tests),
                             "err": f"call failed: {e}", "sec": round(time.time() - t0, 1)})
                continue
            p, tot, err = score(res["code"], tests)
            rows.append({"task": name, "arm": tag, "pass": p, "total": tot,
                         "err": err, "sec": res["sec"], "code": res["code"],
                         "critique": res.get("critique", "")})
            print(f"[{name}][{tag}] {p}/{tot}  {res['sec']}s  {err[:120] if err else ''}")
            with io.open(os.path.join(OUT, f"{name}_{'B' if red else 'A'}.py"), "w", encoding="utf-8") as f:
                f.write(res["code"])

    with io.open(os.path.join(OUT, "ab_results.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    lines = ["| 任务 | A 单AI | B 双AI | 差值 |", "|---|---|---|---|"]
    for name, _, tests in TASKS:
        a = next((r for r in rows if r["task"] == name and r["arm"].startswith("A")), None)
        b = next((r for r in rows if r["task"] == name and r["arm"].startswith("B")), None)
        sa = f"{a['pass']}/{a['total']}" if a else "-"
        sb = f"{b['pass']}/{b['total']}" if b else "-"
        da = (b["pass"] - a["pass"]) if a and b else None
        lines.append(f"| {name} | {sa} | {sb} | {da:+d} |" if da is not None else f"| {name} | {sa} | {sb} | - |")
    ta = sum(r["pass"] for r in rows if r["arm"].startswith("A"))
    tb = sum(r["pass"] for r in rows if r["arm"].startswith("B"))
    tt = sum(r["total"] for r in rows if r["arm"].startswith("A"))
    lines.append(f"| **合计** | **{ta}/{tt}** | **{tb}/{tt}** | **{tb-ta:+d}** |")
    with io.open(os.path.join(OUT, "ab_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
