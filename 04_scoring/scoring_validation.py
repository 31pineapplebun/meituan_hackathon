"""
评分算法 v2 - P3方案
- P1: 调严Critical Gating阈值
- P2: 引入红线即死(red_line)机制

修订点:
1. 部分critical约束升级为red_line（任何一条失败，分数钳制≤50）
2. Critical Gating阈值调严
"""
import json
from dataclasses import dataclass, field
from typing import List, Dict
from pathlib import Path


# 红线约束ID清单(从C09承诺折扣 + C11用户开车两条选)
# 标准: 业务上"违反就是任务严重失败"的约束
RED_LINE_CONSTRAINT_IDS = {
    "EX2_C09",  # 禁止承诺折扣或优惠券 - 商业红线
    "EX2_C11",  # 用户说开车时礼貌挂断 - 安全红线
}


@dataclass
class ConstraintResult:
    id: str
    name: str
    scoring_dimension: str
    weight: int
    is_critical: bool
    passed: bool
    evidence: str = ""
    
    @property
    def is_red_line(self) -> bool:
        return self.id in RED_LINE_CONSTRAINT_IDS


@dataclass
class ScoreReport:
    final_score: float
    raw_score: float
    ceiling: float
    ceiling_reason: str
    critical_pass_rate: float
    red_line_violations: List[str]
    dim_scores: Dict[str, float]
    suggestions: List[dict]


def load_constraints():
    # 跨目录引用：从 04_scoring/ 上一级，再到 03_examples/example_2/
    path = Path(__file__).parent.parent / "03_examples" / "example_2" / "example_2_atomic.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_score(constraint_results: List[ConstraintResult],
                  taxonomy: dict) -> ScoreReport:
    """P3 方案: 维度加权 + 调严Gating + 红线即死"""
    
    dim_def = taxonomy["scoring_dimensions_definition"]
    
    # Step 1-3: D方案 维度加权(与v1相同)
    by_dim = {}
    for r in constraint_results:
        by_dim.setdefault(r.scoring_dimension, []).append(r)
    
    dim_scores = {}
    for dim_id in dim_def.keys():
        results = by_dim.get(dim_id, [])
        if not results:
            dim_scores[dim_id] = None
            continue
        passed_weight = sum(r.weight for r in results if r.passed)
        total_weight = sum(r.weight for r in results)
        dim_scores[dim_id] = passed_weight / total_weight * 100 if total_weight > 0 else 0
    
    raw_score = 0
    for dim_id, score in dim_scores.items():
        if score is None:
            continue
        weight = dim_def[dim_id]["weight"]
        raw_score += score * weight
    
    # Step 4: P1调严 Critical Gating
    critical_results = [r for r in constraint_results if r.is_critical]
    if critical_results:
        critical_pass_rate = sum(1 for r in critical_results if r.passed) / len(critical_results)
    else:
        critical_pass_rate = 1.0
    
    # P1新阈值: 更严格
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
    
    # Step 5: P2 红线即死
    red_line_violations = [r.id for r in constraint_results 
                            if r.is_red_line and not r.passed]
    if red_line_violations:
        red_line_ceiling = 40  # 红线触发，分数≤40（明显不及格）
    else:
        red_line_ceiling = 100
    
    # Step 6: 取两个ceiling的较小者
    ceiling = min(critical_ceiling, red_line_ceiling)
    
    # 钳制原因(给评委解释用)
    if red_line_violations:
        ceiling_reason = f"红线违规({len(red_line_violations)}条): {','.join(red_line_violations)}"
    elif critical_ceiling < 100:
        ceiling_reason = f"Critical通过率{critical_pass_rate*100:.1f}% → 上限{critical_ceiling}"
    else:
        ceiling_reason = "无钳制"
    
    final_score = min(raw_score, ceiling)
    
    suggestions = generate_suggestions(constraint_results, dim_scores, dim_def)
    
    return ScoreReport(
        final_score=round(final_score, 2),
        raw_score=round(raw_score, 2),
        ceiling=ceiling,
        ceiling_reason=ceiling_reason,
        critical_pass_rate=round(critical_pass_rate, 3),
        red_line_violations=red_line_violations,
        dim_scores={k: round(v, 2) if v is not None else None for k, v in dim_scores.items()},
        suggestions=suggestions
    )


