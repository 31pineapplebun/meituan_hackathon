"""
基于 B.5 审计自动修订人工标注 → 生成 human_v4_audited.csv

修订规则:
1. V5_C12 / V4_C12 / V1_C08 / V2_C08 (S1 自我介绍, evidence 是字数):
   - 人工 fail → 改 pass (字数违规应归到 V*_C01, 不是 S1)
2. V5_C01 / V4_C01 (字数 15-20, evidence 是开场白):
   - 人工 pass → 改 fail (开场白豁免后, 非首轮 turn 全部超字数, 应该 fail)

注意:
- 只修 evidence 类型不匹配的 case, 不"自动批准全部"
- 保留所有原标注的其他列, 只改 verdict
- 生成 modifications.json 记录所有改动 (审计追溯)
"""
import csv
import json
from pathlib import Path
from collections import Counter


# 修订规则
REVISION_RULES = {
    # S1 流程结构约束: 如果 evidence 是字数证据, fail → pass
    "V5_C12": {"keyword": "超长", "from": "fail", "to": "pass", "reason": "S1是流程结构, 字数违规应归 V5_C01"},
    "V4_C12": {"keyword": "超长", "from": "fail", "to": "pass", "reason": "S1是流程结构, 字数违规应归 V4_C01"},
    "V1_C08": {"keyword": "超长", "from": "fail", "to": "pass", "reason": "S1是流程结构, 字数违规应归 V1_C01"},
    "V2_C08": {"keyword": "超长", "from": "fail", "to": "pass", "reason": "S1是流程结构, 字数违规应归 V2_C01"},
    # 字数约束: 如果 evidence 是开场白 (含'您好/请问/喂'), pass → fail
    "V5_C01": {"keyword_any": ["您好", "请问", "喂"], "from": "pass", "to": "fail", "reason": "evidence用开场白, 但非首轮turn全部超20字"},
    "V4_C01": {"keyword_any": ["您好", "请问", "喂"], "from": "pass", "to": "fail", "reason": "evidence用开场白, 但非首轮turn全部超20字"},
}


def apply_revisions():
    base = Path(__file__).parent.parent
    input_csv = base / "06_gold_annotation" / "gold_set" / "human_v3_merged.csv"
    output_csv = base / "06_gold_annotation" / "gold_set" / "human_v4_audited.csv"
    log_path = base / "09_pipeline" / "batch_results" / "v4_modifications.json"
    
    rows = []
    with open(input_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    
    modifications = []
    revision_count = Counter()
    
    for r in rows:
        cid = r["constraint_id"]
        if cid not in REVISION_RULES:
            continue
        
        rule = REVISION_RULES[cid]
        verdict = r["verdict"].strip().lower()
        if verdict != rule["from"]:
            continue
        
        evidence = r.get("evidence_text", "")
        
        # 检查 evidence 是否匹配规则
        if "keyword" in rule:
            if rule["keyword"] not in evidence:
                continue
        elif "keyword_any" in rule:
            if not any(kw in evidence for kw in rule["keyword_any"]):
                continue
        
        # 应用修订
        old_verdict = r["verdict"]
        r["verdict"] = rule["to"]
        r["notes"] = (r.get("notes") or "") + f" [B.5修订: {rule['reason']}]"
        
        modifications.append({
            "dialogue_id": r["dialogue_id"],
            "constraint_id": cid,
            "old_verdict": old_verdict,
            "new_verdict": rule["to"],
            "old_evidence": evidence[:100],
            "reason": rule["reason"],
        })
        revision_count[cid] += 1
    
    # 写新 CSV
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "dialogue_id", "constraint_id", "verdict",
            "evidence_turn", "evidence_text", "confidence", "notes", "rater"
        ])
        writer.writeheader()
        for r in rows:
            r["rater"] = "human_v4_audited"
            writer.writerow(r)
    
    # 写改动日志
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_modifications": len(modifications),
            "by_constraint": dict(revision_count),
            "modifications": modifications,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 修订完成")
    print(f"  原 CSV: {input_csv}")
    print(f"  新 CSV: {output_csv}")
    print(f"  改动日志: {log_path}")
    print(f"  总修订数: {len(modifications)}")
    print(f"  按约束: {dict(revision_count)}")
    
    return len(modifications)


if __name__ == "__main__":
    apply_revisions()
