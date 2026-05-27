"""
具体 verifier 实现 - Day 7 MVP 版本

实现的 verifier:
- rule:         字数限制类（"每次回复30字内"）
- rule_pattern: 关键词匹配类（"不说好的"、"开场白含负责人"）

未实现的（Day 8+ 迭代）:
- state_tracker:        流程节点覆盖
- llm_extract_then_rule: LLM 抽取 + 规则
- llm_judge:            纯 LLM 判断
"""
import re
from verifier_base import register, VerdictResult, get_assistant_turns, all_assistant_text


# ============================================================
# rule verifier: 字数限制类
# ============================================================

# 字数约束的关键词模式
LENGTH_REGEX = re.compile(r"(\d+)\s*[-至到~]\s*(\d+)\s*字|(\d+)\s*字(?:以内|内|左右)?")


def extract_length_limit(constraint_name: str, source_text: str) -> tuple:
    """从约束 name/source_text 中提取字数限制
    
    返回 (min_chars, max_chars) 或 (None, None) 表示无法提取
    """
    for text in [constraint_name, source_text]:
        if not text:
            continue
        m = LENGTH_REGEX.search(text)
        if m:
            if m.group(1) and m.group(2):
                # X-Y字 范围
                return int(m.group(1)), int(m.group(2))
            elif m.group(3):
                # X字以内
                return None, int(m.group(3))
    return None, None


