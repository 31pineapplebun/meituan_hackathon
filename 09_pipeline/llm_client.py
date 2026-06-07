"""
统一 LLM 客户端层 (llm_client)

集中处理:
1) 全局并发限流
2) 可重试错误分类 + 指数退避 + 抖动
3) 缓存与可复现
4) 鲁棒 JSON 解析
5) 结构化统计 (含 p95/p99 与错误分布)
"""
import hashlib
import json
import os
import random
import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ============================================================
# 配置
# ============================================================
DEFAULT_SEED = int(os.getenv("LLM_SEED", "42"))
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
MAX_INFLIGHT = int(os.getenv("LLM_MAX_INFLIGHT", "6"))
CACHE_DIR = Path(__file__).parent / ".llm_cache"
CACHE_ENABLED = os.getenv("LLM_CACHE", "1") == "1"

_INFLIGHT_SEMAPHORE = threading.BoundedSemaphore(MAX_INFLIGHT)
_CACHE_LOCK = threading.Lock()


def _percentile(values: list, p: float) -> float:
    if not values:
        return 0.0
    arr = sorted(values)
    if len(arr) == 1:
        return arr[0]
    idx = (len(arr) - 1) * p
    low = int(idx)
    high = min(low + 1, len(arr) - 1)
    frac = idx - low
    return arr[low] * (1 - frac) + arr[high] * frac


# ============================================================
# 调用统计
# ============================================================
class _Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.calls = 0
            self.cache_hits = 0
            self.retries = 0
            self.failures = 0
            self.retryable_failures = 0
            self.non_retryable_failures = 0
            self.total_latency = 0.0
            self.latencies = []
            self.error_breakdown = defaultdict(int)

    def record_call(self):
        with self._lock:
            self.calls += 1

    def record_cache_hit(self):
        with self._lock:
            self.cache_hits += 1

    def record_retry(self):
        with self._lock:
            self.retries += 1

    def record_latency(self, latency_s: float):
        with self._lock:
            self.total_latency += latency_s
            self.latencies.append(latency_s)

    def record_failure(self, retryable: bool, err_code: str):
        with self._lock:
            self.failures += 1
            if retryable:
                self.retryable_failures += 1
            else:
                self.non_retryable_failures += 1
            self.error_breakdown[err_code] += 1

    def summary(self):
        with self._lock:
            real_calls = max(self.calls - self.cache_hits, 0)
            latencies = list(self.latencies)
            breakdown = dict(self.error_breakdown)
            return {
                "total_calls": self.calls,
                "cache_hits": self.cache_hits,
                "cache_hit_rate": round(self.cache_hits / self.calls, 3) if self.calls else 0.0,
                "real_calls": real_calls,
                "retries": self.retries,
                "failures": self.failures,
                "retryable_failures": self.retryable_failures,
                "non_retryable_failures": self.non_retryable_failures,
                "avg_latency_s": round(self.total_latency / max(real_calls, 1), 3),
                "p95_latency_s": round(_percentile(latencies, 0.95), 3),
                "p99_latency_s": round(_percentile(latencies, 0.99), 3),
                "error_breakdown": breakdown,
                "max_inflight": MAX_INFLIGHT,
            }


STATS = _Stats()


def reset_stats():
    STATS.reset()


def get_stats_summary() -> dict:
    return STATS.summary()


# ============================================================
# 缓存
# ============================================================
def _cache_key(prompt: str, model: str, seed: int, system: str = "") -> str:
    raw = f"{model}|{seed}|{system}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_get(key: str) -> Optional[str]:
    if not CACHE_ENABLED:
        return None
    cache_file = CACHE_DIR / f"{key}.txt"
    if not cache_file.exists():
        return None
    try:
        return cache_file.read_text(encoding="utf-8")
    except Exception:
        return None


def _cache_set(key: str, value: str):
    if not CACHE_ENABLED:
        return
    try:
        with _CACHE_LOCK:
            CACHE_DIR.mkdir(exist_ok=True)
            cache_file = CACHE_DIR / f"{key}.txt"
            temp_file = CACHE_DIR / f"{key}.tmp"
            temp_file.write_text(value, encoding="utf-8")
            temp_file.replace(cache_file)
    except Exception:
        # 缓存写失败不影响主流程
        pass


# ============================================================
# 错误分类与重试策略
# ============================================================
def _extract_retry_after_seconds(err: Exception) -> Optional[float]:
    msg = str(err).lower()
    m = re.search(r"retry[-_ ]after[:= ]+([0-9.]+)", msg)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _extract_error_code(err: Exception) -> str:
    # 先按【异常类型】判 parse_error: parse_json_robust 抛的 ValueError 会把 LLM 原文拼进
    # message, 其中可能含 "400"/"401" 等数字串; 若先做 HTTP 码子串匹配会把可重试的坏 JSON
    # 误判成不可重试码、放弃 re-roll 并污染错误统计。故类型判定必须在子串匹配之前。
    if isinstance(err, (json.JSONDecodeError, ValueError)):
        return "parse_error"
    text = str(err).lower()
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return "429"
    for code in ["400", "401", "403", "404", "408", "409", "422", "500", "502", "503", "504"]:
        if code in text:
            return code
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "connection" in text or "network" in text:
        return "network"
    return "unknown"


