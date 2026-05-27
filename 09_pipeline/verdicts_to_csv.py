"""
把 batch_verdicts.jsonl 转成跟 human_v3_merged.csv 同格式的 CSV
用于 kappa_calc.py 直接对比
"""
import argparse
import csv
import json


def convert(verdicts_path: str, output_path: str, rater_name: str = "auto_mock"):
    """转换"""
    with open(verdicts_path, encoding="utf-8") as f:
        verdicts = [json.loads(l) for l in f if l.strip()]
    
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "dialogue_id", "constraint_id", "verdict",
            "evidence_turn", "evidence_text", "confidence", "notes", "rater"
        ])
        writer.writeheader()
        for v in verdicts:
            writer.writerow({
                "dialogue_id": v["dialogue_id"],
                "constraint_id": v["constraint_id"],
                "verdict": v["verdict"],
                "evidence_turn": "",
                "evidence_text": v.get("evidence", "")[:500],
                "confidence": "high" if v.get("confidence", 0) >= 0.85 else "medium" if v.get("confidence", 0) >= 0.6 else "low",
                "notes": v.get("reason", "")[:200],
                "rater": rater_name,
            })
    
    print(f"✓ 已写入 {output_path}: {len(verdicts)} 行")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="batch_results/batch_verdicts.jsonl")
    parser.add_argument("--output", default="batch_results/auto_mock.csv")
    parser.add_argument("--rater_name", default="auto_mock")
    args = parser.parse_args()
    convert(args.input, args.output, args.rater_name)
