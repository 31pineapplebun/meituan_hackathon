"""
优化建议生成器 (B2)

设计:
- 输入: verdict_details (含 fail 的约束 + evidence)
- 输出: 每条 fail → 一个具体可执行的改进建议

建议结构:
{
    "constraint_id": "V4_C01",
    "severity": "critical" | "major" | "minor",
    "category": "字数" | "禁用词" | "流程缺失" | "承诺违规" | "主观",
    "problem": "T7 字数 45 超 25 字阈",
    "root_cause": "助手在单轮塞入过多信息",
    "suggested_fix": "拆成两轮: T7 简短回答 + T9 补充细节",
    "example_after": "T7: '必须带头盔' / T9: '工牌身份证也要带'",  # 改后示例
    "expected_improvement": "字数违规率从 75% 降到 25%"
}

无需 LLM 调用, 纯模板 + 规则, ¥0 成本.
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any


# 严重度分级
SEVERITY_RULES = {
    # critical: red_line 或 critical 约束 fail
    # major: 客观规则 fail (字数/禁用词)
    # minor: 主观判断 fail
    "rule": "major",
    "rule_pattern": "major",
    "state_tracker": "critical",  # 流程缺失通常很严重
    "llm_extract_then_rule": "critical",  # 承诺/越界类
    "llm_judge": "minor",  # 主观类
}


def classify_severity(verdict: dict, constraint: dict) -> str:
    """决定严重度"""
    if constraint.get("is_critical"):
        return "critical"
    return SEVERITY_RULES.get(verdict.get("verifier_type"), "minor")


def categorize(constraint: dict) -> str:
    """约束分类 (中文展示)"""
    verifier = constraint.get("verifier", "")
    name = constraint.get("name", "")
    
    if verifier == "rule":
        if "字" in name:
            return "字数限制"
        if "变量" in name or "占位符" in name:
            return "变量替换"
        return "客观规则"
    elif verifier == "rule_pattern":
        if "好的" in name or "禁用" in name:
            return "禁用词"
        if "开场白" in name:
            return "开场白合规"
        return "格式规范"
    elif verifier == "state_tracker":
        return "流程结构"
    elif verifier == "llm_extract_then_rule":
        if "承诺" in name:
            return "禁止承诺"
        if "越界" in name or "范围" in name:
            return "越界处理"
        if "FAQ" in name or "知识" in name:
            return "知识准确"
        return "条件应答"
    elif verifier == "llm_judge":
        if "口语" in name or "自然" in name:
            return "口语化"
        if "重复" in name:
            return "避免重复"
        if "结束" in name or "终结" in name:
            return "适时结束"
        if "暂停" in name or "发言" in name:
            return "对话节奏"
        if "核心" in name or "任务完成" in name:
            return "任务完整性"
        return "主观判断"
    return "其他"


# ============================================================
# 各类型的建议生成
# ============================================================

def _suggest_word_limit(verdict, constraint, dialogue):
    """字数违规 (rule 类) 的具体建议"""
    name = constraint.get("name", "")
    
    # 从约束名提取字数限制
    m = re.search(r"(\d+)-(\d+)\s*字", name)
    if m:
        lower, upper = int(m.group(1)), int(m.group(2))
        soft_limit = upper + 5
    else:
        m = re.search(r"(\d+)\s*字", name)
        if m:
            upper = int(m.group(1))
            lower = upper - 10
            soft_limit = upper + 5
        else:
            upper, lower, soft_limit = 30, 20, 35
    
    # 从 evidence 提取超字数的具体 turn
    evidence = verdict.get("evidence", "")
    
    # 解析格式如 "turn7=45字; turn3=37字; turn9=31字"
    over_turns = []
    for match in re.finditer(r"[Tt]urn?\s*(\d+)\s*=?\s*(\d+)\s*字", evidence):
        turn_n = int(match.group(1))
        chars = int(match.group(2))
        if chars > soft_limit:
            over_turns.append((turn_n, chars))
    
    if not over_turns:
        return {
            "problem": f"字数约束违规 ({upper} 字限,允许 {soft_limit} 字软上限)",
            "suggested_fix": f"控制每轮助手回复在 {upper} 字以内",
            "example_after": f"短句: '收到, 还需多久能出餐?' (12 字, 合规)",
            "expected_improvement": "字数违规率显著降低"
        }
    
    # 找最严重的一个 turn 给具体建议
    over_turns.sort(key=lambda x: -x[1])
    worst_turn, worst_chars = over_turns[0]
    
    # 找原文
    turn_content = ""
    for t in dialogue.get("turns", []):
        if t.get("turn") == worst_turn and t.get("role") == "assistant":
            turn_content = t.get("content", "")
            break
    
    # 给拆分建议
    if turn_content:
        # 简单拆: 找逗号/句号位置分两半
        mid = len(turn_content) // 2
        # 找最近的标点
        split_pos = mid
        for delim in ["。", "，", "；"]:
            pos = turn_content.rfind(delim, 0, mid + 10)
            if pos > 0:
                split_pos = pos + 1
                break
        
        part1 = turn_content[:split_pos].strip()
        part2 = turn_content[split_pos:].strip()
        
        example_after = f"原 T{worst_turn} ({worst_chars}字) → 拆成:\n  • T{worst_turn}: '{part1}' ({len(part1)}字)\n  • T{worst_turn+2}: '{part2}' ({len(part2)}字)"
    else:
        example_after = f"将 T{worst_turn} 拆成两轮,各 ≤ {upper} 字"
    
    return {
        "problem": f"{len(over_turns)} 处超 {soft_limit} 字 (最严重: T{worst_turn} = {worst_chars} 字)",
        "root_cause": "助手在单轮塞入过多信息,缺乏'一轮一焦点'意识",
        "suggested_fix": f"将长 turn 拆成 2-3 个连续短 turn,每轮聚焦 1 个信息点",
        "example_after": example_after,
        "expected_improvement": f"字数违规率从当前 → 0%"
    }


def _suggest_forbidden_words(verdict, constraint, dialogue):
    """禁用词违规 (rule_pattern 类)"""
    name = constraint.get("name", "")
    evidence = verdict.get("evidence", "")
    
    # 从约束名提取禁用词
    forbidden = []
    for w in ["好的", "哈哈", "嘿嘿", "嘻嘻"]:
        if w in name:
            forbidden.append(w)
    
    # 替代词
    alternatives = {
        "好的": "好/行/明白/收到",
        "哈哈": "(去掉,改用陈述句)",
        "嘿嘿": "(去掉)",
    }
    
    # 从 evidence 找具体哪轮
    turn_match = re.search(r"T(\d+).*?['\"]?(好的|哈哈|嘿嘿|嘻嘻)['\"]?", evidence)
    if turn_match:
        turn_n = turn_match.group(1)
        word = turn_match.group(2)
        suggestion = alternatives.get(word, f"替代用 '行' 或 '明白'")
        
        # 找原文
        turn_content = ""
        for t in dialogue.get("turns", []):
            if t.get("turn") == int(turn_n) and t.get("role") == "assistant":
                turn_content = t.get("content", "")
                break
        
        example = f"T{turn_n} 原: '{turn_content[:60]}...'\n→ 改为: '{turn_content.replace(word, suggestion.split('/')[0], 1)[:60]}...'"
    else:
        word = ", ".join(forbidden) if forbidden else "禁用词"
        suggestion = "用 '行/明白/收到/嗯'"
        example = f"将 '好的' 换成 '行' 或 '收到'"
    
    return {
        "problem": f"使用了约束禁用的语气词: {evidence[:60]}",
        "root_cause": "助手用了不专业的语气词,违反指令规范",
        "suggested_fix": f"替换为: {suggestion}",
        "example_after": example,
        "expected_improvement": "禁用词违规消除"
    }


def _suggest_step_missing(verdict, constraint, dialogue):
    """流程 Step 缺失 (state_tracker 类)"""
    name = constraint.get("name", "")
    
    # 从约束名提取 step 信息
    step_match = re.search(r"(S\d+)\s*[:：]?\s*(.+)", name)
    if step_match:
        step_id = step_match.group(1)
        step_desc = step_match.group(2)[:50]
    else:
        step_id = "Step"
        step_desc = name[:50]
    
    # 给具体话术示例 (按 step 类型)
    template_lookup = {
        "S1": {
            "自我介绍": "话术: '喂,您好,我是美团客服 [姓名],请问是负责人吗?'",
            "告知": "话术: '通知您一个事——[任务核心],截止 [时间]'",
        },
        "S2": {
            "告知": "话术: '近 7 天您有 X 条差评,主要原因是 [具体]'",
            "询问": "话术: '请问您当前 APP 版本号是?'",
        },
        "S6": {
            "取消": "话术: '麻烦您在商家版 APP > 订单管理 > 找到该单 > 点击取消'",
        },
        "S7": {
            "结束": "话术: '行,那就这样,辛苦您配合,再见'",
        },
    }
    
    example_after = ""
    for key, templates in template_lookup.items():
        if step_id == key:
            for kw, template in templates.items():
                if kw in step_desc:
                    example_after = template
                    break
            break
    
    if not example_after:
        example_after = f"在对话流程中加入 '{step_desc[:40]}' 步骤的具体话术"
    
    return {
        "problem": f"{step_id} 缺失或不完整: {step_desc}",
        "root_cause": "助手未按指令规定的流程顺序执行,跳过了关键步骤",
        "suggested_fix": f"在对话中明确执行 {step_id},不要省略",
        "example_after": example_after,
        "expected_improvement": f"流程完整度提升,D1 维度分提升"
    }


def _suggest_no_promise(verdict, constraint, dialogue):
    """禁止承诺违规 (llm_extract 类)"""
    evidence = verdict.get("evidence", "")
    
    return {
        "problem": f"承诺了禁止内容: {evidence[:80]}",
        "root_cause": "助手对用户的诉求过度让步,做出超出权限的承诺",
        "suggested_fix": "明确拒绝承诺,引导到合规渠道",
        "example_after": (
            "❌ 错误: '我帮您申请 50 块补贴'\n"
            "✅ 改为: '补偿超出我的权限,您可以在商家后台 > 我的 > 投诉申诉报备'"
        ),
        "expected_improvement": "消除合规风险,符合权责边界"
    }


def _suggest_out_of_scope(verdict, constraint, dialogue):
    """越界处理违规 (llm_extract 类)"""
    return {
        "problem": "用户问越界问题时未用标准话术",
        "root_cause": "助手直接回答了不在职责范围内的问题",
        "suggested_fix": "对越界问题统一用 '我向同事确认后回电' 或 '这个不在我的职责范围'",
        "example_after": (
            "用户: '你工资多少?'\n"
            "❌ 错误: '保密啊,咱说培训的事'\n"
            "✅ 改为: '这个我向同事确认后回电,咱先继续培训的事'"
        ),
        "expected_improvement": "保持专业边界,不被用户带跑题"
    }


def _suggest_oral_natural(verdict, constraint, dialogue):
    """口语化不足"""
    evidence = verdict.get("evidence", "")
    return {
        "problem": f"语言不够口语化: {evidence[:60]}",
        "root_cause": "助手用了书面文言词或过于规整的列点格式",
        "suggested_fix": "1) 去掉列点 (1./2./首先/其次) 2) 加口语词 (咱们/嗯/啊/吧) 3) 用短句",
        "example_after": (
            "❌ 书面: '请您按以下事项准备: 1. 头盔 2. 工牌 3. 身份证'\n"
            "✅ 口语: '记得带上头盔、工牌、身份证哈'"
        ),
        "expected_improvement": "D5 对话质量提升"
    }


def _suggest_repeat(verdict, constraint, dialogue):
    """重复回复"""
    evidence = verdict.get("evidence", "")
    return {
        "problem": f"对话内容重复: {evidence[:80]}",
        "root_cause": "助手在多轮中重复同样信息,缺乏变化",
        "suggested_fix": "1) 关键信息只说一次 2) 重申时改用其他角度 3) 用代词替代",
        "example_after": (
            "❌ T1+T5+T7 都说 '带头盔工牌身份证'\n"
            "✅ T1 详细说,T5 用 '别忘了三件套',T7 不再重复"
        ),
        "expected_improvement": "避免冗余,D5 对话质量提升"
    }


def _suggest_timely_end(verdict, constraint, dialogue):
    """适时结束"""
    return {
        "problem": "对话拖延或未自然结束",
        "root_cause": "用户已示意结束,助手仍反复追问 '还有其他需要吗'",
        "suggested_fix": "用户说 '我先挂了/我先忙了' 后 1 轮内收尾",
        "example_after": (
            "用户: '行,我知道了'\n"
            "❌ 错误: '还有其他需要吗?有问题随时找我...'\n"
            "✅ 改为: '行,那就这样,辛苦您配合,再见'"
        ),
        "expected_improvement": "对话长度合理,D5 提升"
    }


def _suggest_core_intent(verdict, constraint, dialogue):
    """任务核心意图未完成"""
    return {
        "problem": "任务核心步骤未完成或反馈不明确",
        "root_cause": "助手未覆盖指令规定的核心动作",
        "suggested_fix": "回看指令的 Task 描述,确认对话中是否覆盖所有核心步骤",
        "example_after": (
            "V2 任务: 通知更新 + 引导操作 + 截止时间 + 确认接单\n"
            "缺哪个就补哪个"
        ),
        "expected_improvement": "D2 任务完成度提升"
    }


# ============================================================
# 主入口
# ============================================================

# 分发字典: 约束分类 → 建议生成函数
SUGGESTION_DISPATCH = {
    "字数限制": _suggest_word_limit,
    "禁用词": _suggest_forbidden_words,
    "流程结构": _suggest_step_missing,
    "禁止承诺": _suggest_no_promise,
    "越界处理": _suggest_out_of_scope,
    "口语化": _suggest_oral_natural,
    "避免重复": _suggest_repeat,
    "适时结束": _suggest_timely_end,
    "任务完整性": _suggest_core_intent,
}


def generate_suggestions(verdict_details: List[Dict], 
                          constraints: List[Dict],
                          dialogue: Dict) -> List[Dict]:
    """主函数: 给所有 fail 生成具体建议
    
    Args:
        verdict_details: pipeline 输出的 verdict 列表 (含 fail)
        constraints: 指令的约束清单 (含 is_critical 等元信息)
        dialogue: 对话原文
    
    Returns:
        suggestions: 排序后的建议列表
    """
    # 约束 ID → 完整约束信息
    constraint_lookup = {c["id"]: c for c in constraints}
    
    suggestions = []
    for v in verdict_details:
        if v.get("verdict") != "fail":
            continue
        
        cid = v.get("constraint_id")
        constraint = constraint_lookup.get(cid, {})
        if not constraint:
            continue
        
        category = categorize(constraint)
        severity = classify_severity(v, constraint)
        
        # 分发到对应的建议生成器
        generator = SUGGESTION_DISPATCH.get(category)
        if generator:
            details = generator(v, constraint, dialogue)
        else:
            details = {
                "problem": f"违反约束: {constraint.get('name', '')[:60]}",
                "root_cause": v.get("reason", "未知")[:100],
                "suggested_fix": "请参照约束原文调整对话",
                "example_after": "(暂无模板)",
                "expected_improvement": "约束遵守度提升"
            }
        
        suggestion = {
            "constraint_id": cid,
            "constraint_name": constraint.get("name", "")[:80],
            "severity": severity,
            "category": category,
            "is_critical": constraint.get("is_critical", False),
            "dimension": constraint.get("scoring_dimension", "?"),
            "evidence": v.get("evidence", "")[:200],
            **details
        }
        suggestions.append(suggestion)
    
    # 排序: critical 优先, 然后 major, 最后 minor
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    suggestions.sort(key=lambda s: (severity_order.get(s["severity"], 3), s["constraint_id"]))
    
    return suggestions


def format_suggestions_markdown(suggestions: List[Dict]) -> str:
    """渲染成 markdown 给报告用"""
    if not suggestions:
        return "## 🎉 没有违规,无需改进\n"
    
    lines = []
    lines.append(f"# 优化建议 ({len(suggestions)} 条)\n")
    
    # 按严重度分组
    by_sev = {"critical": [], "major": [], "minor": []}
    for s in suggestions:
        by_sev[s["severity"]].append(s)
    
    sev_emoji = {"critical": "🔴", "major": "🟡", "minor": "🟢"}
    sev_name = {"critical": "严重", "major": "重要", "minor": "轻微"}
    
    for sev in ["critical", "major", "minor"]:
        items = by_sev[sev]
        if not items:
            continue
        lines.append(f"## {sev_emoji[sev]} {sev_name[sev]}问题 ({len(items)} 条)\n")
        
        for i, s in enumerate(items, 1):
            lines.append(f"### {i}. [{s['constraint_id']}] {s['category']}: {s['constraint_name'][:50]}")
            lines.append("")
            lines.append(f"**问题**: {s['problem']}")
            lines.append("")
            if s.get("root_cause"):
                lines.append(f"**根因**: {s['root_cause']}")
                lines.append("")
            lines.append(f"**改进**: {s['suggested_fix']}")
            lines.append("")
            if s.get("example_after"):
                lines.append("**改后示例**:")
                lines.append("```")
                lines.append(s['example_after'])
                lines.append("```")
                lines.append("")
            if s.get("expected_improvement"):
                lines.append(f"**预期效果**: {s['expected_improvement']}")
                lines.append("")
            lines.append("---")
            lines.append("")
    
    return "\n".join(lines)


# ============================================================
# 自测
# ============================================================

def _test():
    """单元测试"""
    print("=" * 60)
    print("优化建议生成器自测")
    print("=" * 60)
    
    # 用 V4 违规对话测试
    base = Path(__file__).parent
    with open(base / "example_reports" / "v4_violation_dialogue.json", encoding="utf-8") as f:
        report = json.load(f)
    
    with open(base.parent / "08_parser" / "parsed_examples" / "v4_parsed.json", encoding="utf-8") as f:
        instr = json.load(f)
    
    with open(base / "test_data" / "v4_cooperative_violation.jsonl", encoding="utf-8") as f:
        dialogue = json.loads(f.readline())
    
    suggestions = generate_suggestions(
        report["verdict_details"],
        instr["atomic_constraints"],
        dialogue
    )
    
    print(f"\n生成了 {len(suggestions)} 条建议:")
    for i, s in enumerate(suggestions, 1):
        emoji = {"critical": "🔴", "major": "🟡", "minor": "🟢"}.get(s["severity"], "⚪")
        print(f"\n  {i}. {emoji} {s['constraint_id']} ({s['category']})")
        print(f"     问题: {s['problem'][:70]}")
        print(f"     改进: {s['suggested_fix'][:70]}")
    
    # 渲染 markdown
    md = format_suggestions_markdown(suggestions)
    out_path = base / "example_reports" / "v4_suggestions_demo.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\n✓ Markdown 报告: {out_path}")
    
    # 验证关键 case
    assert len(suggestions) > 0, "没生成建议"
    
    # 应该有 V4_C20 (S6 取消订单) 的 critical 建议
    v4_c20 = [s for s in suggestions if s["constraint_id"] == "V4_C20"]
    if v4_c20:
        assert v4_c20[0]["severity"] == "critical", f"V4_C20 应该是 critical, 实际 {v4_c20[0]['severity']}"
        print(f"✓ V4_C20 正确标为 critical")
    
    # 应该有 V4_C01 (字数) 建议
    v4_c01 = [s for s in suggestions if s["constraint_id"] == "V4_C01"]
    if v4_c01:
        assert "字" in v4_c01[0]["category"], f"V4_C01 应该是字数类"
        print(f"✓ V4_C01 字数建议正确生成")
    
    print(f"\n✅ 测试通过")
    return True


if __name__ == "__main__":
    _test()
