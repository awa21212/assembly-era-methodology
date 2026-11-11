"""SOP 对照实验：单 AI vs 双 AI 互殴（同生成器，不同批评者厂商）。

设计：
  A 组（单 AI）：0.5B/7B 生成器一次成型，不做任何反馈。
  B 组（双 AI）：同一生成器 → 另一家底座（shiro-soft）当红队 → 生成器按批评改一轮。
  裁判：确定性断言测试（无 LLM），只数通过数。

注意：生成器用本地 7B，天花板很低；这会压低两组成绩，
但也正因如此，两组的差值反映的是「批评是否带来可测增益」。
"""
import json
import re
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/generate"
GEN_MODEL = "qwen2.5:7b-instruct"
REV_MODEL = "shiro-soft"

BLUE_CARD = (
    "你是一个顶尖的 Python 工程师。只输出完整可运行的代码，放在一个 ```python 代码块里，"
    "不要解释、不要示例、不要省略号。函数签名必须与要求完全一致。"
)
RED_CARD = (
    "你是一个极度刻薄、绝不妥协的代码评审专家。只找真问题，每条给出：问题 / 为什么会错 / 具体输入。"
    "禁止夸奖，禁止说'整体不错'。最多 5 条，按严重程度排序。"
)


def ask(model, prompt, num_predict=900, timeout=180):
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")).get("response", "")


def extract_code(text):
    m = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    if m:
        return max(m, key=len)
    # 没有围栏就整段当代码（剥掉可能的解释行）
    lines = [l for l in text.splitlines() if not l.strip().startswith(("#", "Here", "This"))]
    return "\n".join(lines)


def run_once(spec, model=GEN_MODEL, red=False):
    t0 = time.time()
    raw = ask(model, f"{BLUE_CARD}\n\n【任务】\n{spec}")
    code_a = extract_code(raw)
    out = {"arm": "B" if red else "A", "code": code_a, "raw_len": len(raw), "sec": round(time.time() - t0, 1)}
    if red:
        crit = ask(REV_MODEL, f"{RED_CARD}\n\n【任务要求】\n{spec}\n\n【待审代码】\n{code_a}", num_predict=600)
        out["critique"] = crit
        raw2 = ask(model, f"{BLUE_CARD}\n\n【任务】\n{spec}\n\n【上一版代码】\n{code_a}\n\n"
                           f"【评审意见】\n{crit}\n\n请只修正确认存在的问题，输出完整修订版代码。")
        out["code"] = extract_code(raw2)
    out["sec"] = round(time.time() - t0, 1)
    return out
