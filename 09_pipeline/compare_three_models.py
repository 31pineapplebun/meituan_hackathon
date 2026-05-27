"""
三路对照实验: DeepSeek Flash + DeepSeek Pro + GPT-5-mini

设计:
- 抽 10 通均衡对话
- 3 个模型各跑一遍, 相互对比 verdict 一致性
- 算两两 kappa

用途:
- 答辩材料: "我们做了跨模型族对照 (DeepSeek + OpenAI), 排除单一模型族偏差"
- 决策: 看 3 个模型一致性, 决定主 verifier 用哪个

成本估算:
- flash: 10通 × 6约束 × ~$0.001 = $0.06 (¥0.4)
- pro:   10通 × 6约束 × ~$0.05 = $3 (¥21)
- gpt-5-mini: 10通 × 6约束 × ~$0.005 = $0.3 (¥2)
- 总计 ~¥25 (含 pro 75% 折扣后 ¥10)
"""
import argparse
import json
import os
import sys
import time
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier_base import dispatch
import verifiers
import verifier_state_tracker
import verifier_llm_extract
import verifier_llm_judge


def sample_dialogues(gold_set_path: str, n: int = 10) -> list:
    """从 50 通抽 n 通, 均衡覆盖 4 指令 × 4 persona 组合"""
    with open(gold_set_path, encoding="utf-8") as f:
        dialogues = [json.loads(l) for l in f if l.strip()]
    
    from collections import defaultdict
    groups = defaultdict(list)
    for d in dialogues:
        key = (d["instruction_name"], d["persona_id"])
        groups[key].append(d)
    
    sampled = []
    for key in sorted(groups.keys()):
        if groups[key] and len(sampled) < n:
            sampled.append(groups[key][0])
    
    return sampled


def run_one_model(model_name: str, thinking_str: str, dialogues: list, 
                  instructions: dict, label: str) -> tuple:
    """跑一个模型, 返回 (verdicts_list, total_time)"""
    
    os.environ["VERIFIER_LLM_MOCK"] = "0"
    os.environ["VERIFIER_LLM_MODEL"] = model_name
    os.environ["VERIFIER_LLM_THINKING"] = thinking_str
    
    # 重新加载模块, 让环境变量生效
    importlib.reload(verifier_llm_extract)
    importlib.reload(verifier_llm_judge)
    
    print(f"\n{'='*60}")
    print(f"跑 {label}")
    print(f"  model: {model_name}")
    print(f"  thinking: {thinking_str} (0=关 / 1=开)")
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
                "reason": v.reason[:100],
            })
        
        dlg_elapsed = time.time() - t_dlg_start
        print(f"  [{i}/{len(dialogues)}] {dlg_id[:50]} | {len(constraints)} 约束 | {dlg_elapsed:.1f}s")
    
    total_time = time.time() - t_start
    print(f"\n  ✓ 完成: {total_time:.0f}s, {len(all_verdicts)} verdict")
    return all_verdicts, total_time


