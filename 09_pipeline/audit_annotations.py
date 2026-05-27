"""
标注规范健全度审计 - B.5 阶段

目的: 找出"人工 vs mock 系统性反转"的 case
原理: 如果某条约束在多通对话上人工和 mock 完全相反(且 evidence 类型不匹配),
      很可能是人工标注规范有瑕疵.

输出:
- audit_findings.json: 可疑约束清单
- audit_report.md: 给主人看的 review 报告
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_verdicts(path: str, has_evidence: bool = True) -> dict:
    """加载 verdict + evidence"""
    data = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["dialogue_id"], row["constraint_id"])
            verdict = row["verdict"].strip().lower()
            if verdict not in {"pass", "fail", "na", "review"}:
                continue
            data[key] = {
                "verdict": verdict,
                "evidence": row.get("evidence_text", ""),
                "notes": row.get("notes", ""),
            }
    return data


def load_constraint_meta(parser_dir: Path) -> dict:
    """加载约束元数据"""
    meta = {}
    for v in ["v1", "v2", "v4", "v5"]:
        path = parser_dir / f"{v}_parsed.json"
        with open(path) as f:
            d = json.load(f)
        for c in d["atomic_constraints"]:
            meta[c["id"]] = {
                "name": c["name"],
                "verifier": c["verifier"],
                "dimension": c["scoring_dimension"],
                "is_critical": c["is_critical"],
            }
    return meta


def detect_evidence_mismatch(human_evidence: str, constraint_name: str) -> str:
    """检测人工 evidence 是否跟约束类型不符
    
    返回: 'length_to_flow' | 'flow_to_length' | 'ok' | 'unknown'
    """
    # 字数违规的 evidence 通常含: "超长" / "X字" / "T+数字=字数"
    has_length_evidence = any(kw in human_evidence for kw in [
        "超长", "字)", "字;", "T1=", "T2=", "T3=", "T4=", "T5=", 
        "T6=", "T7=", "T8=", "T9=", "字数", "过长"
    ])
    
    # 流程结构约束: S1/Step1/告知/询问
    is_flow_constraint = any(kw in constraint_name for kw in [
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", 
        "Step", "step", "自我介绍", "告知", "询问", "确认", "提醒", "记录"
    ]) and "字" not in constraint_name and "长度" not in constraint_name
    
    # 字数约束本身
    is_length_constraint = any(kw in constraint_name for kw in [
        "字以内", "字内", "字数", "30字", "20字", "15-20", "长度", "字左右"
    ])
    
    if is_flow_constraint and has_length_evidence:
        return "length_evidence_on_flow_constraint"  # 人工用字数证据标流程约束
    if is_length_constraint and not has_length_evidence and len(human_evidence) > 10:
        return "non_length_evidence_on_length_constraint"  # 人工用非字数证据标字数约束
    return "ok"


def audit():
    """主审计函数"""
    base = Path(__file__).parent.parent
    
    human = load_verdicts(base / "06_gold_annotation" / "gold_set" / "human_v3_merged.csv")
    auto = load_verdicts(base / "09_pipeline" / "batch_results" / "auto_mock.csv")
    meta = load_constraint_meta(base / "08_parser" / "parsed_examples")
    
    print(f"加载: 人工 {len(human)} 行, mock {len(auto)} 行, 约束元 {len(meta)} 条")
    
    # 按约束 ID 聚合: 统计人工 vs mock 的分歧模式
    per_constraint = defaultdict(lambda: {
        "total": 0,
        "agree": 0,
        "h_pass_a_fail": 0,
        "h_fail_a_pass": 0,
        "evidence_mismatches": [],  # 人工 evidence 跟约束类型不符的 case
        "human_evidence_samples": [],
        "auto_reason_samples": [],
    })
    
    for k in set(human.keys()) & set(auto.keys()):
        h = human[k]["verdict"]
        a = auto[k]["verdict"]
        if h == "na" or a == "na":
            continue
        
        cid = k[1]
        cname = meta.get(cid, {}).get("name", "")
        s = per_constraint[cid]
        s["total"] += 1
        
        if h == a:
            s["agree"] += 1
        else:
            if h == "pass" and a == "fail":
                s["h_pass_a_fail"] += 1
            elif h == "fail" and a == "pass":
                s["h_fail_a_pass"] += 1
            
            # 看 evidence 是否跟约束类型不符
            mismatch = detect_evidence_mismatch(human[k]["evidence"], cname)
            if mismatch != "ok":
                s["evidence_mismatches"].append({
                    "dialogue_id": k[0],
                    "human_verdict": h,
                    "human_evidence": human[k]["evidence"][:120],
                    "auto_verdict": a,
                    "auto_reason": auto[k]["notes"][:80],
                    "mismatch_type": mismatch,
                })
        
        # 收集样本
        if len(s["human_evidence_samples"]) < 3:
            s["human_evidence_samples"].append(human[k]["evidence"][:80])
        if len(s["auto_reason_samples"]) < 3:
            s["auto_reason_samples"].append(auto[k]["notes"][:80])
    
    # === 找出可疑约束 ===
    # 标准:
    # 1. 系统性反转: h_pass_a_fail 或 h_fail_a_pass ≥ 80% 且 total ≥ 5
    # 2. evidence 类型不匹配 ≥ 50% (人工用错 evidence)
    
    findings = []
    for cid, s in per_constraint.items():
        if s["total"] < 5:
            continue  # 样本太少
        
        disagree = s["total"] - s["agree"]
        if disagree == 0:
            continue
        
        flags = []
        # Flag 1: 大量 evidence 不匹配
        mismatch_count = len(s["evidence_mismatches"])
        if mismatch_count >= max(2, s["total"] * 0.3):
            flags.append(f"evidence_mismatch:{mismatch_count}/{s['total']}")
        
        # Flag 2: 系统性反转 (h_pass→a_fail 或 h_fail→a_pass)
        if s["h_pass_a_fail"] >= s["total"] * 0.6:
            flags.append(f"systematic_h_pass_a_fail:{s['h_pass_a_fail']}/{s['total']}")
        elif s["h_fail_a_pass"] >= s["total"] * 0.6:
            flags.append(f"systematic_h_fail_a_pass:{s['h_fail_a_pass']}/{s['total']}")
        
        if flags:
            findings.append({
                "constraint_id": cid,
                "constraint_name": meta.get(cid, {}).get("name", "?"),
                "verifier": meta.get(cid, {}).get("verifier", "?"),
                "dimension": meta.get(cid, {}).get("dimension", "?"),
                "total": s["total"],
                "agree": s["agree"],
                "disagree": disagree,
                "h_pass_a_fail": s["h_pass_a_fail"],
                "h_fail_a_pass": s["h_fail_a_pass"],
                "flags": flags,
                "evidence_mismatch_count": mismatch_count,
                "sample_evidence_mismatch": s["evidence_mismatches"][:3],
                "human_evidence_samples": s["human_evidence_samples"],
                "auto_reason_samples": s["auto_reason_samples"],
            })
    
    # 按问题严重度排序
    findings.sort(key=lambda f: -(f["disagree"]))
    
    # 输出
    out_dir = base / "09_pipeline" / "batch_results"
    out_dir.mkdir(exist_ok=True)
    
    with open(out_dir / "audit_findings.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_constraints_audited": len(per_constraint),
            "flagged_constraints": len(findings),
            "findings": findings,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 已写入 audit_findings.json")
    print(f"  审计约束总数: {len(per_constraint)}")
    print(f"  标记可疑约束数: {len(findings)}")
    
    # 终端摘要
    print(f"\n=== 可疑约束清单 (Top 10) ===")
    print(f"{'CID':<10} {'分歧':<6} {'类型':<22} {'name':<30} {'flag'}")
    for f_data in findings[:10]:
        name = f_data["constraint_name"][:28]
        flags_str = ",".join(f_data["flags"])[:60]
        print(f"  {f_data['constraint_id']:<10} {f_data['disagree']:<6} {f_data['verifier']:<22} {name:<30} {flags_str}")
    
    return findings


def write_review_report(findings: list, output_path: Path):
    """给主人看的可读报告"""
    lines = []
    lines.append("# B.5 标注规范健全度审计报告")
    lines.append("")
    lines.append(f"> 标记可疑约束: **{len(findings)}** 条")
    lines.append("> 优先级: 按分歧case数降序")
    lines.append("")
    lines.append("## 怎么读这份报告")
    lines.append("")
    lines.append("每条约束含: 约束名 + 人工 evidence 样本 + 我的修订建议")
    lines.append("")
    lines.append("**3 种诊断**:")
    lines.append("- `evidence_mismatch`: 人工 evidence 跟约束类型不符 (高度可疑)")
    lines.append("- `systematic_h_pass_a_fail`: 60%+ 都是'人工 pass, auto fail'(可能人工太宽松)")
    lines.append("- `systematic_h_fail_a_pass`: 60%+ 都是'人工 fail, auto pass'(可能人工太严或人工错判)")
    lines.append("")
    lines.append("---")
    
    for i, f_data in enumerate(findings, 1):
        lines.append(f"\n## {i}. {f_data['constraint_id']}: {f_data['constraint_name']}")
        lines.append("")
        lines.append(f"- **Verifier**: {f_data['verifier']}")
        lines.append(f"- **维度**: {f_data['dimension']}")
        lines.append(f"- **数据**: 总 {f_data['total']} 通, 一致 {f_data['agree']}, 分歧 {f_data['disagree']}")
        lines.append(f"  - 人工 pass / mock fail: {f_data['h_pass_a_fail']}")
        lines.append(f"  - 人工 fail / mock pass: {f_data['h_fail_a_pass']}")
        lines.append(f"- **诊断**: `{', '.join(f_data['flags'])}`")
        
        if f_data["sample_evidence_mismatch"]:
            lines.append(f"")
            lines.append(f"### Evidence 不匹配样本")
            lines.append("")
            for s in f_data["sample_evidence_mismatch"][:2]:
                lines.append(f"- `{s['dialogue_id']}`")
                lines.append(f"  - 人工 {s['human_verdict']}: {s['human_evidence']}")
                lines.append(f"  - Mock {s['auto_verdict']}: {s['auto_reason']}")
                lines.append(f"  - **问题**: {s['mismatch_type']}")
        
        # 修订建议
        lines.append("")
        lines.append("### 我的修订建议")
        lines.append("")
        if "evidence_mismatch" in str(f_data["flags"]):
            lines.append("- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: ")
            lines.append("  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**")
            lines.append("  - 字数违规应该归到 V*_C01 (长度约束) 上")
            lines.append("  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass")
        elif "h_fail_a_pass" in str(f_data["flags"]):
            lines.append("- 人工偏严, mock 偏宽. 需要看具体 case 判定哪边对")
            lines.append("- 如果人工 evidence 是字数→ 改 pass; 否则保留")
        elif "h_pass_a_fail" in str(f_data["flags"]):
            lines.append("- 人工偏宽, mock 偏严. 多数情况 mock 是对的")
            lines.append("- 例: V5_C01 字数 15-20, 人工 pass 但实际超字数 - 应该改 fail")
        lines.append("")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ 已写入 {output_path}")


if __name__ == "__main__":
    findings = audit()
    
    out_md = Path(__file__).parent.parent / "09_pipeline" / "batch_results" / "audit_report.md"
    write_review_report(findings, out_md)
