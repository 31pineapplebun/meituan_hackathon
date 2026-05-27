"""
Flash vs Pro 对照实验脚本

设计:
- 从 50 通 Gold Set 中抽样 10 通(均衡覆盖)
- 用 deepseek-v4-flash (非思考) 跑一遍
- 用 deepseek-v4-pro (思考) 跑一遍同样 10 通
- 对比两种 verifier 在这 10 通上的 verdict 一致性

用途:
- 实证回答"flash 够不够用?" 这个问题
- 答辩素材: "我们用 10 通对照实验证明 flash 跟 pro 在此任务上等价"

成本估算:
- flash: 10通 × 6约束 × ¥0.001 = ¥0.06
- pro:   10通 × 6约束 × ¥0.05 = ¥3
- 总计 < ¥5
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier_base import dispatch
import verifiers
import verifier_state_tracker
import verifier_llm_extract
import verifier_llm_judge


# 抽样策略: 均衡覆盖
def sample_10_dialogues(gold_set_path: str) -> list:
    """从 50 通抽 10 通, 均衡覆盖 4 指令 × 4 persona 组合"""
    with open(gold_set_path, encoding="utf-8") as f:
        dialogues = [json.loads(l) for l in f if l.strip()]
    
    # 按 (指令, persona) 分组
    from collections import defaultdict
    groups = defaultdict(list)
    for d in dialogues:
        key = (d["instruction_name"], d["persona_id"])
        groups[key].append(d)
    
    # 每组取 1 个, 取够 10 个
    sampled = []
    for key in sorted(groups.keys()):
        if groups[key]:
            sampled.append(groups[key][0])
            if len(sampled) >= 10:
                break
    
    return sampled


def run_one_model(model_name: str, thinking_str: str, dialogues: list, 
                  instructions: dict, label: str) -> tuple:
    """跑一个模型, 返回 (verdicts_list, total_time)"""
    
    # 设置环境
    os.environ["VERIFIER_LLM_MOCK"] = "0"
    os.environ["VERIFIER_LLM_MODEL"] = model_name
    os.environ["VERIFIER_LLM_THINKING"] = thinking_str
    
    # 重新加载模块, 让环境变量生效
    import importlib
    importlib.reload(verifier_llm_extract)
    importlib.reload(verifier_llm_judge)
    
    print(f"\n{'='*60}")
    print(f"跑 {label}: model={model_name}, thinking={thinking_str}")
    print(f"{'='*60}")
    
    all_verdicts = []
    t_start = time.time()
    
    for i, dialogue in enumerate(dialogues, 1):
        dlg_id = dialogue["dialogue_id"]
        instr_name = dialogue["instruction_name"]
        instruction = instructions.get(instr_name)
        constraints = instruction.get("atomic_constraints", [])
        
        t_dlg_start = time.time()
        for c in constraints:
            v = dispatch(c, dialogue, instruction)
            all_verdicts.append({
                "dialogue_id": dlg_id,
                "constraint_id": v.constraint_id,
                "verdict": v.verdict,
                "evidence": v.evidence[:100],
                "verifier_type": v.verifier_type,
            })
        
        dlg_elapsed = time.time() - t_dlg_start
        print(f"  [{i}/10] {dlg_id} | {len(constraints)} 约束 | {dlg_elapsed:.1f}s")
    
    total_time = time.time() - t_start
    print(f"\n  总耗时: {total_time:.0f}s")
    return all_verdicts, total_time


def compare(flash_verdicts: list, pro_verdicts: list):
    """对比两种 verifier 的一致性"""
    print(f"\n{'='*60}")
    print(f"Flash vs Pro 一致性分析")
    print(f"{'='*60}")
    
    flash_by_key = {(v["dialogue_id"], v["constraint_id"]): v["verdict"] for v in flash_verdicts}
    pro_by_key = {(v["dialogue_id"], v["constraint_id"]): v["verdict"] for v in pro_verdicts}
    
    # 只看共同的 key
    common = set(flash_by_key.keys()) & set(pro_by_key.keys())
    print(f"  共同 verdict 数: {len(common)}")
    
    # 只看真实判定 (pass/fail/na)
    valid = [(flash_by_key[k], pro_by_key[k]) for k in common 
             if flash_by_key[k] in ("pass", "fail", "na") 
             and pro_by_key[k] in ("pass", "fail", "na")]
    
    agree = sum(1 for f, p in valid if f == p)
    print(f"  有效配对(排除 not_implemented/error): {len(valid)}")
    print(f"  一致: {agree} ({agree*100/len(valid):.1f}%)")
    
    # 不一致的具体分布
    from collections import Counter
    disagree_dist = Counter((f, p) for f, p in valid if f != p)
    if disagree_dist:
        print(f"\n  不一致分布:")
        for (f, p), n in disagree_dist.most_common():
            print(f"    flash={f} / pro={p}: {n}")
    
    # 计算 Cohen's kappa
    def cohen_kappa(r1, r2):
        n = len(r1)
        if n == 0: return None
        agree = sum(1 for a,b in zip(r1, r2) if a==b)
        po = agree/n
        cats = set(r1) | set(r2)
        pe = sum((r1.count(c)/n) * (r2.count(c)/n) for c in cats)
        if pe >= 1.0:
            return 1.0 if po==1.0 else 0.0
        return (po-pe)/(1-pe)
    
    r1 = [f for f, p in valid]
    r2 = [p for f, p in valid]
    k = cohen_kappa(r1, r2)
    print(f"\n  Cohen's kappa (flash vs pro): {k:.4f}")
    
    # 解读
    print(f"\n  解读:")
    if k >= 0.8:
        print(f"  🎉 高度一致 (kappa ≥ 0.8) → flash 跟 pro 等价, 用 flash 完全没问题")
    elif k >= 0.6:
        print(f"  ✅ 较好一致 (kappa ≥ 0.6) → flash 可用, 偏差可接受")
    elif k >= 0.4:
        print(f"  ⚠️ 中等一致 (kappa ≥ 0.4) → flash 有偏差, 谨慎使用")
    else:
        print(f"  ❌ 一致性差 (kappa < 0.4) → 必须用 pro")
    
    return {"common": len(common), "valid": len(valid), "agree": agree, 
            "kappa": k, "disagree_dist": dict(disagree_dist)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold_set", default="../06_gold_annotation/gold_set/gold_set_50.jsonl")
    parser.add_argument("--output", default="batch_results/flash_vs_pro_comparison.json")
    args = parser.parse_args()
    
    # 检查 API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 需要 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)
    
    # 加载数据
    base = Path(__file__).parent.parent / "08_parser" / "parsed_examples"
    instructions = {}
    for v in ["v1", "v2", "v4", "v5"]:
        with open(base / f"{v}_parsed.json") as f:
            instructions[v.upper()] = json.load(f)
    
    print(f"采样 10 通对话(均衡覆盖)")
    sampled = sample_10_dialogues(args.gold_set)
    print(f"采样结果:")
    for d in sampled:
        print(f"  - {d['dialogue_id']} ({d['instruction_name']}/{d['persona_id']})")
    
    # 跑 flash
    flash_verdicts, flash_time = run_one_model("deepseek-v4-flash", "0", sampled, instructions, "Flash (非思考)")
    
    # 跑 pro
    pro_verdicts, pro_time = run_one_model("deepseek-v4-pro", "1", sampled, instructions, "Pro (思考)")
    
    # 对比
    comparison = compare(flash_verdicts, pro_verdicts)
    
    # 保存
    output = {
        "sampled_dialogues": [d["dialogue_id"] for d in sampled],
        "flash_time_seconds": flash_time,
        "pro_time_seconds": pro_time,
        "speedup": pro_time / flash_time if flash_time > 0 else 0,
        "flash_verdicts": flash_verdicts,
        "pro_verdicts": pro_verdicts,
        "comparison": comparison,
    }
    Path(args.output).parent.mkdir(exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 完整结果保存到 {args.output}")
    print(f"\n=== 最终建议 ===")
    print(f"  Flash 耗时: {flash_time:.0f}s")
    print(f"  Pro 耗时:   {pro_time:.0f}s ({pro_time/flash_time:.1f}x slower)")
    print(f"  一致性 kappa: {comparison['kappa']:.4f}")


if __name__ == "__main__":
    main()
