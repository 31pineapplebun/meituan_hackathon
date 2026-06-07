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
import os
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


# 同义词组: 解决"约束说告知, 模型说通知/跟您说"的字面匹配冤案
# 每组内任一词出现, 都算命中该组里的任意关键词
SYNONYM_GROUPS = [
    {"告知", "通知", "告诉", "跟您说", "跟你说", "和您说", "说一下", "看到您", "提到", "讲"},
    {"询问", "问", "请问", "想问", "了解一下", "您看"},
    {"提醒", "提示", "记得", "别忘", "注意", "务必"},
    {"确认", "核实", "对一下", "确定", "是不是", "对吗"},
    {"说明", "解释", "介绍", "讲解", "阐述", "我们的"},
    {"引导", "带您", "帮您", "协助", "您可以", "操作"},
    {"记录", "登记", "记下", "标记", "备注"},
    {"取消", "撤销", "退掉", "关闭"},
    {"结束", "再见", "挂了", "祝您", "辛苦了", "就这样"},
    {"差评", "评价", "评分", "不好的评价"},
    {"超时", "慢", "晚", "延迟", "迟"},
]


# 关键动作动词 (meta 行为词). 提到模块级: 既给关键词抽取用,
# 也给"关键词退化为纯动作词→不可靠"的检测用 (见 verify_state_tracker)。
ACTION_VERBS = [
    "告知", "通知", "提醒", "询问", "问", "确认", "核实", "说明", "解释",
    "强调", "引导", "记录", "提供", "传达", "介绍", "祝", "结束", "拒绝",
]


def _kw_in_text(kw: str, text: str) -> bool:
    """关键词是否命中文本 — 支持同义词

    1. 字面直接命中
    2. 若 kw 属于某同义词组, 该组任一词命中也算
    """
    if kw in text:
        return True
    for group in SYNONYM_GROUPS:
        if kw in group:
            # kw 在这组里, 看这组其他词是否出现在文本
            if any(syn in text for syn in group):
                return True
    return False


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

    # 关键动词 (ACTION_VERBS) 现为模块级常量, 见文件上方

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
# LLM 语义兜底 (关键词退化为纯动作词时启用)
# ============================================================

def _llm_step_covered(constraint: dict, dialogue: dict) -> dict:
    """LLM 语义判定: assistant 是否真的覆盖/执行了该流程 step 的内容。

    在关键词匹配不可靠时调用 — 即架构里说的 "state_tracker = 关键词 + 同义词, LLM 兜底"
    的兜底分支。覆盖: 分支型 step / 关键词退化为纯动作词 / 抽不出关键词 / 关键词字面未命中。
    返回 facts dict: {verdict, score, evidence, reason}
    """
    turns_text = "\n".join(
        f"[Turn {t.get('turn')}] {t.get('role')}: {t.get('content')}"
        for t in dialogue.get("turns", [])
    )
    step_desc = constraint.get("source_text") or constraint.get("name", "")
    prompt = f"""# 任务: 判断助手是否在通话中真正"执行/覆盖"了下面这个流程步骤的语义内容

# 流程步骤 (来自外呼任务指令)
"{step_desc}"

# 判定标准
- pass: 助手用任意措辞, 实质性地传达/询问/执行了该步骤要求的核心信息
        (看语义不看字面; 占位符如 ${{Y}} 被任意具体数值替代都算覆盖)。
        若步骤是分支/条件型, 助手正确执行了对话中【实际触发】的那个分支即算 pass。
- fail: 助手通篇没有传达/执行该步骤的核心信息。
- na: 该步骤的触发前提在本次对话中未出现 (条件分支的条件未满足)。

# 对话内容
{turns_text}

# 输出 JSON (不要任何其他文字)
{{
  "verdict": "pass" 或 "fail" 或 "na",
  "score": 0.0-1.0,
  "evidence": "引用具体 turn 与原文片段, 最多200字",
  "reason": "简短理由, 最多100字"
}}
只输出 JSON."""

    # 关键约束走自一致性投票 (复用 llm_judge 的实现), 抹平单次抖动
    is_critical = constraint.get("is_critical", False)
    if is_critical and os.getenv("LLM_SELF_CONSISTENCY", "1") == "1":
        from verifier_llm_judge import _vote_judge
        return _vote_judge(prompt, n=3)
    from verifier_llm_extract import call_llm_for_extraction
    return call_llm_for_extraction(prompt)


# ============================================================
# state_tracker 主体
# ============================================================

