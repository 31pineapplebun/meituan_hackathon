"""
端到端评测 Pipeline - Day 7 MVP

输入:
- 已解析指令 JSON (08_parser/parsed_examples/v1_parsed.json)
- 对话 JSONL 中的一通对话

流程:
1. 加载约束清单
2. 对每条约束跑对应 verifier
3. 收集结果 → P3 评分算法
4. 生成 JSON + Markdown 报告

输出:
- score_report.json (机器友好)
- score_report.md   (人类可读)
"""
import argparse
import json
import sys
from pathlib import Path
from dataclasses import asdict
from collections import Counter

# 引入 verifier
sys.path.insert(0, str(Path(__file__).parent))
from verifier_base import dispatch, list_registered, VerdictResult
import verifiers              # 触发 rule + rule_pattern @register
import verifier_state_tracker  # 触发 state_tracker @register (Day 8 新增)
import verifier_llm_extract    # 触发 llm_extract_then_rule @register (Day 9.1 新增)
import verifier_llm_judge      # 触发 llm_judge @register (Day 9.2 新增)


# ============================================================
# 加载数据
# ============================================================

def load_instruction(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_dialogue(path: str, dialogue_id: str = None) -> dict:
    """从 JSONL 加载一通对话.
    
    dialogue_id 为 None 时取第一通.
    """
    dialogues = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            dialogues.append(d)
    
    if not dialogues:
        raise ValueError(f"{path} 无任何对话")
    
    if dialogue_id:
        for d in dialogues:
            if d.get("dialogue_id") == dialogue_id:
                return d
        raise ValueError(f"未找到对话 {dialogue_id}")
    
    return dialogues[0]


# ============================================================
# Pipeline 主体
# ============================================================

def run_pipeline(instruction: dict, dialogue: dict) -> dict:
    """跑完整 pipeline, 返回结构化结果"""
    
    constraints = instruction.get("atomic_constraints", [])
    if not constraints:
        return {"error": "指令无约束"}
    
    # 1. 跑所有 verifier
    results = []
    for c in constraints:
        verdict_result = dispatch(c, dialogue, instruction)
        results.append(verdict_result)
    
    # 2. P3 评分（先简化版: 不依赖 scoring_validation.py, 直接复刻逻辑）
    score_report = compute_p3_score(results, constraints)
    
    # 2.5 生成详细优化建议 (B2 新增)
    try:
        from suggestion_generator import generate_suggestions, suggestions_to_dict
        detailed_suggestions = generate_suggestions(results, constraints, dialogue, score_report)
        detailed_suggestions_dict = suggestions_to_dict(detailed_suggestions)
    except Exception as e:
        print(f"  ⚠️ 详细建议生成失败 (不影响评分): {e}")
        detailed_suggestions_dict = []
    
    # 3. 组装最终输出
    output = {
        "dialogue_id": dialogue.get("dialogue_id"),
        "instruction_id": instruction.get("meta", {}).get("instruction_id") if isinstance(instruction.get("meta"), dict) else instruction.get("instruction_id"),
        "score_report": score_report,
        "detailed_suggestions": detailed_suggestions_dict,  # B2 新增
        "verdict_details": [r.to_dict() for r in results],
        "stats": {
            "total_constraints": len(constraints),
            "pass": sum(1 for r in results if r.verdict == "pass"),
            "fail": sum(1 for r in results if r.verdict == "fail"),
            "na": sum(1 for r in results if r.verdict == "na"),
            "not_implemented": sum(1 for r in results if r.verdict == "not_implemented"),
            "error": sum(1 for r in results if r.verdict == "error"),
        }
    }
    return output


# ============================================================
# P3 评分（D + P1 + P2）—— Day 2 已验证的算法
# ============================================================

DIM_WEIGHTS = {
    "D1_flow_compliance": 0.25,
    "D2_task_completion": 0.25,
    "D3_constraint_compliance": 0.20,
    "D4_knowledge_accuracy": 0.15,
    "D5_dialogue_quality": 0.15,
}

DIM_NAMES = {
    "D1_flow_compliance": "流程遵循度",
    "D2_task_completion": "任务完成度",
    "D3_constraint_compliance": "约束遵循度",
    "D4_knowledge_accuracy": "知识准确性",
    "D5_dialogue_quality": "对话质量",
}

# 红线约束（违反钳制 ≤ 40）—— 默认空，后续指令可以标记
DEFAULT_RED_LINES = set()


def compute_p3_score(results: list, constraints: list) -> dict:
    """P3 三层防御评分:
    1. D方案: 维度加权
    2. P1: Critical Gating
    3. P2: Red line 钳制
    """
    # 构建 id → constraint dict
    c_by_id = {c["id"]: c for c in constraints}
    
    # 只把 verdict in {pass, fail} 的算入分母, na/not_implemented/error 跳过
    counted_results = [r for r in results if r.verdict in ("pass", "fail")]
    
    if not counted_results:
        return {
            "final_score": 0,
            "raw_score": 0,
            "ceiling": 0,
            "ceiling_reason": "无可计分的约束",
            "dim_scores": {k: None for k in DIM_WEIGHTS},
            "critical_pass_rate": None,
            "red_line_violations": [],
            "suggestions": ["pipeline 无有效结果，建议检查 verifier 实现"]
        }
    
    # === Step 1-2: D方案 维度加权 ===
    by_dim = {}
    for r in counted_results:
        c = c_by_id.get(r.constraint_id, {})
        dim = c.get("scoring_dimension", "")
        if dim not in DIM_WEIGHTS:
            continue
        by_dim.setdefault(dim, []).append((r, c))
    
    dim_scores = {}
    for dim_id in DIM_WEIGHTS:
        items = by_dim.get(dim_id, [])
        if not items:
            dim_scores[dim_id] = None
            continue
        passed_weight = sum(c.get("weight", 1) for r, c in items if r.verdict == "pass")
        total_weight = sum(c.get("weight", 1) for r, c in items)
        dim_scores[dim_id] = round(passed_weight / total_weight * 100, 2) if total_weight else 0
    
    raw_score = 0
    for dim_id, score in dim_scores.items():
        if score is not None:
            raw_score += score * DIM_WEIGHTS[dim_id]
    
    # 如果某些维度无数据，权重要重新归一化（不然分数偏低）
    used_weight_total = sum(DIM_WEIGHTS[d] for d, s in dim_scores.items() if s is not None)
    if used_weight_total > 0 and used_weight_total < 1.0:
        raw_score = raw_score / used_weight_total
    
    raw_score = round(raw_score, 2)
    
    # === Step 3: P1 Critical Gating ===
    critical_results = [r for r in counted_results 
                         if c_by_id.get(r.constraint_id, {}).get("is_critical")]
    if critical_results:
        critical_pass_rate = sum(1 for r in critical_results if r.verdict == "pass") / len(critical_results)
    else:
        critical_pass_rate = 1.0
    
    if critical_pass_rate >= 1.0:
        critical_ceiling = 100
    elif critical_pass_rate >= 0.9:
        critical_ceiling = 85
    elif critical_pass_rate >= 0.7:
        critical_ceiling = 65
    elif critical_pass_rate >= 0.5:
        critical_ceiling = 45
    else:
        critical_ceiling = 30
    
    # === Step 4: P2 Red Line ===
    red_line_violations = [r.constraint_id for r in counted_results 
                           if c_by_id.get(r.constraint_id, {}).get("is_red_line") and r.verdict == "fail"]
    red_line_ceiling = 40 if red_line_violations else 100
    
    ceiling = min(critical_ceiling, red_line_ceiling)
    final_score = round(min(raw_score, ceiling), 2)
    
    # === 钳制原因 ===
    if red_line_violations:
        ceiling_reason = f"红线违规({len(red_line_violations)}条): {','.join(red_line_violations)} → 钳制≤40"
    elif critical_ceiling < 100:
        ceiling_reason = f"Critical通过率{critical_pass_rate*100:.0f}% → 上限{critical_ceiling}"
    else:
        ceiling_reason = "无钳制"
    
    # === 优化建议 ===
    suggestions = []
    
    # 1) 红线
    if red_line_violations:
        suggestions.append({
            "priority": "P0_RED_LINE",
            "msg": f"🚨 红线违规! 此类违规直接钳制分数≤40",
            "constraint_ids": red_line_violations,
        })
    
    # 2) Critical 失败
    critical_fails = [r for r in counted_results 
                       if c_by_id.get(r.constraint_id, {}).get("is_critical")
                       and r.verdict == "fail"
                       and r.constraint_id not in red_line_violations]
    if critical_fails:
        suggestions.append({
            "priority": "P0_CRITICAL",
            "msg": f"{len(critical_fails)} 条关键约束失败",
            "constraint_ids": [r.constraint_id for r in critical_fails],
        })
    
    # 3) 最低维度
    valid_dims = {k: v for k, v in dim_scores.items() if v is not None}
    if valid_dims:
        worst_dim = min(valid_dims, key=valid_dims.get)
        if valid_dims[worst_dim] < 80:
            failed_in_worst = [r for r in counted_results 
                                if c_by_id.get(r.constraint_id, {}).get("scoring_dimension") == worst_dim
                                and r.verdict == "fail"]
            if failed_in_worst:
                suggestions.append({
                    "priority": "P1_DIM",
                    "msg": f"维度【{DIM_NAMES[worst_dim]}】得分 {valid_dims[worst_dim]:.1f}/100 最低",
                    "constraint_ids": [r.constraint_id for r in failed_in_worst],
                })
    
    return {
        "final_score": final_score,
        "raw_score": raw_score,
        "ceiling": ceiling,
        "ceiling_reason": ceiling_reason,
        "dim_scores": dim_scores,
        "critical_pass_rate": round(critical_pass_rate, 3),
        "red_line_violations": red_line_violations,
        "suggestions": suggestions,
    }


# ============================================================
# 报告生成
# ============================================================

def render_markdown_report(output: dict, instruction: dict, dialogue: dict) -> str:
    """生成人类可读 Markdown 报告"""
    sr = output["score_report"]
    stats = output["stats"]
    
    lines = []
    lines.append(f"# 评分报告 - {output['dialogue_id']}")
    lines.append("")
    lines.append(f"> **指令**: {output['instruction_id']}")
    lines.append(f"> **生成时间**: Day 7 MVP")
    lines.append("")
    
    # === 核心分数 ===
    lines.append("## 📊 评分总览")
    lines.append("")
    lines.append(f"### **最终得分: {sr['final_score']} / 100**")
    lines.append("")
    lines.append(f"| 维度 | 得分 |")
    lines.append(f"|---|---|")
    lines.append(f"| 原始分数 (D 方案) | {sr['raw_score']} |")
    lines.append(f"| 上限钳制 | {sr['ceiling']} |")
    lines.append(f"| 钳制原因 | {sr['ceiling_reason']} |")
    lines.append(f"| Critical 通过率 | {sr['critical_pass_rate']*100:.1f}% |")
    if sr['red_line_violations']:
        lines.append(f"| 🚨 红线违规 | {len(sr['red_line_violations'])} 条 |")
    lines.append("")
    
    # === 维度分布 ===
    lines.append("## 📐 5 维度得分")
    lines.append("")
    lines.append("| 维度 | 名称 | 权重 | 得分 |")
    lines.append("|---|---|---|---|")
    for dim_id, weight in DIM_WEIGHTS.items():
        score = sr['dim_scores'].get(dim_id)
        score_str = f"{score:.1f}" if score is not None else "N/A (无数据)"
        lines.append(f"| {dim_id} | {DIM_NAMES[dim_id]} | {weight*100:.0f}% | {score_str} |")
    lines.append("")
    
    # === 约束执行统计 ===
    lines.append("## 🔍 约束执行情况")
    lines.append("")
    lines.append(f"| 状态 | 数量 |")
    lines.append(f"|---|---|")
    lines.append(f"| 总约束 | {stats['total_constraints']} |")
    lines.append(f"| ✅ pass | {stats['pass']} |")
    lines.append(f"| ❌ fail | {stats['fail']} |")
    lines.append(f"| ➖ na (未触发) | {stats['na']} |")
    lines.append(f"| ⏳ not_implemented | {stats['not_implemented']} |")
    if stats['error']:
        lines.append(f"| 🐛 error | {stats['error']} |")
    lines.append("")
    
    # === 优化建议 (B2: 用详细建议替代简单提示) ===
    detailed = output.get("detailed_suggestions", [])
    if detailed:
        lines.append("## 💡 详细优化建议")
        lines.append("")
        try:
            from suggestion_generator import Suggestion
            # 重新构造 Suggestion 对象用 to_markdown
            from suggestion_generator import suggestions_to_markdown
            # detailed 是 list of dict, 转回 Suggestion
            suggestions = []
            for d in detailed:
                s = Suggestion(
                    constraint_id=d["constraint_id"],
                    constraint_name=d["constraint_name"],
                    priority=d["priority"],
                    severity=d.get("severity", "中等"),
                    category=d.get("category", ""),
                    problem=d.get("problem", ""),
                    evidence=d.get("evidence", ""),
                    how_to_fix=d.get("how_to_fix", ""),
                    expected_impact=d.get("expected_impact", ""),
                    example=d.get("example"),
                )
                suggestions.append(s)
            md_suggestions = suggestions_to_markdown(suggestions)
            lines.append(md_suggestions)
        except Exception as e:
            # 兜底: 用旧版简单提示
            lines.append(f"_(详细建议生成失败: {e})_")
            for i, sg in enumerate(sr.get('suggestions', []), 1):
                lines.append(f"### {i}. [{sg['priority']}] {sg['msg']}")
        lines.append("")
    elif sr.get('suggestions'):
        # 没 detailed,fallback 旧版
        lines.append("## 💡 优化方向")
        lines.append("")
        for i, sg in enumerate(sr['suggestions'], 1):
            lines.append(f"### {i}. [{sg['priority']}] {sg['msg']}")
            if sg.get('constraint_ids'):
                for cid in sg['constraint_ids']:
                    detail = next((d for d in output['verdict_details'] 
                                    if d['constraint_id'] == cid), None)
                    if detail:
                        lines.append(f"   - **{cid}**: {detail.get('constraint_name', '?')}")
                        if detail.get('evidence'):
                            lines.append(f"     - 证据: {detail['evidence']}")
                        if detail.get('reason'):
                            lines.append(f"     - 原因: {detail['reason']}")
            lines.append("")
    
    # === 详细判定（折叠区） ===
    lines.append("## 📋 所有约束判定明细")
    lines.append("")
    lines.append("| 约束 ID | 名称 | Verifier | Verdict | 证据 |")
    lines.append("|---|---|---|---|---|")
    for d in output['verdict_details']:
        emoji = {"pass": "✅", "fail": "❌", "na": "➖", "not_implemented": "⏳", "error": "🐛"}.get(d['verdict'], "?")
        evidence = (d.get('evidence', '') or d.get('reason', ''))[:60]
        lines.append(f"| {d['constraint_id']} | {d['constraint_name'][:30]} | {d['verifier_type']} | {emoji} {d['verdict']} | {evidence} |")
    
    return "\n".join(lines)


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="端到端评测 Pipeline")
    parser.add_argument("--instruction", required=True, help="解析好的指令 JSON")
    parser.add_argument("--dialogue", required=True, help="对话 JSONL")
    parser.add_argument("--dialogue_id", help="指定对话 ID(默认取第一通)")
    parser.add_argument("--output_dir", default=".", help="输出目录")
    args = parser.parse_args()
    
    print("=" * 70)
    print("端到端评测 Pipeline - Day 7 MVP")
    print("=" * 70)
    
    print(f"\n[1/4] 加载数据")
    instruction = load_instruction(args.instruction)
    dialogue = load_dialogue(args.dialogue, args.dialogue_id)
    
    instruction_id = instruction.get("meta", {}).get("instruction_id") if isinstance(instruction.get("meta"), dict) else instruction.get("instruction_id")
    print(f"  指令: {instruction_id}")
    print(f"  对话: {dialogue.get('dialogue_id')}")
    print(f"  约束数: {len(instruction.get('atomic_constraints', []))}")
    print(f"  对话轮数: {len(dialogue.get('turns', []))}")
    
    print(f"\n[2/4] 已注册 verifier: {list_registered()}")
    
    print(f"\n[3/4] 跑 pipeline")
    output = run_pipeline(instruction, dialogue)
    
    print(f"\n[4/4] 生成报告")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = output_dir / f"score_report_{dialogue.get('dialogue_id')}.json"
    md_path = output_dir / f"score_report_{dialogue.get('dialogue_id')}.md"
    html_path = output_dir / f"score_report_{dialogue.get('dialogue_id')}.html"
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    md_content = render_markdown_report(output, instruction, dialogue)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    # B3 新增: 自动生成 HTML 报告
    try:
        from html_report import generate_html_report
        html_content = generate_html_report(output, instruction)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception as e:
        print(f"  ⚠️ HTML 报告生成失败 (不影响 JSON/MD): {e}")
        html_path = None
    
    # 终端摘要
    sr = output["score_report"]
    stats = output["stats"]
    
    print()
    print("=" * 70)
    print(f"评分结果: {sr['final_score']} / 100")
    print("=" * 70)
    print(f"  原始分数: {sr['raw_score']}")
    print(f"  上限钳制: {sr['ceiling']} ({sr['ceiling_reason']})")
    print(f"  Critical 通过率: {sr['critical_pass_rate']*100:.1f}%")
    print()
    print(f"  统计: pass={stats['pass']}, fail={stats['fail']}, "
          f"na={stats['na']}, not_implemented={stats['not_implemented']}")
    print(f"\n  维度分:")
    for dim_id, score in sr['dim_scores'].items():
        if score is not None:
            bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
            print(f"    {DIM_NAMES[dim_id]:8s}: {bar} {score:.1f}")
        else:
            print(f"    {DIM_NAMES[dim_id]:8s}: -- (无可评估约束)")
    print()
    print(f"输出文件:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    if html_path:
        print(f"  HTML: {html_path}  ← 用浏览器打开看精美报告")


if __name__ == "__main__":
    main()