def _is_retryable_error(err: Exception) -> bool:
    code = _extract_error_code(err)
    # parse_error 视为可重试: LLM 偶发吐出坏/非 JSON 时, re-roll 通常能救回
    # (尤其 llm_judge)。坏文本不会入缓存(parse 在 _cache_set 之前), 重试即重新请求。
    if code in {"429", "408", "500", "502", "503", "504", "timeout", "network", "parse_error"}:
        return True
    if code in {"400", "401", "403", "404", "409", "422"}:
        return False
    return False


def _retry_wait_seconds(attempt_idx: int, err: Exception) -> float:
    retry_after = _extract_retry_after_seconds(err)
    base = retry_after if retry_after is not None else (2 ** attempt_idx)
    jitter = random.uniform(0.0, 1.0)
    return min(base + jitter, 30.0)


# ============================================================
# 鲁棒 JSON 解析
# ============================================================
def parse_json_robust(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("LLM 返回空文本")

    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    t = re.sub(r"\s*```$", "", t)

    start = t.find("{")
    if start == -1:
        raise ValueError(f"LLM 输出无 JSON 起始: {text[:200]}")

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
            pass

    try:
        return json.loads(t[start:])
    except json.JSONDecodeError:
        pass

    candidate = t[start:end] if end != -1 else t[start:]
    for _ in range(depth if depth > 0 else 3):
        candidate += "}"
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError(f"JSON 解析失败: {text[:200]}")


# ============================================================
# 核心: 带重试 + 限流 + 缓存 + seed 的 LLM 调用
# ============================================================
def call_llm(
    prompt: str,
    model: str,
    system: str = "你是精确的判定助手. 只输出 JSON, 不要任何额外文字.",
    max_tokens: int = 1000,
    seed: int = None,
    return_raw: bool = False,
):
    if seed is None:
        seed = DEFAULT_SEED

    STATS.record_call()

    key = _cache_key(prompt, model, seed, system)
    cached = _cache_get(key)
    if cached is not None:
        STATS.record_cache_hit()
        return cached if return_raw else parse_json_robust(cached)

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            with _INFLIGHT_SEMAPHORE:
                text = _dispatch_call(prompt, model, system, max_tokens, seed)
            STATS.record_latency(time.time() - t0)

            parsed = None
            if not return_raw:
                parsed = parse_json_robust(text)

            _cache_set(key, text)
            return text if return_raw else parsed
        except Exception as err:
            last_err = err
            retryable = _is_retryable_error(err)
            if attempt < MAX_RETRIES - 1 and retryable:
                STATS.record_retry()
                time.sleep(_retry_wait_seconds(attempt, err))
                continue
            err_code = _extract_error_code(err)
            STATS.record_failure(retryable=retryable, err_code=err_code)
            break

    raise RuntimeError(f"LLM 调用失败 (重试 {MAX_RETRIES} 次): {last_err}")


def _dispatch_call(prompt: str, model: str, system: str, max_tokens: int, seed: int) -> str:
    if model.startswith("claude"):
        return _call_anthropic(prompt, model, system, max_tokens)
    if model.startswith("deepseek"):
        return _call_openai_compat(
            prompt,
            model,
            system,
            max_tokens,
            seed,
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        )
    if model.startswith(("gpt", "o1", "o3", "o4")):
        return _call_openai_compat(
            prompt, model, system, max_tokens, seed, base_url=None, api_key_env="OPENAI_API_KEY"
        )
    raise ValueError(f"不支持的模型: {model}")


def _call_anthropic(prompt: str, model: str, system: str, max_tokens: int) -> str:
    from anthropic import Anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("需要 ANTHROPIC_API_KEY 环境变量")
    client = Anthropic(api_key=api_key, timeout=DEFAULT_TIMEOUT)
    actual_model = "claude-opus-4-7" if "4-7" in model else model
    resp = client.messages.create(
        model=actual_model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _call_openai_compat(
    prompt: str, model: str, system: str, max_tokens: int, seed: int, base_url, api_key_env
) -> str:
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
    else:
        create_kwargs["max_tokens"] = max_tokens
        create_kwargs["temperature"] = 0.0
        create_kwargs["seed"] = seed

    if model.startswith("deepseek"):
        thinking_on = os.getenv("VERIFIER_LLM_THINKING", "0") == "1"
        create_kwargs["extra_body"] = {"thinking": {"type": "enabled" if thinking_on else "disabled"}}

    resp = client.chat.completions.create(**create_kwargs)
    return resp.choices[0].message.content


if __name__ == "__main__":
    print("=== llm_client 自测 ===\n")
    cases = [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('这是结果: {"verdict": "pass", "reason": "ok"} 完毕', {"verdict": "pass", "reason": "ok"}),
        ('{"msg": "他说\\"你好\\""}', {"msg": '他说"你好"'}),
        ('{"a": 1, "b": {"c": 2}}', {"a": 1, "b": {"c": 2}}),
        ('{"a": 1', {"a": 1}),
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

    k1 = _cache_key("p", "m", 42, "s")
    k2 = _cache_key("p", "m", 42, "s")
    k3 = _cache_key("p", "m", 43, "s")
    print(f"\n缓存键: 同键={k1 == k2}, 异键={k1 != k3}")
    print(f"统计摘要: {get_stats_summary()}")
    print(
        f"\n配置: seed={DEFAULT_SEED}, timeout={DEFAULT_TIMEOUT}s, retries={MAX_RETRIES}, "
        f"cache={CACHE_ENABLED}, max_inflight={MAX_INFLIGHT}"
    )
    print("✅ 自测完成" if passed == len(cases) and k1 == k2 and k1 != k3 else "❌ 有失败")