def cohen_kappa(r1: list, r2: list) -> float:
    """计算 Cohen's Kappa"""
    n = len(r1)
    if n == 0: return None
    agree = sum(1 for a, b in zip(r1, r2) if a == b)
    po = agree / n
    cats = set(r1) | set(r2)
    pe = sum((r1.count(c)/n) * (r2.count(c)/n) for c in cats)
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def compare_two(v1: list, v2: list, label_a: str, label_b: str) -> dict:
    """对比两组 verdict"""
    by_key_a = {(v["dialogue_id"], v["constraint_id"]): v["verdict"] for v in v1}
    by_key_b = {(v["dialogue_id"], v["constraint_id"]): v["verdict"] for v in v2}
    
    common = set(by_key_a.keys()) & set(by_key_b.keys())
    # 排除 not_implemented/error
    valid = [(by_key_a[k], by_key_b[k]) for k in common 
             if by_key_a[k] in ("pass", "fail", "na") 
             and by_key_b[k] in ("pass", "fail", "na")]
    
    if not valid:
        return {"n": 0, "kappa": None, "agree": 0, "label_a": label_a, "label_b": label_b}
    
    r1 = [a for a, b in valid]
    r2 = [b for a, b in valid]
    agree = sum(1 for a, b in valid if a == b)
    k = cohen_kappa(r1, r2)
    
    from collections import Counter
    disagree = Counter((a, b) for a, b in valid if a != b)
    # JSON 不允许 tuple 作 key, 转成 "a→b" 字符串
    disagree_jsonable = {f"{a}_vs_{b}": n for (a, b), n in disagree.items()}
    
    return {
        "label_a": label_a, "label_b": label_b,
        "n": len(valid), "agree": agree, "po": agree/len(valid),
        "kappa": k, "disagree_dist": disagree_jsonable
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold_set", default="../06_gold_annotation/gold_set/gold_set_50.jsonl")
    parser.add_argument("--output", default="batch_results/three_way_comparison.json")
    parser.add_argument("--n", type=int, default=10, help="抽样对话数")
    parser.add_argument("--skip_pro", action="store_true", help="跳过 deepseek-v4-pro (省时省钱)")
    parser.add_argument("--skip_gpt", action="store_true", help="跳过 gpt-5-mini")
    args = parser.parse_args()
    
    # 环境检查
    missing = []
    if not os.getenv("DEEPSEEK_API_KEY"):
        missing.append("DEEPSEEK_API_KEY")
    if not args.skip_gpt and not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        print(f"❌ 缺少环境变量: {', '.join(missing)}")
        sys.exit(1)
    
    # 加载指令
    base = Path(__file__).parent.parent / "08_parser" / "parsed_examples"
    instructions = {}
    for v in ["v1", "v2", "v4", "v5"]:
        with open(base / f"{v}_parsed.json") as f:
            instructions[v.upper()] = json.load(f)
    
    # 抽样
    print(f"采样 {args.n} 通对话(均衡覆盖)")
    sampled = sample_dialogues(args.gold_set, args.n)
    for d in sampled:
        print(f"  - {d['dialogue_id']} ({d['instruction_name']}/{d['persona_id']})")
    
    # 跑三个模型
    results = {}
    
    # 1. flash (核心)
    flash_v, flash_t = run_one_model(
        "deepseek-v4-flash", "0", sampled, instructions, "DeepSeek Flash (非思考)"
    )
    results["flash"] = {"verdicts": flash_v, "time": flash_t}
    
    # 2. pro (可选)
    if not args.skip_pro:
        pro_v, pro_t = run_one_model(
            "deepseek-v4-pro", "0", sampled, instructions, "DeepSeek Pro (非思考)"
        )
        results["pro"] = {"verdicts": pro_v, "time": pro_t}
    
    # 3. gpt-5-mini (可选)
    if not args.skip_gpt:
        gpt_v, gpt_t = run_one_model(
            "gpt-5-mini", "0", sampled, instructions, "GPT-5 mini"
        )
        results["gpt"] = {"verdicts": gpt_v, "time": gpt_t}
    
    # 两两对比
    print(f"\n{'='*60}")
    print(f"两两一致性分析")
    print(f"{'='*60}")
    
    comparisons = []
    pairs = []
    if "flash" in results and "pro" in results:
        pairs.append(("flash", "pro"))
    if "flash" in results and "gpt" in results:
        pairs.append(("flash", "gpt"))
    if "pro" in results and "gpt" in results:
        pairs.append(("pro", "gpt"))
    
    for a, b in pairs:
        comp = compare_two(results[a]["verdicts"], results[b]["verdicts"], a, b)
        comparisons.append(comp)
        if comp.get("kappa") is not None:
            print(f"\n  {a} vs {b}:")
            print(f"    有效配对: {comp['n']}, 一致: {comp['agree']} ({comp['po']*100:.1f}%)")
            print(f"    Cohen's kappa: {comp['kappa']:.4f}")
            if comp.get("disagree_dist"):
                print(f"    不一致样本:")
                for key, n in sorted(comp["disagree_dist"].items(), key=lambda x: -x[1])[:3]:
                    # key 形如 "pass_vs_fail"
                    parts = key.split("_vs_")
                    if len(parts) == 2:
                        x, y = parts
                        print(f"      {a}={x} / {b}={y}: {n}")
                    else:
                        print(f"      {key}: {n}")
    
    # 汇总建议
    print(f"\n{'='*60}")
    print(f"💡 决策建议")
    print(f"{'='*60}")
    
    if "flash" in results and "pro" in results:
        fp = next(c for c in comparisons if c["label_a"] == "flash" and c["label_b"] == "pro")
        if fp.get("kappa") is not None:
            print(f"\n  Flash vs Pro kappa = {fp['kappa']:.4f}")
            if fp["kappa"] >= 0.8:
                print(f"  🎉 强烈一致 → 用 flash 完全没问题(节省 5-10 倍时间)")
            elif fp["kappa"] >= 0.6:
                print(f"  ✅ 较好一致 → 用 flash 可以, 答辩时附此实验数据")
            elif fp["kappa"] >= 0.4:
                print(f"  ⚠️ 中等一致 → 视乎答辩重要性, 选稳妥用 pro")
            else:
                print(f"  ❌ 一致性差 → 必须用 pro")
    
    if "flash" in results and "gpt" in results:
        fg = next(c for c in comparisons if c["label_a"] == "flash" and c["label_b"] == "gpt")
        if fg.get("kappa") is not None:
            print(f"\n  Flash vs GPT-5-mini kappa = {fg['kappa']:.4f}")
            if fg["kappa"] >= 0.6:
                print(f"  ✅ 跨模型族一致 → 排除单一模型偏差, 答辩有力")
            else:
                print(f"  ⚠️ 跨模型族分歧大 → 答辩可能被质疑模型选择")
    
    # 时间对比
    print(f"\n  耗时对比:")
    for name, r in results.items():
        print(f"    {name}: {r['time']:.0f}s")
    
    # 保存
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "sampled_dialogues": [d["dialogue_id"] for d in sampled],
            "results": {k: {"verdicts": v["verdicts"], "time_seconds": v["time"]} 
                        for k, v in results.items()},
            "comparisons": comparisons,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 完整结果保存到 {output_path}")


if __name__ == "__main__":
    main()
