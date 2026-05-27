"""
Verifier 注册表 + 基础接口

设计原则:
1. 统一接口 (signature)，方便扩展
2. 注册表机制，新 verifier 只需 @register('xxx')
3. 未实现的 verifier 优雅跳过 (verdict=not_implemented)

每个 Verifier 接收:
  constraint: 约束 dict (id/name/verifier/source_text/verifier_config等)
  dialogue:   对话 dict (含 turns 列表)
  instruction: 完整指令 dict (含 meta/atomic_constraints/flow_steps)

每个 Verifier 返回 VerdictResult dataclass:
  verdict:    pass | fail | na | error | not_implemented
  evidence:   证据片段 (字符串)
  confidence: 0.0-1.0
  reason:     判定理由
"""
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional


# ============================================================
# 接口定义
# ============================================================

@dataclass
class VerdictResult:
    """单条约束的判定结果"""
    verdict: str                  # pass | fail | na | error | not_implemented
    evidence: str = ""            # 证据片段
    confidence: float = 1.0       # 0-1
    reason: str = ""              # 判定理由(人类可读)
    
    # 自动填充字段(由 pipeline 注入)
    constraint_id: str = ""
    constraint_name: str = ""
    verifier_type: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @property
    def passed(self) -> bool:
        """方便给 P3 评分算法用 (它需要 bool)"""
        return self.verdict == "pass"


# Verifier 函数签名: 
# (constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult
VerifierFunc = Callable[[dict, dict, dict], VerdictResult]


# ============================================================
# 注册表
# ============================================================

_VERIFIER_REGISTRY: dict = {}


def register(verifier_type: str):
    """装饰器: 注册 verifier 函数"""
    def decorator(func: VerifierFunc):
        _VERIFIER_REGISTRY[verifier_type] = func
        return func
    return decorator


def dispatch(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """根据 constraint 的 verifier 类型分发到对应函数"""
    verifier_type = constraint.get("verifier", "")
    constraint_id = constraint.get("id", "")
    constraint_name = constraint.get("name", "")
    
    func = _VERIFIER_REGISTRY.get(verifier_type)
    
    if func is None:
        # 未实现
        result = VerdictResult(
            verdict="not_implemented",
            reason=f"verifier 类型 '{verifier_type}' 未实现 (将在后续迭代中支持)",
        )
    else:
        try:
            result = func(constraint, dialogue, instruction)
        except Exception as e:
            result = VerdictResult(
                verdict="error",
                reason=f"verifier 执行异常: {type(e).__name__}: {e}",
            )
    
    # 注入约束 ID 信息
    result.constraint_id = constraint_id
    result.constraint_name = constraint_name
    result.verifier_type = verifier_type
    return result


def list_registered() -> list:
    """列出已注册的 verifier 类型"""
    return sorted(_VERIFIER_REGISTRY.keys())


# ============================================================
# 工具函数（多个 verifier 复用）
# ============================================================

def get_assistant_turns(dialogue: dict) -> list:
    """提取所有 assistant turn"""
    return [t for t in dialogue.get("turns", []) if t.get("role") == "assistant"]


def get_user_turns(dialogue: dict) -> list:
    """提取所有 user turn"""
    return [t for t in dialogue.get("turns", []) if t.get("role") == "user"]


def all_assistant_text(dialogue: dict) -> str:
    """拼接所有 assistant 输出，用于全文搜索"""
    return " ".join(t.get("content", "") for t in get_assistant_turns(dialogue))


# ============================================================
# 自测
# ============================================================

def _test():
    """单元测试"""
    print("=" * 60)
    print("verifier 接口自测")
    print("=" * 60)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: 未注册 verifier 返回 not_implemented
    tests_total += 1
    result = dispatch(
        {"id": "TEST_C01", "name": "测试", "verifier": "non_existent"},
        {"turns": []},
        {}
    )
    if result.verdict == "not_implemented":
        print("✓ Test 1: 未注册 verifier 返回 not_implemented")
        tests_passed += 1
    else:
        print(f"✗ Test 1: 期望 not_implemented, 实际 {result.verdict}")
    
    # Test 2: 注册并调用
    tests_total += 1
    @register("test_verifier")
    def test_func(constraint, dialogue, instruction):
        return VerdictResult(verdict="pass", reason="测试通过")
    
    result = dispatch(
        {"id": "TEST_C02", "name": "测试2", "verifier": "test_verifier"},
        {"turns": []},
        {}
    )
    if result.verdict == "pass" and result.constraint_id == "TEST_C02":
        print("✓ Test 2: 注册 + 调用 + ID 注入成功")
        tests_passed += 1
    else:
        print(f"✗ Test 2: 异常 {result}")
    
    # Test 3: verifier 抛异常被捕获
    tests_total += 1
    @register("buggy_verifier")
    def buggy_func(constraint, dialogue, instruction):
        raise ValueError("故意的异常")
    
    result = dispatch(
        {"id": "TEST_C03", "name": "测试3", "verifier": "buggy_verifier"},
        {"turns": []},
        {}
    )
    if result.verdict == "error" and "ValueError" in result.reason:
        print("✓ Test 3: 异常被捕获并返回 error")
        tests_passed += 1
    else:
        print(f"✗ Test 3: 异常未被捕获 {result}")
    
    # Test 4: 工具函数
    tests_total += 1
    dialogue = {"turns": [
        {"role": "assistant", "content": "你好"},
        {"role": "user", "content": "嗯"},
        {"role": "assistant", "content": "再见"},
    ]}
    asst = get_assistant_turns(dialogue)
    text = all_assistant_text(dialogue)
    if len(asst) == 2 and text == "你好 再见":
        print("✓ Test 4: 工具函数 (get_assistant_turns + all_assistant_text)")
        tests_passed += 1
    else:
        print(f"✗ Test 4: 工具函数异常")
    
    # 清理测试注册
    _VERIFIER_REGISTRY.pop("test_verifier", None)
    _VERIFIER_REGISTRY.pop("buggy_verifier", None)
    
    print()
    if tests_passed == tests_total:
        print(f"✅ {tests_passed}/{tests_total} 全过")
        return True
    else:
        print(f"❌ {tests_passed}/{tests_total} 通过")
        return False


if __name__ == "__main__":
    import sys
    success = _test()
    sys.exit(0 if success else 1)