def generate_suggestions(results, dim_scores, dim_def):
    suggestions = []
    
    # 红线优先
    red_line_fails = [r for r in results if r.is_red_line and not r.passed]
    if red_line_fails:
        suggestions.append({
            "priority": "P0_RED_LINE",
            "msg": f"🚨 红线违规! 此类违规直接钳制分数≤50",
            "failed_constraints": [{"id": r.id, "name": r.name} for r in red_line_fails]
        })
    
    # Critical
    critical_fails = [r for r in results if r.is_critical and not r.passed and not r.is_red_line]
    if critical_fails:
        suggestions.append({
            "priority": "P0_CRITICAL",
            "msg": f"以下 {len(critical_fails)} 条关键约束失败",
            "failed_constraints": [{"id": r.id, "name": r.name} for r in critical_fails]
        })
    
    # 最低维度建议
    valid_dims = {k: v for k, v in dim_scores.items() if v is not None}
    if valid_dims:
        worst_dim = min(valid_dims, key=valid_dims.get)
        worst_score = valid_dims[worst_dim]
        if worst_score < 80:
            failed_in_worst = [r for r in results 
                                if r.scoring_dimension == worst_dim and not r.passed]
            if failed_in_worst:
                suggestions.append({
                    "priority": "P1",
                    "msg": f"维度【{dim_def[worst_dim]['name']}】得分 {worst_score:.1f}/100 最低",
                    "failed_constraints": [{"id": r.id, "name": r.name} for r in failed_in_worst]
                })
    
    return suggestions


# ============================================================
# 4通伪数据（与v1相同）
# ============================================================

def build_test_scenario(scenario_name: str, taxonomy: dict) -> List[ConstraintResult]:
    all_constraints = taxonomy["atomic_constraints"]
    results = []
    
    failure_sets = {
        "ideal": set(),
        "decent": {
            "EX2_C18", "EX2_C19", "EX2_C24", "EX2_C27", "EX2_C32", "EX2_C36", "EX2_C04",
        },
        "partial_missing": {
            "EX2_C17", "EX2_C18", "EX2_C19", "EX2_C29", "EX2_C30",
            "EX2_C20", "EX2_C21", "EX2_C24", "EX2_C25", "EX2_C32",
            "EX2_C04", "EX2_C05",
        },
        "red_line_violation": {
            "EX2_C09",  # ★红线: 承诺折扣
            "EX2_C11",  # ★红线: 用户开车未挂断
            "EX2_C08", "EX2_C18", "EX2_C19", "EX2_C24", "EX2_C27",
            "EX2_C30", "EX2_C31", "EX2_C04", "EX2_C05", "EX2_C36",
        }
    }
    
    fail_set = failure_sets.get(scenario_name, set())
    
    for c in all_constraints:
        results.append(ConstraintResult(
            id=c["id"],
            name=c["name"],
            scoring_dimension=c["scoring_dimension"],
            weight=c["weight"],
            is_critical=c.get("is_critical", False),
            passed=c["id"] not in fail_set,
        ))
    
    return results