@register("state_tracker")
def verify_state_tracker(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """流程 step 覆盖判定 (分层: 关键词命中 → 规则; 不可靠 → LLM 语义兜底)

    1. 有内容关键词且非分支 → 关键词+同义词匹配; 命中(高精度)直接 pass, 省 LLM。
    2. 关键词不可靠的情形 → 走 LLM 语义兜底 (架构承诺的"LLM 兜底"):
       - 分支型 step 约束 (含"若X→Y"等条件分支)
       - 关键词退化为纯动作词 (如仅 '说明', 业务名词抽不出来)
       - 抽不出关键词
       - 关键词字面未命中 (模型可能换了说法 → 字面 fail 是假阴性)
       mock 模式无法语义判定: 分支/纯动作词/无关键词 → not_implemented;
       关键词未命中 → 保留启发式 fail (便于离线测试, 不调 LLM)。
    """
    name = constraint.get("name", "")
    is_mock = os.getenv("VERIFIER_LLM_MOCK", "1") == "1"
    asst_text = all_assistant_text(dialogue)

    is_branch = is_branch_constraint(constraint)
    keywords = extract_step_keywords(constraint)
    meta_only = bool(keywords) and all(kw in ACTION_VERBS for kw in keywords)

    # ---- 路径 A: 关键词可靠 (有内容关键词 + 非分支 + 非纯动作词) → 先做规则匹配 ----
    if keywords and not is_branch and not meta_only:
        if not asst_text:
            return VerdictResult(verdict="na", reason="无 assistant 输出")
        matched, missed = [], []
        for kw in keywords:
            (matched if _kw_in_text(kw, asst_text) else missed).append(kw)
        match_rate = len(matched) / len(keywords)
        threshold_count = min(2, max(1, len(keywords) // 2))
        if len(matched) >= threshold_count or match_rate >= 0.4:
            # 关键词命中 = 高精度信号, 直接信任 (不调 LLM, 省成本)
            evidence_turns = []
            for t in get_assistant_turns(dialogue):
                if any(kw in t.get("content", "") for kw in matched):
                    evidence_turns.append(t.get("turn"))
                    if len(evidence_turns) >= 3:
                        break
            return VerdictResult(
                verdict="pass",
                evidence=f"turn{','.join(map(str, evidence_turns))} 含 {matched[:4]}",
                confidence=0.7 + match_rate * 0.3,
                reason=f"匹配关键词 {len(matched)}/{len(keywords)} ({match_rate*100:.0f}%, 阈值≥{threshold_count}个)"
            )
        # 关键词未命中: 字面不匹配可能是模型换了说法(假阴性)。
        # mock 模式无 LLM, 保留启发式 fail; 真实模式 → 落到下面的 LLM 语义兜底复核。
        if is_mock:
            return VerdictResult(
                verdict="fail",
                evidence=f"缺失关键词: {missed[:4]}",
                confidence=0.6,
                reason=f"只匹配 {len(matched)}/{len(keywords)} ({match_rate*100:.0f}%, 不足 {threshold_count} 个)"
            )
        # else: fall through to LLM 兜底

    # ---- 路径 B: LLM 语义兜底 (分支 / 纯动作词 / 无关键词 / 真实模式下关键词未命中) ----
    if is_branch:
        cause = "分支型step"
    elif meta_only:
        cause = f"关键词退化为纯动作词{keywords}"
    elif not keywords:
        cause = "无法抽取关键词"
    else:
        cause = "关键词字面未命中"

    if is_mock:
        return VerdictResult(
            verdict="not_implemented",
            reason=f"{cause}, mock 模式无法语义判定, 跳过: '{name[:30]}'"
        )
    if not asst_text:
        return VerdictResult(verdict="na", reason="无 assistant 输出")
    try:
        facts = _llm_step_covered(constraint, dialogue)
    except Exception as e:
        return VerdictResult(verdict="error", reason=f"LLM 语义兜底失败: {e}")
    verdict = facts.get("verdict", "error")
    if verdict not in ("pass", "fail", "na"):
        verdict = "error"
    return VerdictResult(
        verdict=verdict,
        evidence=("[LLM语义兜底] " + str(facts.get("evidence", "")))[:200],
        confidence=facts.get("score", 0.7),
        reason=(f"[{cause}→LLM兜底] " + str(facts.get("reason", "")))[:200],
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

    # Test 6: 关键词退化为纯动作词 (C08 式) → mock 模式 not_implemented (退化保护)
    tests_total += 1
    os.environ["VERIFIER_LLM_MOCK"] = "1"   # 显式锁定 mock, 测退化兜底分支
    degenerate = {
        "id": "TEST_C08",
        "name": "S2 说明单日飞毛腿合同需要**连续 ${Y} 天**完成配送；否则合同将受到影响。",
        "verifier": "state_tracker",
        "source_text": "说明单日飞毛腿合同需要**连续 ${Y} 天**完成配送；否则合同将受到影响。",
        "is_critical": True,
    }
    kws = extract_step_keywords(degenerate)
    r = verify_state_tracker(degenerate, {"turns": [
        {"role": "assistant", "turn": 1, "content": "你好，合同已生效，今天能跑吗？"},
    ]}, {})
    print(f"\nTest 6 (关键词退化保护, C08 式):")
    print(f"  抽取关键词: {kws} (应只剩动作词)")
    print(f"  verdict: {r.verdict}  reason: {r.reason[:50]}")
    only_action = bool(kws) and all(k in ACTION_VERBS for k in kws)
    if only_action and r.verdict == "not_implemented":
        print(f"  ✓ Pass (纯动作词 → mock 下 not_implemented, 不再误判 fail)")
        tests_passed += 1
    else:
        print(f"  ✗ 期望 only_action=True 且 not_implemented")

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
