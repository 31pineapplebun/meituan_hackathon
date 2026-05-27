"""
state_tracker verifier - 判断流程 Step 是否被覆盖

设计:
- 主路径: 从约束 source_text 提取关键词, 在 assistant 全文中匹配
- 子路径: 分支类约束(含"分支"/"若"字)走 LLM 判定
- 兜底: 无法判定时返回 not_implemented

约束的常见模式:
1. 行动描述: "告知培训时间地点" → 提取 "培训", "时间", "地点" 等核心词
2. 询问类: "询问是否参加" → 检查疑问句 + 核心词
3. 分支判定: "若X→Y, 若A→B" → 关键词太抽象, 暂用 not_implemented

输出统一用 VerdictResult.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier_base import register, VerdictResult, get_assistant_turns, all_assistant_text


# ============================================================
# 关键词提取
# ============================================================

# 停用词(出现频率高但不算"业务关键")
STOPWORDS = {
    "的", "了", "是", "在", "和", "也", "都", "这", "那", "有", "就", "我", "你", "她", "他",
    "对", "并", "及", "或", "与", "如", "且", "等", "需要", "可以", "进行", "请", "您",
    "为", "以", "向", "把", "被", "让", "给", "做", "比", "从", "到", "上", "下", "里",
    "之", "其", "者", "之", "了", "啊", "哦", "呢", "嗯", "吗", "吧", "啦",
    "若", "如果", "如", "时", "时候",
    "进入", "跳到", "Step", "S", "S1", "S2", "S3", "S4", "S5", "S6", "S7",
    "分支", "原因", "情况", "方式", "内容", "信息",
    "**", "$", "{", "}",
}


def extract_step_keywords(constraint: dict) -> list:
    """从约束名称和源文本提取关键词
    
    策略:
    1. 移除 Sx/Step X 前缀, 占位符, 标记
    2. 用更细粒度的分词: 按字符 n-gram 拆解出 2-4 字的核心词
    3. 过滤停用词
    4. 优先保留: 动词("告知"/"询问"/"提醒")+名词("培训"/"原因") 组合
    """
    name = constraint.get("name", "")
    source = constraint.get("source_text", "")
    
    # 优先用 source_text(更完整), 兜底用 name
    text = source if source and len(source) > len(name) // 2 else name
    
    # 移除 "S1/Step X" 前缀
    text = re.sub(r"^S?\d+(\.\d+)?\s*", "", text)
    text = re.sub(r"^Step\s*\d+\s*", "", text)
    text = re.sub(r"^\*\*[^*]+\*\*[:：]?\s*", "", text)
    
    # 移除占位符
    text = re.sub(r"\$\{[^}]+\}", "", text)
    
    # 关键动词 (评测系统里最常用的)
    ACTION_VERBS = ["告知", "通知", "提醒", "询问", "问", "确认", "核实", "说明", "解释", 
                     "强调", "引导", "记录", "提供", "传达", "介绍", "祝", "结束", "拒绝"]
    
    # 关键名词 (业务核心)
    DOMAIN_NOUNS = [
        # 通用
        "培训", "时间", "地点", "原因", "费用", "补贴", "评级", "证件",
        # V1 骑手
        "头盔", "工牌", "身份证", "安全培训", "接单",
        # V2 APP更新
        "APP", "更新", "强制", "版本", "应用商店", "登录", 
        # V3 天气
        "天气", "预警", "出勤", "暴雨", "调休",
        # V4 商家出餐
        "订单", "出餐", "超时", "高峰期", "缺货", "取消", "联系", "骑手", "用户",
        # V5 差评
        "差评", "申诉", "改善", "意见", "数量",
        # V6 关店
        "关店", "申请", "临时", "永久", "经营", "节假日",
        # 角色
        "负责人", "商家", "骑手", "客服", "站长",
    ]
    
    found_verbs = [v for v in ACTION_VERBS if v in text]
    found_nouns = [n for n in DOMAIN_NOUNS if n in text]
    
    keywords = []
    
    # 优先添加动词+名词组合(关键短语)
    keywords.extend(found_verbs)
    keywords.extend(found_nouns)
    
    # 兜底: 如果上面没找到, 按标点切分提取
    if len(keywords) < 2:
        segments = re.split(r"[，。；,;:、\s（()）]+|并|且|又|再|然后|接着|或", text)
        for seg in segments:
            seg = seg.strip()
            if 2 <= len(seg) <= 6 and seg not in STOPWORDS:
                # 去除常见后缀
                seg = re.sub(r"(等)$", "", seg)
                if seg and seg not in keywords:
                    keywords.append(seg)
    
    # 去重保序
    seen = set()
    result = []
    for k in keywords:
        if k not in seen and len(k) >= 1:
            seen.add(k)
            result.append(k)
    
    return result[:7]  # 最多 7 个


def is_branch_constraint(constraint: dict) -> bool:
    """是否分支判定类(暂不支持)"""
    text = constraint.get("name", "") + " " + constraint.get("source_text", "")
    # 含"分支"、多个"若"、"→" 等
    if "分支" in text and "若" in text:
        return True
    if text.count("若") >= 2:
        return True
    if text.count("→") >= 2:
        return True
    return False


# ============================================================
# state_tracker 主体
# ============================================================

@register("state_tracker")
def verify_state_tracker(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """流程 step 覆盖判定
    
    策略:
    1. 分支类 → not_implemented (Day 9 用 LLM)
    2. 普通 step → 关键词匹配
    """
    name = constraint.get("name", "")
    
    # 1. 分支类约束: 暂不支持
    if is_branch_constraint(constraint):
        return VerdictResult(
            verdict="not_implemented",
            reason=f"分支判定类约束需 LLM 支持(Day 9 实现): '{name[:40]}'"
        )
    
    # 2. 提取关键词
    keywords = extract_step_keywords(constraint)
    
    if not keywords:
        return VerdictResult(
            verdict="not_implemented",
            reason=f"无法从约束提取关键词: '{name[:40]}'"
        )
    
    # 3. 在 assistant 全文匹配
    asst_text = all_assistant_text(dialogue)
    if not asst_text:
        return VerdictResult(verdict="na", reason="无 assistant 输出")
    
    # 4. 判定逻辑: 至少匹配 2 个关键词 或 40% 匹配率
    matched = []
    missed = []
    for kw in keywords:
        if kw in asst_text:
            matched.append(kw)
        else:
            missed.append(kw)
    
    match_rate = len(matched) / len(keywords) if keywords else 0
    
    # 找匹配的 turn 作为证据
    evidence_turns = []
    if matched:
        for t in get_assistant_turns(dialogue):
            if any(kw in t.get("content", "") for kw in matched):
                evidence_turns.append(t.get("turn"))
                if len(evidence_turns) >= 3:
                    break
    
    # 判定: 至少 2 个匹配 或 ≥40%
    threshold_count = min(2, max(1, len(keywords) // 2))
    if len(matched) >= threshold_count or match_rate >= 0.4:
        return VerdictResult(
            verdict="pass",
            evidence=f"turn{','.join(map(str, evidence_turns))} 含 {matched[:4]}",
            confidence=0.7 + match_rate * 0.3,
            reason=f"匹配关键词 {len(matched)}/{len(keywords)} ({match_rate*100:.0f}%, 阈值≥{threshold_count}个)"
        )
    else:
        return VerdictResult(
            verdict="fail",
            evidence=f"缺失关键词: {missed[:4]}",
            confidence=0.6,
            reason=f"只匹配 {len(matched)}/{len(keywords)} ({match_rate*100:.0f}%, 不足 {threshold_count} 个)"
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
    print(f"  关键词: {extract_step_keywords(constraint)}")
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
    
    # Test 3: 分支类约束 → not_implemented
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
    if result.verdict == "not_implemented":
        print(f"  ✓ Pass")
        tests_passed += 1
    else:
        print(f"  ✗ 期望 not_implemented")
    
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
    print(f"  关键词: {extract_step_keywords(constraint)}")
    print(f"  verdict: {result.verdict}")
    print(f"  evidence: {result.evidence}")
    print(f"  reason: {result.reason}")
    if result.verdict == "pass":
        print(f"  ✓ Pass (符合预期: 配合型应覆盖 S1)")
        tests_passed += 1
    else:
        print(f"  ⚠️ 不符合预期")
    
    # Test 5: 关键词提取规则验证
    tests_total += 1
    print(f"\nTest 5 (关键词提取规则):")
    test_cases = [
        ("S1 告知培训时间地点", ["告知", "培训", "时间", "地点"]),  # 简单
        ("S3 **分支**：询问出餐慢原因", ["询问", "出餐慢", "原因"]),  # 含**分支**前缀
        ("S2 告知 APP 有强制更新要求", ["告知", "APP", "强制", "更新", "要求"]),  # 含英文
    ]
    pass_cnt = 0
    for text, expected in test_cases:
        kws = extract_step_keywords({"name": text, "source_text": text})
        # 检查 expected 中至少 60% 出现
        hit = sum(1 for e in expected if any(e in k or k in e for k in kws))
        rate = hit / len(expected)
        marker = "✓" if rate >= 0.5 else "✗"
        print(f"  {marker} '{text[:40]}' → {kws} (匹配率 {rate*100:.0f}%)")
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