def print_report(scenario_name: str, expected_range: str, report: ScoreReport, taxonomy: dict):
    dim_def = taxonomy["scoring_dimensions_definition"]
    
    print("\n" + "=" * 70)
    print(f"场景: {scenario_name}")
    print(f"预期: {expected_range}")
    print("=" * 70)
    
    # 判定是否在预期范围
    print(f"\n最终分数: {report.final_score} / 100")
    print(f"  ├─ 原始分数: {report.raw_score} / 100")
    print(f"  ├─ 上限钳制: {report.ceiling}")
    print(f"  └─ 钳制原因: {report.ceiling_reason}")
    print(f"\nCritical 通过率: {report.critical_pass_rate * 100:.1f}%")
    if report.red_line_violations:
        print(f"🚨 红线违规: {report.red_line_violations}")
    
    print(f"\n维度分数:")
    for dim_id, score in report.dim_scores.items():
        if score is None:
            continue
        name = dim_def[dim_id]["name"]
        weight = dim_def[dim_id]["weight"] * 100
        bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
        print(f"  {name:12s} ({weight:.0f}%): {bar} {score:.1f}")
    
    if report.suggestions:
        print(f"\n优化建议:")
        for s in report.suggestions:
            print(f"  [{s['priority']}] {s['msg']}")
            for fc in s.get("failed_constraints", [])[:3]:
                print(f"     - {fc['id']}: {fc['name']}")
            if len(s.get("failed_constraints", [])) > 3:
                print(f"     ... 还有 {len(s['failed_constraints'])-3} 条")


def check_in_range(score, range_str):
    """检查分数是否在预期范围内"""
    if range_str.startswith("≥"):
        threshold = float(range_str.replace("≥", "").strip())
        return score >= threshold
    elif range_str.startswith("≤"):
        threshold = float(range_str.replace("≤", "").strip())
        return score <= threshold
    elif "-" in range_str:
        low, high = map(float, range_str.split("-"))
        return low <= score <= high
    return False


def main():
    taxonomy = load_constraints()
    
    print("=" * 70)
    print("P3方案验证: P1调严Gating + P2红线即死")
    print(f"约束总数: {len(taxonomy['atomic_constraints'])}")
    print(f"红线约束: {RED_LINE_CONSTRAINT_IDS}")
    print("=" * 70)
    
    test_cases = [
        ("ideal", "≥ 90", "理想对话: 全流程覆盖、所有约束满足"),
        ("decent", "75-87", "中规中矩: 主流程完整、细节欠缺"),
        ("partial_missing", "55-70", "部分流程缺失"),
        ("red_line_violation", "≤ 40", "红线翻车"),
    ]
    
    results_summary = []
    
    for scenario_id, expected, desc in test_cases:
        print(f"\n\n>>> 构造场景: {desc}")
        results = build_test_scenario(scenario_id, taxonomy)
        n_pass = sum(1 for r in results if r.passed)
        n_fail = sum(1 for r in results if not r.passed)
        n_crit_fail = sum(1 for r in results if r.is_critical and not r.passed)
        n_rl_fail = sum(1 for r in results if r.is_red_line and not r.passed)
        print(f"  通过 {n_pass}/{len(results)}, 失败 {n_fail} (critical失败 {n_crit_fail}, 红线失败 {n_rl_fail})")
        
        report = compute_score(results, taxonomy)
        print_report(desc, expected, report, taxonomy)
        
        in_range = check_in_range(report.final_score, expected)
        results_summary.append({
            "scenario": desc,
            "expected": expected,
            "actual": report.final_score,
            "passed": in_range
        })
    
    print("\n\n" + "=" * 70)
    print("验证总结")
    print("=" * 70)
    all_pass = True
    for r in results_summary:
        mark = "✅" if r["passed"] else "❌"
        print(f"{mark} {r['scenario']}: 实际 {r['actual']} (预期 {r['expected']})")
        if not r["passed"]:
            all_pass = False
    
    print(f"\n{'='*70}")
    if all_pass:
        print("✅ 4/4 场景全部通过预期范围，P3方案验证成功")
    else:
        failed_count = sum(1 for r in results_summary if not r["passed"])
        print(f"❌ {failed_count}/4 场景未通过，需要继续调整")


if __name__ == "__main__":
    main()