@register("rule")
def verify_rule(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """字数限制类约束
    
    支持的 source_text 格式:
    - "每次回复30字以内" → max=30
    - "每次回复15-20字" → min=15, max=20
    - "回复控制在 15-20 字左右" → min=15, max=20
    
    特殊处理:
    - "无变量残留" / "占位符未替换" → 检查对话中无 ${xxx} 残留
    """
    name = constraint.get("name", "")
    source_text = constraint.get("source_text", "")
    full_text = name + " " + source_text
    
    # 特殊场景: 无占位符残留检查
    if "变量" in full_text and ("替换" in full_text or "残留" in full_text or "占位" in full_text):
        return _verify_no_placeholder(dialogue)
    
    # 提取字数限制
    min_chars, max_chars = extract_length_limit(name, source_text)
    
    if max_chars is None:
        return VerdictResult(
            verdict="not_implemented",
            reason=f"无法从约束中提取字数限制: name='{name}' source='{source_text[:50]}'"
        )
    
    # 软边界 (允许超 5 字)
    soft_max = max_chars + 5
    
    asst_turns = get_assistant_turns(dialogue)
    if not asst_turns:
        return VerdictResult(verdict="na", reason="对话无 assistant 输出")
    
    # 跳过第一轮(开场白豁免)
    asst_to_check = asst_turns[1:] if len(asst_turns) > 1 else []
    
    if not asst_to_check:
        return VerdictResult(verdict="na", reason="只有开场白,无后续 assistant 回复可检查")
    
    # 检查每轮
    violations = []
    too_short = []
    for t in asst_to_check:
        n = len(t.get("content", ""))
        if n > soft_max:
            violations.append((t.get("turn"), n))
        if min_chars is not None and n < min_chars - 3:  # 软下边界
            too_short.append((t.get("turn"), n))
    
    total = len(asst_to_check)
    violation_rate = len(violations) / total if total > 0 else 0
    
    # 判定逻辑:
    # - 违规率 ≥ 30% → fail
    # - 违规率 < 30% → pass
    if violation_rate >= 0.3:
        # 取最长的几个作为证据
        worst = sorted(violations, key=lambda x: -x[1])[:3]
        evidence = "; ".join([f"turn{t}={n}字" for t, n in worst])
        return VerdictResult(
            verdict="fail",
            evidence=evidence,
            confidence=0.95,
            reason=f"{len(violations)}/{total}={violation_rate*100:.0f}%超字数(限{max_chars}+5={soft_max})"
        )
    else:
        return VerdictResult(
            verdict="pass",
            evidence=f"{len(violations)}/{total} 轮超字数",
            confidence=0.9,
            reason=f"超字数率 {violation_rate*100:.0f}% < 30%, 通过"
        )


# ============================================================
# rule_pattern verifier: 关键词匹配类
# ============================================================

PLACEHOLDER_RE = re.compile(r"\$\{[^}]+\}")


def _verify_no_placeholder(dialogue: dict) -> VerdictResult:
    """检查对话中是否还有未替换的 ${xxx} 占位符"""
    asst_turns = get_assistant_turns(dialogue)
    if not asst_turns:
        return VerdictResult(verdict="na", reason="无 assistant 输出")
    
    violations = []
    for t in asst_turns:
        content = t.get("content", "")
        matches = PLACEHOLDER_RE.findall(content)
        if matches:
            violations.append({
                "turn": t.get("turn"),
                "placeholders": list(set(matches)),
                "snippet": content[:80],
            })
    
    if violations:
        evidence = "; ".join([f"turn{v['turn']}: {v['placeholders']}" for v in violations[:3]])
        return VerdictResult(
            verdict="fail",
            evidence=evidence,
            confidence=1.0,
            reason=f"{len(violations)} 轮含未替换占位符"
        )
    return VerdictResult(
        verdict="pass",
        confidence=1.0,
        reason="所有变量都已正确替换"
    )

# 常见禁用词
FORBIDDEN_WORDS_PATTERNS = [
    r"好的",
    r"哈哈",
    r"嘿嘿",
    r"嘻嘻",
]


def is_forbidden_words_constraint(constraint: dict) -> bool:
    """判断是否为禁用词类约束"""
    text = (constraint.get("name", "") + " " + constraint.get("source_text", "")).lower()
    return "禁用" in text or "不说" in text or "禁止" in text


def is_opening_line_constraint(constraint: dict) -> bool:
    """判断是否为开场白合规约束"""
    text = constraint.get("name", "").lower()
    return "opening" in text or "开场白" in text or "开头" in text


def extract_must_have_keywords(constraint: dict, instruction: dict) -> list:
    """提取约束的'必须含有'关键词
    
    暂时简单实现: 看 source_text 中是否提到必含词
    更完整的实现需要 LLM 抽取
    """
    source = constraint.get("source_text", "")
    # 简单启发: source_text 里出现的关键词
    candidates = []
    for kw in ["负责人", "培训机构", "美团", "客服", "站长", "骑手"]:
        if kw in source:
            candidates.append(kw)
    return candidates


@register("rule_pattern")
def verify_rule_pattern(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """关键词匹配类约束
    
    分两种子类型:
    1. 禁用词类: 不能含 X (如 "不说好的")
    2. 必含词类: 必须含 X (如 "开场白含负责人")
    """
    name = constraint.get("name", "")
    
    # 子类型 1: 禁用词
    if is_forbidden_words_constraint(constraint):
        return _verify_forbidden_words(constraint, dialogue)
    
    # 子类型 2: 开场白合规
    if is_opening_line_constraint(constraint):
        return _verify_opening_line(constraint, dialogue, instruction)
    
    # 其他类型: 还未支持
    return VerdictResult(
        verdict="not_implemented",
        reason=f"rule_pattern 暂不支持此子类型: '{name}'"
    )


def _verify_forbidden_words(constraint: dict, dialogue: dict) -> VerdictResult:
    """禁用词检查"""
    asst_text = all_assistant_text(dialogue)
    
    if not asst_text:
        return VerdictResult(verdict="na", reason="无 assistant 输出")
    
    violations = []
    for pattern in FORBIDDEN_WORDS_PATTERNS:
        if re.search(pattern, asst_text):
            # 找出哪些 turn 出现
            for t in get_assistant_turns(dialogue):
                if re.search(pattern, t.get("content", "")):
                    violations.append({
                        "turn": t.get("turn"),
                        "word": pattern,
                        "snippet": t.get("content", "")[:50]
                    })
                    break  # 每个词只取第一处
    
    if violations:
        evidence = "; ".join([f"turn{v['turn']}用了'{v['word']}'" for v in violations])
        return VerdictResult(
            verdict="fail",
            evidence=evidence,
            confidence=1.0,
            reason=f"出现 {len(violations)} 个禁用词"
        )
    else:
        return VerdictResult(
            verdict="pass",
            confidence=1.0,
            reason="全程未出现禁用词"
        )


def _verify_opening_line(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """开场白合规检查"""
    asst_turns = get_assistant_turns(dialogue)
    if not asst_turns:
        return VerdictResult(verdict="na", reason="无 assistant 输出")
    
    opening_content = asst_turns[0].get("content", "")
    
    # 从指令拿到 opening_line 模板, 提取关键词
    instr_opening = ""
    if isinstance(instruction.get("meta"), dict):
        instr_opening = instruction["meta"].get("opening_line", "")
    
    must_have = extract_must_have_keywords(constraint, instruction)
    
    if not must_have:
        return VerdictResult(
            verdict="not_implemented",
            reason="无法从约束推断'必含关键词',跳过"
        )
    
    missing = [kw for kw in must_have if kw not in opening_content]
    
    if missing:
        return VerdictResult(
            verdict="fail",
            evidence=f"开场白: {opening_content[:80]}",
            confidence=0.9,
            reason=f"开场白缺少关键词: {missing}"
        )
    else:
        return VerdictResult(
            verdict="pass",
            evidence=f"开场白: {opening_content[:80]}",
            confidence=0.9,
            reason=f"开场白含所有必要关键词: {must_have}"
        )


# ============================================================
# 自测
# ============================================================

def _test():
    """单元测试"""
    print("=" * 60)
    print("verifier 实现自测")
    print("=" * 60)
    
    tests_passed = 0
    tests_total = 0
    
    # ===== rule (字数) =====
    
    # Test 1: 长度违规 (V4 长度限制 20 字)
    tests_total += 1
    constraint = {
        "id": "V4_C01", "name": "每次回复15-20字",
        "verifier": "rule", "source_text": "15-20 字以内"
    }
    dialogue = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好，请问是负责人吗？" * 3},  # 开场白(豁免)
            {"role": "user", "turn": 2, "content": "是"},
            {"role": "assistant", "turn": 3, "content": "好的，我跟您说一下这次的事情，是关于订单超时的问题，需要您配合一下。"},  # 超字数
            {"role": "user", "turn": 4, "content": "嗯"},
            {"role": "assistant", "turn": 5, "content": "您看这个订单有30分钟没出餐了，跟您核实是不是高峰期忙不过来。"},  # 超字数
            {"role": "user", "turn": 6, "content": "对"},
            {"role": "assistant", "turn": 7, "content": "好的。"},  # 合规
        ]
    }
    result = verify_rule(constraint, dialogue, {})
    if result.verdict == "fail" and "超字数" in result.reason:
        print(f"✓ Test 1 (rule): 长度违规 correctly fail")
        print(f"    {result.reason}")
        tests_passed += 1
    else:
        print(f"✗ Test 1: 期望 fail, 实际 {result.verdict} ({result.reason})")
    
    # Test 2: 长度合规
    tests_total += 1
    dialogue2 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好"},
            {"role": "user", "turn": 2, "content": "嗯"},
            {"role": "assistant", "turn": 3, "content": "您是负责人吗"},
            {"role": "user", "turn": 4, "content": "对"},
            {"role": "assistant", "turn": 5, "content": "订单超时了"},
        ]
    }
    result = verify_rule(constraint, dialogue2, {})
    if result.verdict == "pass":
        print(f"✓ Test 2 (rule): 长度合规 correctly pass")
        tests_passed += 1
    else:
        print(f"✗ Test 2: 期望 pass, 实际 {result.verdict}")
    
    # Test 3: 无法提取字数限制
    tests_total += 1
    bad_constraint = {
        "id": "TEST", "name": "随便写",
        "verifier": "rule", "source_text": "什么都没说"
    }
    result = verify_rule(bad_constraint, dialogue2, {})
    if result.verdict == "not_implemented":
        print(f"✓ Test 3 (rule): 无字数限制 → not_implemented")
        tests_passed += 1
    else:
        print(f"✗ Test 3: 期望 not_implemented, 实际 {result.verdict}")
    
    # ===== rule_pattern (禁用词) =====
    
    # Test 4: 禁用词违规
    tests_total += 1
    forbidden_constraint = {
        "id": "V1_C07", "name": "不说好的等语气词",
        "verifier": "rule_pattern", "source_text": "不说'好的'等语气词"
    }
    dialogue3 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好"},
            {"role": "user", "turn": 2, "content": "嗯"},
            {"role": "assistant", "turn": 3, "content": "好的，那我跟您说"},  # 违规
        ]
    }
    result = verify_rule_pattern(forbidden_constraint, dialogue3, {})
    if result.verdict == "fail" and "好的" in result.evidence:
        print(f"✓ Test 4 (rule_pattern): 禁用词 correctly fail")
        print(f"    evidence: {result.evidence}")
        tests_passed += 1
    else:
        print(f"✗ Test 4: 期望 fail, 实际 {result.verdict}")
    
    # Test 5: 禁用词合规
    tests_total += 1
    dialogue4 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好"},
            {"role": "assistant", "turn": 3, "content": "明白了，那我跟您说"},  # 合规
        ]
    }
    result = verify_rule_pattern(forbidden_constraint, dialogue4, {})
    if result.verdict == "pass":
        print(f"✓ Test 5 (rule_pattern): 无禁用词 correctly pass")
        tests_passed += 1
    else:
        print(f"✗ Test 5: 期望 pass, 实际 {result.verdict}")
    
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
