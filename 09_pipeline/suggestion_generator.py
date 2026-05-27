"""
优化建议生成器 - 把"什么 fail 了"升级为"该怎么改"

设计理念:
- 不只是列出违规,要给具体的改进方法
- 每条建议含: 问题描述 + 具体证据 + 改进方法 + 期望效果
- 按 verifier 类型分类生成,因为不同类型的修复方法不同

输出格式:
- 结构化 JSON (机器友好,可被 UI 渲染)
- 自然语言 (人类友好,可直接放 markdown)
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
import re


@dataclass
class Suggestion:
    """单条优化建议"""
    constraint_id: str           # 约束 ID
    constraint_name: str         # 约束名称
    priority: str                # P0_CRITICAL / P1_HIGH / P2_MEDIUM / P3_LOW
    severity: str                # 严重程度: 致命/严重/中等/轻微
    category: str                # 改进类别: 字数/流程/承诺/...
    problem: str                 # 问题描述 (一句话)
    evidence: str                # 具体证据 (引用 turn)
    how_to_fix: str              # 改进方法 (具体可执行)
    expected_impact: str         # 期望效果 ("修复后 D3 +5 分")
    example: Optional[str] = None  # 示范例子 (可选)


# ============================================================
# 按 verifier 类型的修复模板
# ============================================================

def generate_for_rule(constraint: dict, verdict_result, dialogue: dict) -> Suggestion:
    """rule 类: 字数/占位符"""
    name = constraint.get("name", "")
    evidence = verdict_result.evidence or ""
    
    # 字数类
    if "字" in name and ("以内" in name or "字数" in name or "字左右" in name):
        # 提取限制字数
        m = re.search(r"(\d+)\s*-\s*(\d+)\s*字", name)
        if m:
            limit_low, limit_high = int(m.group(1)), int(m.group(2))
            limit_desc = f"{limit_low}-{limit_high} 字"
        else:
            m2 = re.search(r"(\d+)\s*字以内", name)
            limit_desc = f"{m2.group(1)} 字以内" if m2 else "字数限制"
        
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P1_HIGH" if constraint.get("is_critical") else "P2_MEDIUM",
            severity="严重" if verdict_result.confidence > 0.7 else "中等",
            category="回复长度",
            problem=f"多轮回复超出 {limit_desc} 限制",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **拆分长 turn**: 把超字数的回复拆成 2 轮,每轮控制在 {limit_desc}\n"
                f"  2. **删冗余信息**: 检查是否重复了之前已说过的内容\n"
                f"  3. **使用短句**: 把'我帮您确认一下并通知骑手让他们等待'改为'我去通知骑手等等'\n"
                f"  4. **每轮聚焦 1 个信息点**: 不要一口气说 3 件事"
            ),
            expected_impact=f"修复后 D3 约束遵循度 +5-10 分",
            example=f"❌ 'T7=45字'  →  ✅ T7=20字 + T9=20字（拆成两轮）"
        )
    
    # 占位符残留
    if "变量" in name or "占位符" in name or "${" in str(constraint.get("source_text", "")):
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P0_CRITICAL",
            severity="致命",
            category="变量替换",
            problem="对话中残留未替换的 ${} 模板占位符",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **检查变量字典**: 确保 instruction 中所有 ${{xxx}} 都在 variables 里有值\n"
                f"  2. **替换前校验**: 模型输出前用正则 r'\\$\\{{.+?\\}}' 扫一遍,有就报错\n"
                f"  3. **加默认值**: 万一变量没传,用默认值替代而不是保留原文"
            ),
            expected_impact="修复后避免用户看到 '欢迎您 ${user_name}' 这种穿帮",
        )
    
    # 默认通用模板
    return Suggestion(
        constraint_id=constraint["id"],
        constraint_name=name,
        priority="P2_MEDIUM",
        severity="中等",
        category="规则违规",
        problem=verdict_result.reason or "违反规则",
        evidence=evidence[:150],
        how_to_fix="按约束原文要求修正",
        expected_impact="修复后该约束 pass",
    )


def generate_for_rule_pattern(constraint: dict, verdict_result, dialogue: dict) -> Suggestion:
    """rule_pattern 类: 禁用词/开场白合规"""
    name = constraint.get("name", "")
    evidence = verdict_result.evidence or ""
    
    # 禁用词
    if "不说" in name or "禁用" in name or "不要说" in name:
        # 提取禁用词
        m = re.search(r"[\"]([^\"]+)[\"]", name)
        forbidden_word = m.group(1) if m else "禁用词"
        
        # 友好替代词
        replacements = {
            "好的": "嗯/行/收到",
            "哈哈": "(直接删,不用替换)",
            "嘿嘿": "(删除)",
            "嘻嘻": "(删除)",
            "哎呀": "(删除)",
        }
        replacement = replacements.get(forbidden_word, "用更专业的表达")
        
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P1_HIGH",
            severity="中等",
            category="语气词",
            problem=f"使用了禁用语气词「{forbidden_word}」",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **替换**: 「{forbidden_word}」 → 「{replacement}」\n"
                f"  2. **prompt 加约束**: 在 system prompt 加'禁用「{forbidden_word}」'\n"
                f"  3. **输出后过滤**: 模型生成后用正则替换或删除"
            ),
            expected_impact="修复后 D3/D5 +2-3 分,提升专业感",
            example=f"❌ '好的，那我帮您...'  →  ✅ '嗯，那我帮您...'"
        )
    
    # 开场白合规
    if "开场白" in name or "首轮" in name:
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P0_CRITICAL",
            severity="严重",
            category="开场白",
            problem="开场白缺少必要变量（如姓名、时间）",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **模板化开场白**: '喂，是{{name}}吗？...{{time}}...'\n"
                f"  2. **检查变量字典**: 确保关键变量都传给了模型\n"
                f"  3. **prompt 强化**: 在 system prompt 加'第一句必须包含[姓名/时间/事由]'"
            ),
            expected_impact="修复后 D2 任务完成度 +5 分",
        )
    
    # 默认
    return Suggestion(
        constraint_id=constraint["id"],
        constraint_name=name,
        priority="P2_MEDIUM",
        severity="中等",
        category="语言规范",
        problem=verdict_result.reason or "语言规范违规",
        evidence=evidence[:150],
        how_to_fix="参照约束原文调整 prompt",
        expected_impact="修复后该约束 pass",
    )


def generate_for_state_tracker(constraint: dict, verdict_result, dialogue: dict) -> Suggestion:
    """state_tracker 类: 流程结构"""
    name = constraint.get("name", "")
    evidence = verdict_result.evidence or ""
    
    # S 开头的步骤
    step_match = re.match(r"S(\d+)", name)
    step_num = step_match.group(1) if step_match else "?"
    
    # 提取该步骤的核心动作
    # 例如 "S6 取消订单流程:引导商家在商家版APP操作取消订单" → 核心是"引导取消"
    core_action = name.split(":")[1] if ":" in name else name.split(" ", 1)[-1] if " " in name else name
    
    return Suggestion(
        constraint_id=constraint["id"],
        constraint_name=name,
        priority="P0_CRITICAL" if constraint.get("is_critical") else "P1_HIGH",
        severity="严重",
        category=f"流程步骤 S{step_num}",
        problem=f"缺失流程步骤 S{step_num} 的核心动作",
        evidence=evidence[:150],
        how_to_fix=(
            f"具体改进方法:\n"
            f"  1. **明确步骤目标**: S{step_num} 要做的是「{core_action[:50]}」\n"
            f"  2. **prompt 添加步骤指令**: 在 system prompt 列出完整 S1→S{step_num}→... 流程\n"
            f"  3. **检查触发条件**: 如果是分支(若X则Y), 看用户是否触发了 X\n"
            f"  4. **加状态记忆**: 让模型记住已走到哪个 step,避免跳步"
        ),
        expected_impact=f"修复后 D1 流程遵循度 +10-15 分",
        example=f"S{step_num} 核心动作示例: '{core_action[:60]}'"
    )


def generate_for_llm_extract(constraint: dict, verdict_result, dialogue: dict) -> Suggestion:
    """llm_extract_then_rule 类: 禁止承诺/越界处理"""
    name = constraint.get("name", "")
    evidence = verdict_result.evidence or ""
    
    # 禁止承诺
    if "承诺" in name or "保证" in name or "一定能" in name:
        # 提取承诺内容(折扣/补贴/赔付等)
        promise_targets = []
        for kw in ["折扣", "补贴", "赔付", "补偿", "优惠", "免单"]:
            if kw in name:
                promise_targets.append(kw)
        target_str = "/".join(promise_targets) if promise_targets else "金钱补偿"
        
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P0_CRITICAL",
            severity="致命",
            category="禁止承诺",
            problem=f"助手承诺了不该承诺的内容（{target_str}）",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **替换话术**: 把'我帮您申请补贴'改为'这超出我的权限,您可走平台申诉'\n"
                f"  2. **prompt 强化**: '禁止任何形式的{target_str}承诺,即使用户施压'\n"
                f"  3. **训练拒绝**: 在 fewshot 加'用户要补贴 → 助手拒绝并引导申诉'\n"
                f"  4. **后处理过滤**: 输出含'我帮您申请[补贴/折扣]'类正则模式 → 重新生成"
            ),
            expected_impact="修复后 D3 +5 分,避免客户/平台纠纷",
            example=f"❌ '我帮您申请50块超时补贴'  →  ✅ '补偿超出我权限,您可在 APP 申诉'"
        )
    
    # 越界处理
    if "越界" in name or "范围外" in name or "向同事确认" in name or "职责" in name:
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P1_HIGH",
            severity="严重",
            category="越界拒答",
            problem="对越界问题没有用规定话术应对",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **使用规定话术**: '这个我向同事确认后再回电' / '不在职责范围内'\n"
                f"  2. **prompt 加越界识别**: 列出'外平台/个人/工资/感情'等越界主题\n"
                f"  3. **训练'优雅拒绝'**: fewshot 包含'用户问越界 → 用模板话术'\n"
                f"  4. **拉回任务**: 拒答后立刻说'咱们继续说[任务主题]'"
            ),
            expected_impact="修复后 D3 +3-5 分,保持任务聚焦",
            example=f"用户:'你工资多少?' → 助手:'这个我向同事确认后再回电,咱们继续说培训'"
        )
    
    # 默认
    return Suggestion(
        constraint_id=constraint["id"],
        constraint_name=name,
        priority="P1_HIGH",
        severity="严重",
        category="事实约束",
        problem=verdict_result.reason or "事实性违规",
        evidence=evidence[:150],
        how_to_fix="按约束原文修正话术,可加 fewshot 强化",
        expected_impact="修复后该约束 pass",
    )


def generate_for_llm_judge(constraint: dict, verdict_result, dialogue: dict) -> Suggestion:
    """llm_judge 类: 主观判断 (口语化/重复/适时结束等)"""
    name = constraint.get("name", "")
    evidence = verdict_result.evidence or ""
    
    # 口语化
    if "口语" in name or "自然" in name or "随意" in name:
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P2_MEDIUM",
            severity="中等",
            category="语言风格",
            problem="语气不够口语化（偏书面/列点/文言）",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **加口语词**: 适当加'咱们/嗯/啊/吧/哈/嘞'\n"
                f"  2. **去列点**: 不用 '1./2./首先/其次/综上'\n"
                f"  3. **去文言**: 不用 '兹/便/若/之/望/敬请/务必'\n"
                f"  4. **短句优先**: 长句拆短,像电话沟通的口语"
            ),
            expected_impact="修复后 D5 对话质量 +5-8 分",
            example=f"❌ '兹通知您参加培训' → ✅ '通知您一下,咱们有个培训'"
        )
    
    # 避免重复
    if "重复" in name:
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P2_MEDIUM",
            severity="中等",
            category="重复回复",
            problem="多轮回复出现大段重复内容",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **检测前文**: 让模型每轮先回顾自己说过什么\n"
                f"  2. **换说法**: 同一信息用不同方式表达 (主动/被动/详略不同)\n"
                f"  3. **缩短重复**: 第二次提到的内容应该比第一次短\n"
                f"  4. **变量化**: 抽取已说过的关键信息存 state,不重复输出"
            ),
            expected_impact="修复后 D5 对话质量 +3-5 分",
            example=f"❌ T3说'带头盔工牌身份证', T7又说'带头盔工牌身份证'  →  ✅ T3详说, T7简提'别忘装备'"
        )
    
    # 适时结束
    if "结束" in name or "适时" in name or "终结" in name:
        return Suggestion(
            constraint_id=constraint["id"],
            constraint_name=name,
            priority="P2_MEDIUM",
            severity="中等",
            category="对话节奏",
            problem="对话拖沓,用户已表示结束后助手继续追问",
            evidence=evidence[:150],
            how_to_fix=(
                f"具体改进方法:\n"
                f"  1. **识别结束信号**: 用户说'好的/挂了/我先去忙了' → 立即收尾\n"
                f"  2. **1-2 轮内收尾**: 用'好的,辛苦您/再见/祝顺利'结束\n"
                f"  3. **不要追问**: 任务完成后不要再问'还有其他需要吗'\n"
                f"  4. **prompt 加 stop 条件**: 明确何时应该结束对话"
            ),
            expected_impact="修复后 D5 对话质量 +5 分",
            example=f"❌ '还有其他问题吗?...还有要确认的吗?...' → ✅ '好,那这样,再见'"
        )
    
    # 默认
    return Suggestion(
        constraint_id=constraint["id"],
        constraint_name=name,
        priority="P2_MEDIUM",
        severity="中等",
        category="对话质量",
        problem=verdict_result.reason or "主观判断违规",
        evidence=evidence[:150],
        how_to_fix="参考约束原文,在 prompt 中明确预期",
        expected_impact="修复后该约束 pass",
    )


# ============================================================
# 主入口
# ============================================================

def generate_suggestions(results: list, constraints: list, dialogue: dict, score_report: dict) -> List[Suggestion]:
    """从评测结果生成所有优化建议
    
    Args:
        results: pipeline 产出的 VerdictResult 列表
        constraints: 原始约束列表
        dialogue: 对话原文
        score_report: P3 评分结果(用于优先级排序)
    
    Returns:
        List[Suggestion] - 按优先级排序的建议
    """
    constraint_map = {c["id"]: c for c in constraints}
    
    suggestions = []
    for r in results:
        if r.verdict != "fail":
            continue  # 只对 fail 生成建议
        
        c = constraint_map.get(r.constraint_id)
        if not c:
            continue
        
        verifier_type = c.get("verifier", "")
        
        # 派发
        if verifier_type == "rule":
            sg = generate_for_rule(c, r, dialogue)
        elif verifier_type == "rule_pattern":
            sg = generate_for_rule_pattern(c, r, dialogue)
        elif verifier_type == "state_tracker":
            sg = generate_for_state_tracker(c, r, dialogue)
        elif verifier_type == "llm_extract_then_rule":
            sg = generate_for_llm_extract(c, r, dialogue)
        elif verifier_type == "llm_judge":
            sg = generate_for_llm_judge(c, r, dialogue)
        else:
            continue
        
        suggestions.append(sg)
    
    # 排序: priority + severity
    priority_order = {"P0_CRITICAL": 0, "P1_HIGH": 1, "P2_MEDIUM": 2, "P3_LOW": 3}
    severity_order = {"致命": 0, "严重": 1, "中等": 2, "轻微": 3}
    suggestions.sort(key=lambda s: (
        priority_order.get(s.priority, 99),
        severity_order.get(s.severity, 99)
    ))
    
    return suggestions


def suggestions_to_dict(suggestions: List[Suggestion]) -> List[dict]:
    """转 JSON 可序列化格式"""
    return [
        {
            "constraint_id": s.constraint_id,
            "constraint_name": s.constraint_name,
            "priority": s.priority,
            "severity": s.severity,
            "category": s.category,
            "problem": s.problem,
            "evidence": s.evidence,
            "how_to_fix": s.how_to_fix,
            "expected_impact": s.expected_impact,
            "example": s.example,
        }
        for s in suggestions
    ]


def suggestions_to_markdown(suggestions: List[Suggestion]) -> str:
    """转 Markdown 友好格式"""
    if not suggestions:
        return "✅ 该对话无违规,无需优化"
    
    lines = []
    lines.append(f"## 💡 优化建议（共 {len(suggestions)} 条）\n")
    
    # 按 category 分组
    from collections import defaultdict
    by_cat = defaultdict(list)
    for s in suggestions:
        by_cat[s.category].append(s)
    
    lines.append(f"**违规类别分布**:")
    for cat, items in by_cat.items():
        lines.append(f"- {cat}: {len(items)} 条")
    lines.append("")
    
    # 逐条详细
    for i, s in enumerate(suggestions, 1):
        emoji = "🔴" if s.priority == "P0_CRITICAL" else "🟠" if s.priority == "P1_HIGH" else "🟡"
        lines.append(f"### {i}. {emoji} [{s.priority}] {s.constraint_id}")
        lines.append(f"")
        lines.append(f"**问题**: {s.problem}")
        lines.append(f"**证据**: `{s.evidence}`")
        lines.append(f"**类别**: {s.category} | **严重度**: {s.severity}")
        lines.append(f"")
        lines.append(f"**改进方法**:")
        lines.append(s.how_to_fix)
        lines.append(f"")
        lines.append(f"**预期效果**: {s.expected_impact}")
        if s.example:
            lines.append(f"")
            lines.append(f"**示例**: {s.example}")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
    
    return "\n".join(lines)


# ============================================================
# 自测
# ============================================================

def _test():
    print("=" * 60)
    print("Suggestion Generator 自测")
    print("=" * 60)
    
    # 模拟 VerdictResult
    from dataclasses import dataclass
    @dataclass
    class FakeResult:
        constraint_id: str
        verdict: str
        verifier_type: str
        evidence: str = ""
        reason: str = ""
        confidence: float = 0.8
        constraint_name: str = ""
    
    # Test 1: 字数约束 fail
    constraints = [{
        "id": "V4_C01",
        "name": "每次回复控制在 15-20 字左右，保持精简。",
        "verifier": "rule",
        "is_critical": False,
        "scoring_dimension": "D3_constraint_compliance",
    }]
    result = FakeResult("V4_C01", "fail", "rule", 
                        evidence="T7=45字 T9=36字 T11=31字 违规率3/5=60%",
                        confidence=0.9)
    
    suggestions = generate_suggestions(
        [result], constraints, {}, {}
    )
    
    print(f"\n生成建议数: {len(suggestions)}")
    if suggestions:
        s = suggestions[0]
        print(f"\n建议 1:")
        print(f"  约束: {s.constraint_id}")
        print(f"  优先级: {s.priority}")
        print(f"  问题: {s.problem}")
        print(f"  改进方法:\n{s.how_to_fix}")
        print(f"  预期: {s.expected_impact}")
    
    # Test 2: 禁止承诺 fail
    constraints2 = [{
        "id": "V4_C08",
        "name": "绝不向商家承诺任何形式的折扣或者超时补贴。",
        "verifier": "llm_extract_then_rule",
        "is_critical": True,
        "scoring_dimension": "D3_constraint_compliance",
    }]
    result2 = FakeResult("V4_C08", "fail", "llm_extract_then_rule",
                         evidence="T7 助手说'我帮您申请50块超时补贴'",
                         reason="承诺了金钱补贴")
    
    suggestions2 = generate_suggestions([result2], constraints2, {}, {})
    if suggestions2:
        s = suggestions2[0]
        print(f"\n\n建议 2 (禁止承诺):")
        print(f"  约束: {s.constraint_id}")
        print(f"  优先级: {s.priority}")
        print(f"  问题: {s.problem}")
        print(f"  类别: {s.category}")
        print(f"  改进方法:\n{s.how_to_fix}")
        print(f"  示例: {s.example}")
    
    # Test 3: 转 markdown
    md = suggestions_to_markdown(suggestions + suggestions2)
    print(f"\n\nMarkdown 长度: {len(md)} 字")
    print(f"前 500 字预览:\n{md[:500]}")
    
    print(f"\n\n✅ 自测通过: {len(suggestions) + len(suggestions2)} 条建议生成成功")


if __name__ == "__main__":
    _test()
