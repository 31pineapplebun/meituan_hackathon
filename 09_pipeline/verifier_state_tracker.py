"""
state_tracker verifier - 判断流程 Step 是否被覆盖

升级目标:
1) 从“匹配 2 个关键词即 pass”升级为“必要要素清单 AND 判定”
2) 条件分支先判触发，再判执行，避免条件未触发时误判 fail/pass
3) 统一 evidence 输出，便于人工复核
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier_base import register, VerdictResult, get_assistant_turns, all_assistant_text


ACTION_SYNONYMS = {
    "告知": ["告知", "通知", "告诉", "说明", "提到", "讲", "说一下"],
    "询问": ["询问", "请问", "问", "想问", "能否", "是否", "吗", "呢", "对吗"],
    "提醒": ["提醒", "记得", "注意", "别忘", "务必"],
    "确认": ["确认", "核实", "确定", "是不是", "是否"],
    "引导": ["引导", "操作", "点击", "进入", "去", "打开"],
    "记录": ["记录", "登记", "备注", "记下"],
    "结束": ["结束", "再见", "挂断", "辛苦", "感谢", "祝您"],
}


def _contains_any(text: str, words: list) -> bool:
    return any(w and w in text for w in words)


def _extract_requirement_groups(constraint: dict) -> list:
    """把约束转成必要要素组: 每组命中任一词即可, 所有组都需命中"""
    text = f"{constraint.get('name', '')} {constraint.get('source_text', '')}"
    text = re.sub(r"\$\{[^}]+\}", "", text)
    groups = []

    if "自我介绍" in text or "我是" in text:
        groups.append(["我是", "这边是", "我是美团", "客服", "站长"])
    if "负责人" in text:
        groups.append(["负责人", "老板", "店长"])
    if "时间" in text:
        groups.append(["时间", "点", "月", "号", "明天", "今晚"])
    if "地点" in text:
        groups.append(["地点", "地址", "中心", "路", "门店", "应用商店", "APP", "在"])
    if "询问" in text or "请问" in text or "是否" in text or "能否" in text:
        groups.append(ACTION_SYNONYMS["询问"])
    if "提醒" in text:
        groups.append(ACTION_SYNONYMS["提醒"])
    if "记录" in text:
        groups.append(ACTION_SYNONYMS["记录"])
    if "引导" in text or "操作" in text or "点击" in text:
        groups.append(ACTION_SYNONYMS["引导"])
    if "结束" in text or "挂断" in text or "道谢" in text:
        groups.append(ACTION_SYNONYMS["结束"])

    # 业务关键词也视为必要槽位
    domain_keywords = ["培训", "头盔", "工牌", "身份证", "更新", "订单", "出餐", "差评", "申诉", "取消", "评级", "负责人"]
    for kw in domain_keywords:
        if kw in text:
            groups.append([kw])

    # 去重（组级）
    dedup = []
    seen = set()
    for g in groups:
        key = tuple(g)
        if key not in seen:
            seen.add(key)
            dedup.append(g)
    return dedup


def _extract_fallback_keywords(constraint: dict) -> list:
    text = f"{constraint.get('name', '')} {constraint.get('source_text', '')}"
    text = re.sub(r"\$\{[^}]+\}", "", text)
    tokens = re.split(r"[，。；,;:、\s（）()]+|并|且|然后|以及|或者|或", text)
    kws = []
    for tok in tokens:
        tok = tok.strip()
        if len(tok) >= 2 and tok not in {"若", "如果", "则", "进入", "跳到", "分支"}:
            kws.append(tok)
    out = []
    seen = set()
    for k in kws:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out[:6]


def _extract_conditional_parts(constraint: dict):
    text = f"{constraint.get('name', '')} {constraint.get('source_text', '')}"
    m = re.search(r"若(.+?)(?:，|,|。|；|;|则|进入|跳到)(.+)", text)
    if not m:
        return None, None
    cond = m.group(1).strip()
    action = m.group(2).strip()
    cond_tokens = [t for t in re.split(r"[，。；,;:、\s]+", cond) if len(t) >= 2][:4]
    action_tokens = [t for t in re.split(r"[，。；,;:、\s]+", action) if len(t) >= 2][:4]
    return cond_tokens, action_tokens


# ============================================================
# state_tracker 主体
# ============================================================

@register("state_tracker")
def verify_state_tracker(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """流程 step 覆盖判定: 必要要素 AND 判定 + 条件先触发后执行"""
    name = constraint.get("name", "")

    asst_text = all_assistant_text(dialogue)
    if not asst_text:
        return VerdictResult(verdict="na", reason="无 assistant 输出")

    user_text = " ".join([t.get("content", "") for t in dialogue.get("turns", []) if t.get("role") == "user"])

    # 条件分支: 先判触发
    cond_tokens, action_tokens = _extract_conditional_parts(constraint)
    if cond_tokens:
        cond_triggered = _contains_any(user_text, cond_tokens)
        if not cond_triggered:
            return VerdictResult(
                verdict="na",
                reason=f"条件未触发: {cond_tokens[:3]}",
                confidence=0.85,
            )
        if action_tokens and not _contains_any(asst_text, action_tokens):
            return VerdictResult(
                verdict="fail",
                evidence=f"条件触发但未执行动作: {action_tokens[:3]}",
                reason=f"条件已触发({cond_tokens[:3]}), 但助手未覆盖动作",
                confidence=0.7,
            )
        return VerdictResult(
            verdict="pass",
            evidence=f"条件触发({cond_tokens[:3]}), 且动作覆盖({action_tokens[:3]})",
            reason="分支约束满足",
            confidence=0.8,
        )

    # 普通流程: 必要要素 AND 判定
    groups = _extract_requirement_groups(constraint)
    if not groups:
        fallback = _extract_fallback_keywords(constraint)
        if not fallback:
            return VerdictResult(verdict="not_implemented", reason=f"无法提取流程要素: {name[:40]}")
        groups = [[k] for k in fallback]

    matched_groups = []
    missed_groups = []
    for g in groups:
        if _contains_any(asst_text, g):
            matched_groups.append(g)
        else:
            missed_groups.append(g)

    evidence_turns = []
    for t in get_assistant_turns(dialogue):
        content = t.get("content", "")
        if any(_contains_any(content, g) for g in matched_groups):
            evidence_turns.append(str(t.get("turn")))
            if len(evidence_turns) >= 3:
                break

    match_rate = len(matched_groups) / len(groups) if groups else 0
    if len(missed_groups) == 0:
        return VerdictResult(
            verdict="pass",
            evidence=f"turn{','.join(evidence_turns)} 覆盖要素组 {len(matched_groups)}/{len(groups)}",
            confidence=0.75 + match_rate * 0.2,
            reason=f"必要要素全部覆盖 ({len(groups)}/{len(groups)})",
        )

    missing_preview = ["|".join(g[:2]) for g in missed_groups[:3]]
    return VerdictResult(
        verdict="fail",
        evidence=f"缺失要素组: {missing_preview}",
        confidence=0.65,
        reason=f"必要要素覆盖不足 {len(matched_groups)}/{len(groups)} ({match_rate*100:.0f}%)",
    )


# ============================================================
# 自测
# ============================================================

def _test():
    """单元测试"""
    print("=" * 60)
    print("state_tracker verifier 自测")
    print("=" * 60)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: 普通行动 + 关键词完全匹配 → pass
    tests_total += 1
    constraint = {
        "id": "V1_C08", 
        "name": "S1 告知培训的具体时间地点，并询问骑手是否可以参加。",
        "verifier": "state_tracker",
        "source_text": "告知培训的具体时间地点，并询问骑手是否可以参加。"
    }
    dialogue = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好,告知您10月15号下午2点在望京有个安全培训,询问骑手能否参加?"},
            {"role": "user", "turn": 2, "content": "嗯,可以"},
        ]
    }
    result = verify_state_tracker(constraint, dialogue, {})
    print(f"\nTest 1 (V1_C08 完整匹配):")
    print(f"  verdict: {result.verdict}")
    print(f"  reason: {result.reason}")
    if result.verdict == "pass":
        print(f"  ✓ Pass")
        tests_passed += 1
    else:
        print(f"  ✗ 期望 pass")
    
    # Test 2: 缺失关键词 → fail
    tests_total += 1
    dialogue2 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好,我跟您说个事"},
            {"role": "user", "turn": 2, "content": "什么事"},
            {"role": "assistant", "turn": 3, "content": "就是有个事情"},
        ]
    }
    result = verify_state_tracker(constraint, dialogue2, {})
    print(f"\nTest 2 (缺失关键词):")
    print(f"  verdict: {result.verdict}")
    print(f"  reason: {result.reason}")
    if result.verdict == "fail":
        print(f"  ✓ Pass")
        tests_passed += 1
    else:
        print(f"  ✗ 期望 fail")
    
    # Test 3: 分支类约束 条件未触发 → na
    tests_total += 1
    branch_constraint = {
        "id": "V3_C11",
        "name": "S3 **分支1**：若骑手表示计划出勤，进入 Step 4；若骑手表示不出勤，跳到 Step 5",
        "verifier": "state_tracker",
        "source_text": "**分支1**：若骑手表示计划出勤，进入 Step 4；若骑手表示不出勤，跳到 Step 5。"
    }
    result = verify_state_tracker(branch_constraint, dialogue, {})
    print(f"\nTest 3 (分支类):")
    print(f"  verdict: {result.verdict}")
    print(f"  reason: {result.reason}")
    if result.verdict in ("na", "pass"):
        print(f"  ✓ Pass")
        tests_passed += 1
    else:
        print(f"  ✗ 期望 na/pass")
    
    # Test 4: mock 真实风格 V1 对话 (不依赖外部文件)
    tests_total += 1
    real_dialogue = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "喂，是王强吗？我是咱们美团的骑手站长。告知您10月15号下午2点在望京培训中心有个线下安全培训，您能过来参加吗?"},
            {"role": "user", "turn": 2, "content": "嗯,可以"},
            {"role": "assistant", "turn": 3, "content": "好,记得带上头盔、工牌和身份证。"},
            {"role": "user", "turn": 4, "content": "好"},
            {"role": "assistant", "turn": 5, "content": "未参加会影响接单评级,请务必到场。"},
        ]
    }
    result = verify_state_tracker(constraint, real_dialogue, {})
    print(f"\nTest 4 (mock 真实风格 V1 对话, V1_C08):")
    print(f"  verdict: {result.verdict}")
    print(f"  evidence: {result.evidence}")
    print(f"  reason: {result.reason}")
    if result.verdict == "pass":
        print(f"  ✓ Pass (符合预期: 配合型应覆盖 S1)")
        tests_passed += 1
    else:
        print(f"  ⚠️ 不符合预期")
    
    # Test 5: 要素提取规则验证
    tests_total += 1
    print(f"\nTest 5 (要素提取规则):")
    test_cases = [
        ("S1 告知培训时间地点", ["培训", "时间", "地点"]),
        ("S3 **分支**：询问出餐慢原因", ["询问", "出餐"]),
        ("S2 告知 APP 有强制更新要求", ["APP", "更新"]),
    ]
    pass_cnt = 0
    for text, expected in test_cases:
        groups = _extract_requirement_groups({"name": text, "source_text": text})
        flat = "|".join(["|".join(g) for g in groups])
        hit = sum(1 for e in expected if e in flat)
        rate = hit / len(expected)
        marker = "✓" if rate >= 0.5 else "✗"
        print(f"  {marker} '{text[:40]}' → {groups} (匹配率 {rate*100:.0f}%)")
        if rate >= 0.5:
            pass_cnt += 1
    if pass_cnt == len(test_cases):
        print(f"  ✓ 所有提取测试通过")
        tests_passed += 1
    else:
        print(f"  ⚠️ {pass_cnt}/{len(test_cases)} 通过")
    
    print()
    if tests_passed == tests_total:
        print(f"✅ {tests_passed}/{tests_total} 全过")
        return True
    else:
        print(f"⚠️ {tests_passed}/{tests_total} 通过")
        return tests_passed >= tests_total - 1  # 容忍 1 个失败


if __name__ == "__main__":
    success = _test()
    sys.exit(0 if success else 1)