"""
统一 LLM 客户端层 (llm_client)

把所有 LLM 调用的"跨切面能力"集中在这里, 所有 verifier 复用:
1. 重试: API 抖动自动重试 3 次 (指数退避), 不让单次失败拖垮评测
2. 可复现: 固定 seed + temperature=0 + 记录模型版本
3. 缓存: (prompt + model + seed) → 结果, 重复评测秒出且省钱
4. 鲁棒 JSON 解析: 容错 markdown 围栏 / 转义字符 / 截断
5. 超时: 单次调用超时保护

设计原则: 这是唯一的 LLM 入口, verifier 不直接碰 openai/anthropic SDK。
"""
import os
import re
import json
import time
import hashlib
from pathlib import Path
from typing import Optional


# ============================================================
# 配置
# ============================================================
DEFAULT_SEED = int(os.getenv("LLM_SEED", "42"))          # 固定 seed 求可复现
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))   # 单次超时(秒)
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))      # 重试次数
CACHE_DIR = Path(__file__).parent / ".llm_cache"          # 缓存目录
CACHE_ENABLED = os.getenv("LLM_CACHE", "1") == "1"        # 缓存开关


# ============================================================
# 调用统计 (评测后可查: 多少次命中缓存/重试/失败)
# ============================================================
class _Stats:
    def __init__(self):
        self.reset()
    def reset(self):
        self.calls = 0
        self.cache_hits = 0
        self.retries = 0
        self.failures = 0
        self.total_latency = 0.0
    def summary(self):
        return {
            "total_calls": self.calls,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": round(self.cache_hits / self.calls, 2) if self.calls else 0,
            "retries": self.retries,
            "failures": self.failures,
            "avg_latency_s": round(self.total_latency / max(self.calls - self.cache_hits, 1), 2),
        }

STATS = _Stats()


# ============================================================
# 缓存
# ============================================================
def _cache_key(prompt: str, model: str, seed: int, system: str = "") -> str:
    raw = f"{model}|{seed}|{system}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_get(key: str) -> Optional[str]:
    if not CACHE_ENABLED:
        return None
    f = CACHE_DIR / f"{key}.txt"
    if f.exists():
        try:
            return f.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def _cache_set(key: str, value: str):
    if not CACHE_ENABLED:
        return
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        (CACHE_DIR / f"{key}.txt").write_text(value, encoding="utf-8")
    except Exception:
        pass  # 缓存失败不影响主流程


# ============================================================
# 鲁棒 JSON 解析 (容错 markdown / 转义 / 截断)
# ============================================================
def parse_json_robust(text: str) -> dict:
    """从可能含噪声的 LLM 输出里提取 JSON dict

    容错:
    - markdown 围栏 ```json ... ```
    - 前后多余文字
    - 字符串内的转义引号
    - 尾部截断 (尽量补全)
    """
    if not text or not text.strip():
        raise ValueError("LLM 返回空文本")

    # 去 markdown 围栏
    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    t = re.sub(r"\s*```$", "", t)

    start = t.find("{")
    if start == -1:
        raise ValueError(f"LLM 输出无 JSON 起始: {text[:200]}")

    # 正确的括号匹配 (处理字符串内转义)
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(t)):
        ch = t[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end != -1:
        candidate = t[start:end]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass  # 落到下面的兜底

    # 兜底 1: 直接尝试从 start 到结尾
    try:
        return json.loads(t[start:])
    except json.JSONDecodeError:
        pass

    # 兜底 2: 截断的 JSON, 尝试补齐缺失的 }
    candidate = t[start:end] if end != -1 else t[start:]
    for _ in range(depth if depth > 0 else 3):
        candidate += "}"
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError(f"JSON 解析失败: {text[:200]}")


# ============================================================
# 核心: 带重试 + 缓存 + seed 的 LLM 调用
# ============================================================
def call_llm(
    prompt: str,
    model: str,
    system: str = "你是精确的判定助手. 只输出 JSON, 不要任何额外文字.",
    max_tokens: int = 1000,
    seed: int = None,
    return_raw: bool = False,
):
    """统一 LLM 调用入口 (带重试/缓存/seed)

    Args:
        prompt: 用户提示
        model: 模型名 (claude* / deepseek* / gpt*)
        system: system prompt
        max_tokens: 最大输出
        seed: 随机种子 (默认 DEFAULT_SEED, 求可复现)
        return_raw: True 返回原始文本, False 返回解析后的 dict

    Returns:
        dict (默认) 或 str (return_raw=True)

    Raises:
        RuntimeError: 重试耗尽仍失败
    """
    if seed is None:
        seed = DEFAULT_SEED

    STATS.calls += 1

    # 查缓存
    key = _cache_key(prompt, model, seed, system)
    cached = _cache_get(key)
    if cached is not None:
        STATS.cache_hits += 1
        return cached if return_raw else parse_json_robust(cached)

    # 真实调用 (带重试)
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            text = _dispatch_call(prompt, model, system, max_tokens, seed)
            STATS.total_latency += time.time() - t0

            # 验证能解析 (除非 return_raw)
            if not return_raw:
                parse_json_robust(text)  # 解析失败会抛异常, 触发重试

            _cache_set(key, text)
            return text if return_raw else parse_json_robust(text)

        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                STATS.retries += 1
                wait = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait)
            continue

    STATS.failures += 1
    raise RuntimeError(f"LLM 调用失败 (重试 {MAX_RETRIES} 次): {last_err}")


