"""
Cohen's Kappa 计算脚本

用途:
1. 算两套独立标注的一致性（Test-Retest 或 Human-AI）
2. 出每条约束的单独 kappa（定位分歧最大的约束）
3. 出整体 kappa（项目总可靠性数字）

输入: 2 个 CSV/Excel 文件，列：dialogue_id, constraint_id, verdict
输出: 一致性报告

用法:
    python kappa_calc.py --rater1 annotation_round1.csv --rater2 annotation_round2.csv
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


def load_annotations(path: str) -> dict:
    """读取标注文件，返回 {(dialogue_id, constraint_id): verdict}"""
    annotations = {}
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"标注文件不存在: {path}")
    
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["dialogue_id"], row["constraint_id"])
            verdict = row["verdict"].strip().lower()
            # 只保留 pass/fail/na/review 这些"真实判定"
            # 排除 not_implemented (评估系统未支持) 和 error (调用失败)
            if verdict in {"pass", "fail", "na", "review"}:
                annotations[key] = verdict
            # not_implemented 和 error 不进入 dict, 也不会进 kappa 计算
    return annotations


def cohen_kappa(rater1: list, rater2: list) -> dict:
    """
    手算 Cohen's Kappa（不依赖 sklearn）
    
    Cohen's Kappa: κ = (po - pe) / (1 - pe)
    - po: observed agreement (实际一致率)
    - pe: expected agreement by chance (随机一致率)
    """
    assert len(rater1) == len(rater2), "两个标注列表长度必须相同"
    n = len(rater1)
    if n == 0:
        return {"kappa": None, "po": None, "pe": None, "n": 0, "reason": "无数据"}
    
    # 收集所有类别
    categories = sorted(set(rater1) | set(rater2))
    
    # 计算 po (observed agreement)
    agree = sum(1 for a, b in zip(rater1, rater2) if a == b)
    po = agree / n
    
    # 计算 pe (expected agreement by chance)
    pe = 0
    for cat in categories:
        p1 = rater1.count(cat) / n
        p2 = rater2.count(cat) / n
        pe += p1 * p2
    
    # Cohen's Kappa
    if pe >= 1.0:  # 防止除零（所有标注都是同一类别）
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1 - pe)
    
    return {
        "kappa": round(kappa, 4),
        "po": round(po, 4),
        "pe": round(pe, 4),
        "n": n,
        "categories": categories,
        "agree": agree,
        "disagree": n - agree
    }


def interpret_kappa(k: float) -> str:
    """kappa 值的解读"""
    if k is None:
        return "无数据"
    if k < 0.20:
        return "极差 (基本是瞎猜)"
    elif k < 0.40:
        return "一般 (部分一致)"
    elif k < 0.60:
        return "中等"
    elif k < 0.75:
        return "较好 (可用作 Gold Set)"
    elif k < 0.90:
        return "优秀 (高可信)"
    else:
        return "极优 (几乎完美)"


def analyze(rater1_path: str, rater2_path: str) -> dict:
    """主分析函数"""
    a1 = load_annotations(rater1_path)
    a2 = load_annotations(rater2_path)
    
    # 找两份标注都有的 key
    common_keys = set(a1.keys()) & set(a2.keys())
    if not common_keys:
        return {"error": "两份标注没有共同的 (dialogue, constraint) 对"}
    
    only_r1 = set(a1.keys()) - set(a2.keys())
    only_r2 = set(a2.keys()) - set(a1.keys())
    
    # 提取共同部分
    common_list = sorted(common_keys)
    r1_verdicts = [a1[k] for k in common_list]
    r2_verdicts = [a2[k] for k in common_list]
    
    # 排除 N/A（不计入 kappa）
    valid_pairs = [(r1, r2) for r1, r2 in zip(r1_verdicts, r2_verdicts) 
                   if r1 != "na" and r2 != "na"]
    
    if not valid_pairs:
        return {"error": "无有效标注对（全是 N/A）"}
    
    r1_valid = [p[0] for p in valid_pairs]
    r2_valid = [p[1] for p in valid_pairs]
    
    # 整体 kappa
    overall = cohen_kappa(r1_valid, r2_valid)
    
    # 按约束分组算 kappa
    by_constraint = defaultdict(lambda: {"r1": [], "r2": []})
    for (dlg_id, c_id), v1, v2 in zip(common_list, r1_verdicts, r2_verdicts):
        if v1 == "na" or v2 == "na":
            continue
        by_constraint[c_id]["r1"].append(v1)
        by_constraint[c_id]["r2"].append(v2)
    
    per_constraint_kappa = {}
    for c_id, data in by_constraint.items():
        per_constraint_kappa[c_id] = cohen_kappa(data["r1"], data["r2"])
    
    return {
        "overall": overall,
        "per_constraint": per_constraint_kappa,
        "stats": {
            "rater1_total": len(a1),
            "rater2_total": len(a2),
            "common_pairs": len(common_keys),
            "valid_pairs": len(valid_pairs),
            "only_r1": len(only_r1),
            "only_r2": len(only_r2),
            "na_excluded": len(common_list) - len(valid_pairs)
        }
    }


def print_report(result: dict):
    """格式化打印分析报告"""
    print("=" * 70)
    print("Cohen's Kappa 一致性分析报告")
    print("=" * 70)
    
    if "error" in result:
        print(f"❌ 错误: {result['error']}")
        return
    
    s = result["stats"]
    print(f"\n[数据统计]")
    print(f"  标注员1 标注数: {s['rater1_total']}")
    print(f"  标注员2 标注数: {s['rater2_total']}")
    print(f"  共同的 (对话,约束) 对: {s['common_pairs']}")
    print(f"  有效配对（排除N/A）: {s['valid_pairs']}")
    if s['only_r1']:
        print(f"  ⚠️ 仅标注员1标了 {s['only_r1']} 对")
    if s['only_r2']:
        print(f"  ⚠️ 仅标注员2标了 {s['only_r2']} 对")
    
    # 整体 kappa
    o = result["overall"]
    print(f"\n[整体一致性]")
    print(f"  Cohen's Kappa: {o['kappa']} ({interpret_kappa(o['kappa'])})")
    print(f"  实际一致率 po: {o['po']*100:.2f}%")
    print(f"  随机一致率 pe: {o['pe']*100:.2f}%")
    print(f"  一致: {o['agree']} / {o['n']}, 不一致: {o['disagree']}")
    
    # 通过门槛判定
    if o['kappa'] is None:
        print(f"  状态: ❓ 无法判定")
    elif o['kappa'] >= 0.75:
        print(f"  状态: ✅ 优秀，可作为高可信 Gold Set")
    elif o['kappa'] >= 0.70:
        print(f"  状态: ✅ 通过门槛 (≥0.70)")
    elif o['kappa'] >= 0.60:
        print(f"  状态: ⚠️ 临界，建议复盘分歧大的约束")
    else:
        print(f"  状态: ❌ 不通过门槛，必须重新校准")
    
    # 每条约束的 kappa
    pc = result["per_constraint"]
    print(f"\n[按约束的 Kappa（按值从低到高，问题最大的在前）]")
    sorted_c = sorted(pc.items(), key=lambda x: (x[1]["kappa"] if x[1]["kappa"] is not None else 1.0))
    
    print(f"  {'约束 ID':<15} {'Kappa':<10} {'有效N':<8} {'解读'}")
    print(f"  {'-'*15} {'-'*10} {'-'*8} {'-'*20}")
    for c_id, k_data in sorted_c[:15]:  # 只列前15个
        kappa_str = f"{k_data['kappa']:.3f}" if k_data['kappa'] is not None else "N/A"
        n_str = f"{k_data['n']}"
        interp = interpret_kappa(k_data['kappa'])
        flag = "❌" if k_data['kappa'] is not None and k_data['kappa'] < 0.6 else "  "
        print(f"  {flag}{c_id:<13} {kappa_str:<10} {n_str:<8} {interp}")
    
    if len(sorted_c) > 15:
        print(f"  ... 还有 {len(sorted_c)-15} 条约束未列出")
    
    # 行动建议
    low_kappa = [c for c, k in sorted_c if k['kappa'] is not None and k['kappa'] < 0.6]
    if low_kappa:
        print(f"\n[行动建议]")
        print(f"  以下 {len(low_kappa)} 条约束 kappa<0.6，建议:")
        print(f"  1) 找出所有分歧 case 列在一起")
        print(f"  2) 重读规范，看规则是否写清")
        print(f"  3) 修订规范，对这些约束重标 20 通")
        print(f"  4) 重新算 kappa")
        print(f"  约束清单: {', '.join(low_kappa)}")


# =====================================================================
# 单元测试 - 用合成数据验证kappa计算正确性
# =====================================================================

def run_unit_tests():
    """跑单元测试，验证kappa计算正确"""
    print("=" * 70)
    print("单元测试: 验证kappa计算正确性")
    print("=" * 70)
    
    tests = [
        {
            "name": "完美一致 (kappa=1.0)",
            "r1": ["pass", "fail", "pass", "fail", "pass"],
            "r2": ["pass", "fail", "pass", "fail", "pass"],
            "expected_kappa": 1.0,
        },
        {
            "name": "完全不一致 (kappa=-1.0)",
            "r1": ["pass", "pass", "fail", "fail"],
            "r2": ["fail", "fail", "pass", "pass"],
            "expected_kappa": -1.0,
        },
        {
            "name": "中等一致（理论kappa约0.4）",
            "r1": ["pass", "pass", "pass", "fail", "fail", "fail"],
            "r2": ["pass", "fail", "pass", "fail", "pass", "fail"],
            "expected_kappa_range": (0.3, 0.5),
        },
        {
            "name": "全部一种类别",
            "r1": ["pass", "pass", "pass"],
            "r2": ["pass", "pass", "pass"],
            "expected_kappa": 1.0,
        },
    ]
    
    all_pass = True
    for t in tests:
        result = cohen_kappa(t["r1"], t["r2"])
        actual = result["kappa"]
        
        if "expected_kappa" in t:
            expected = t["expected_kappa"]
            passed = abs(actual - expected) < 0.01
        else:
            low, high = t["expected_kappa_range"]
            passed = low <= actual <= high
        
        mark = "✅" if passed else "❌"
        if not passed:
            all_pass = False
        
        print(f"\n{mark} {t['name']}")
        print(f"   实际 kappa = {actual}")
        if "expected_kappa" in t:
            print(f"   预期 = {t['expected_kappa']}")
        else:
            print(f"   预期范围 = {t['expected_kappa_range']}")
    
    print("\n" + "=" * 70)
    if all_pass:
        print("✅ 所有单元测试通过，kappa 计算实现正确")
    else:
        print("❌ 单元测试失败，需要修复")
    return all_pass


def main():
    parser = argparse.ArgumentParser(description="Cohen's Kappa 一致性计算")
    parser.add_argument("--rater1", help="标注员1的 CSV 文件")
    parser.add_argument("--rater2", help="标注员2的 CSV 文件")
    parser.add_argument("--test", action="store_true", help="跑单元测试")
    args = parser.parse_args()
    
    if args.test:
        success = run_unit_tests()
        sys.exit(0 if success else 1)
    
    if not args.rater1 or not args.rater2:
        print("用法:")
        print("  python kappa_calc.py --rater1 a.csv --rater2 b.csv")
        print("  python kappa_calc.py --test  (跑单元测试)")
        sys.exit(1)
    
    result = analyze(args.rater1, args.rater2)
    print_report(result)


if __name__ == "__main__":
    main()