def _dispatch_call(prompt: str, model: str, system: str, max_tokens: int, seed: int) -> str:
    """根据模型分发到具体 SDK, 返回原始文本"""
    if model.startswith("claude"):
        return _call_anthropic(prompt, model, system, max_tokens)
    elif model.startswith("deepseek"):
        return _call_openai_compat(prompt, model, system, max_tokens, seed,
                                   base_url="https://api.deepseek.com", api_key_env="DEEPSEEK_API_KEY")
    elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4"):
        return _call_openai_compat(prompt, model, system, max_tokens, seed,
                                   base_url=None, api_key_env="OPENAI_API_KEY")
    else:
        raise ValueError(f"不支持的模型: {model}")


def _call_anthropic(prompt: str, model: str, system: str, max_tokens: int) -> str:
    from anthropic import Anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("需要 ANTHROPIC_API_KEY 环境变量")
    client = Anthropic(api_key=api_key, timeout=DEFAULT_TIMEOUT)
    actual_model = "claude-opus-4-7" if "4-7" in model else model
    # Anthropic 暂不支持 seed; temperature=0 已最大化可复现
    resp = client.messages.create(
        model=actual_model, max_tokens=max_tokens, temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _call_openai_compat(prompt: str, model: str, system: str, max_tokens: int, seed: int,
                        base_url, api_key_env) -> str:
    from openai import OpenAI
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"需要 {api_key_env} 环境变量")
    kwargs = {"api_key": api_key, "timeout": DEFAULT_TIMEOUT}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)

    create_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }

    is_reasoning = model.startswith(("gpt-5", "o1", "o3", "o4"))
    if is_reasoning:
        create_kwargs["max_completion_tokens"] = max(max_tokens, 1500)
        # 推理模型不支持自定义 temperature / seed
    else:
        create_kwargs["max_tokens"] = max_tokens
        create_kwargs["temperature"] = 0.0
        create_kwargs["seed"] = seed  # 关键: 固定 seed 求可复现

    if model.startswith("deepseek"):
        thinking_on = os.getenv("VERIFIER_LLM_THINKING", "0") == "1"
        create_kwargs["extra_body"] = {
            "thinking": {"type": "enabled" if thinking_on else "disabled"}
        }

    resp = client.chat.completions.create(**create_kwargs)
    return resp.choices[0].message.content


# ============================================================
# 自测
# ============================================================
if __name__ == "__main__":
    print("=== llm_client 自测 ===\n")

    # 测 JSON 鲁棒解析 (不需要 API)
    cases = [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('这是结果: {"verdict": "pass", "reason": "ok"} 完毕', {"verdict": "pass", "reason": "ok"}),
        ('{"msg": "他说\\"你好\\""}', {"msg": '他说"你好"'}),  # 转义引号
        ('{"a": 1, "b": {"c": 2}}', {"a": 1, "b": {"c": 2}}),  # 嵌套
        ('{"a": 1', {"a": 1}),  # 截断, 兜底补 }
    ]
    passed = 0
    for inp, expected in cases:
        try:
            got = parse_json_robust(inp)
            ok = got == expected
            print(f"  {'✓' if ok else '✗'} {inp[:40]:42s} → {got}")
            if ok:
                passed += 1
        except Exception as e:
            print(f"  ✗ {inp[:40]:42s} → 异常 {e}")
    print(f"\nJSON 鲁棒解析: {passed}/{len(cases)} 通过")

    # 测缓存键稳定性
    k1 = _cache_key("p", "m", 42, "s")
    k2 = _cache_key("p", "m", 42, "s")
    k3 = _cache_key("p", "m", 43, "s")
    print(f"\n缓存键: 相同输入同键={k1==k2} (应 True), 不同seed异键={k1!=k3} (应 True)")

    print(f"\n配置: seed={DEFAULT_SEED}, timeout={DEFAULT_TIMEOUT}s, retries={MAX_RETRIES}, cache={CACHE_ENABLED}")
    print("✅ 自测完成" if passed == len(cases) and k1 == k2 and k1 != k3 else "❌ 有失败")