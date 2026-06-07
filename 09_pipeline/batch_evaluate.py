"""
批量评测脚本 - 跑全 50 通 Gold Set, 收集所有 verdict

输出:
- batch_results.jsonl: 每行一条 verdict (dialogue_id, constraint_id, verdict, evidence, ...)
- batch_summary.json: 每通对话的总分汇总

用途:
- B 阶段: mock 模式跑出基线
- A 阶段: 切真实 LLM 重跑对比
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
from pipeline import compute_p3_score
from llm_client import get_stats_summary, reset_stats


def load_all_instructions() -> dict:
    """加载 V1/V2/V4/V5 的解析 JSON"""
    instructions = {}
    base = Path(__file__).parent.parent / "08_parser" / "parsed_examples"
    for v in ["v1", "v2", "v4", "v5"]:
        path = base / f"{v}_parsed.json"
        with open(path, encoding="utf-8") as f:
            instructions[v.upper()] = json.load(f)
    return instructions


def _safe_dispatch(constraint: dict, dialogue: dict, instruction: dict):
    """单条约束兜底, 防止单约束异常打断整通评测"""
    from verifier_base import VerdictResult
    try:
        return dispatch(constraint, dialogue, instruction)
    except Exception as e:
        return VerdictResult(
            verdict="error",
            constraint_id=constraint.get("id", "?"),
            constraint_name=constraint.get("name", ""),
            verifier_type=constraint.get("verifier", "?"),
            reason=f"dispatch 异常: {e}",
            confidence=0.0,
        )


def _load_existing_records(verdicts_path: Path, summary_path: Path):
    """读取历史输出用于断点续跑"""
    existing_verdicts = []
    existing_summaries = []
    completed_dialogues = set()

    if verdicts_path.exists():
        with open(verdicts_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                existing_verdicts.append(row)
                if row.get("dialogue_id"):
                    completed_dialogues.add(row["dialogue_id"])

    if summary_path.exists():
        try:
            old = json.loads(summary_path.read_text(encoding="utf-8"))
            existing_summaries = old.get("summaries", [])
            completed_dialogues.update(s.get("dialogue_id") for s in existing_summaries if s.get("dialogue_id"))
        except Exception:
            pass

    return existing_verdicts, existing_summaries, completed_dialogues


def run_batch(gold_set_path: str, output_dir: str, resume: bool = True):
    """跑全 50 通 Gold Set"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    instructions = load_all_instructions()
    print(f"[1/4] 加载 {len(instructions)} 条指令: {list(instructions.keys())}")
    
    # 加载 Gold Set
    dialogues = []
    with open(gold_set_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dialogues.append(json.loads(line))
    print(f"[2/4] 加载 {len(dialogues)} 通对话")
    
    # 跑每通
    use_mock = os.getenv('VERIFIER_LLM_MOCK', '1') == '1'
    mode_str = "mock" if use_mock else f"LLM ({os.getenv('VERIFIER_LLM_MODEL', 'deepseek-v4-flash')})"
    print(f"[3/4] 跑 pipeline (模式: {mode_str})")
    
    # 并行度: mock 不需要并行(瓶颈是CPU), LLM 需要并行(瓶颈是网络IO)
    max_workers = 1 if use_mock else int(os.getenv("VERIFIER_PARALLEL", "5"))
    if max_workers > 1:
        print(f"    并行度: {max_workers}")
    
    verdicts_path = output_dir / "batch_verdicts.jsonl"
    summary_path = output_dir / "batch_summary.json"

    all_verdicts = []  # 每条 verdict 一行
    all_summaries = []  # 每通对话一行
    completed_dialogues = set()

    if resume:
        all_verdicts, all_summaries, completed_dialogues = _load_existing_records(verdicts_path, summary_path)
        if completed_dialogues:
            print(f"    断点续跑: 已存在 {len(completed_dialogues)} 通完成记录, 将自动跳过")

    reset_stats()
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    t_start = time.time()
    for i, dialogue in enumerate(dialogues, 1):
        dlg_id = dialogue["dialogue_id"]
        instr_name = dialogue["instruction_name"]
        instruction = instructions.get(instr_name)
        
        if dlg_id in completed_dialogues:
            print(f"  [{i}/{len(dialogues)}] {dlg_id}: ⏭️ 跳过 (已完成)")
            continue

        if instruction is None:
            print(f"  [{i}/{len(dialogues)}] {dlg_id}: ⚠️ 跳过 (无对应指令 {instr_name})")
            continue
        
        constraints = instruction.get("atomic_constraints", [])
        
        # 关键: 一通对话内, 多个约束并行调LLM (前提: 各约束相互独立)
        if max_workers > 1:
            results = [None] * len(constraints)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_safe_dispatch, c, dialogue, instruction): idx
                           for idx, c in enumerate(constraints)}
                for fut in as_completed(futures):
                    idx = futures[fut]
                    results[idx] = fut.result()
        else:
            # 顺序模式
            results = [_safe_dispatch(c, dialogue, instruction) for c in constraints]
        
        # 记录 verdicts
        for v in results:
            all_verdicts.append({
                "dialogue_id": dlg_id,
                "constraint_id": v.constraint_id,
                "constraint_name": v.constraint_name,
                "verifier_type": v.verifier_type,
                "verdict": v.verdict,
                "evidence": v.evidence,
                "reason": v.reason,
                "confidence": v.confidence,
            })
        
        # 算分
        score_report = compute_p3_score(results, constraints)
        
        # 统计
        from collections import Counter
        verdict_counts = Counter(r.verdict for r in results)
        all_summaries.append({
            "dialogue_id": dlg_id,
            "instruction": instr_name,
            "persona": dialogue.get("persona_id"),
            "sample_source": dialogue.get("sample_source"),
            "final_score": score_report["final_score"],
            "raw_score": score_report["raw_score"],
            "ceiling": score_report["ceiling"],
            "critical_pass_rate": score_report["critical_pass_rate"],
            "dim_scores": score_report["dim_scores"],
            "verdict_dist": dict(verdict_counts),
        })
        
        # 进度
        if i % 10 == 0 or i == len(dialogues):
            elapsed = time.time() - t_start
            eta = elapsed / i * (len(dialogues) - i) if i < len(dialogues) else 0
            print(f"  [{i}/{len(dialogues)}] 已耗时 {elapsed:.1f}s, ETA {eta:.0f}s")
    
    # 写文件
    print(f"\n[4/4] 写输出")

    with open(verdicts_path, "w", encoding="utf-8") as f:
        for v in all_verdicts:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
    print(f"  ✓ {verdicts_path}: {len(all_verdicts)} 条 verdict")

    llm_stats = get_stats_summary()
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_dialogues": len(dialogues),
            "successful_dialogues": len(all_summaries),
            "total_verdicts": len(all_verdicts),
            "mode": "mock" if os.getenv("VERIFIER_LLM_MOCK", "1") == "1" else "real_llm",
            "resumed": resume,
            "completed_dialogues": sorted({s.get("dialogue_id") for s in all_summaries if s.get("dialogue_id")}),
            "llm_stats": llm_stats,
            "summaries": all_summaries,
        }, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {summary_path}: {len(all_summaries)} 通对话总结")
    
    # 终端摘要
    print(f"\n{'=' * 60}")
    print(f"批量评测完成")
    print(f"{'=' * 60}")
    print(f"  对话总数: {len(dialogues)}")
    print(f"  Verdict 总数: {len(all_verdicts)}")
    
    from collections import Counter
    overall_verdict = Counter(v["verdict"] for v in all_verdicts)
    print(f"  Verdict 分布:")
    for k, v in overall_verdict.most_common():
        print(f"    {k}: {v} ({v*100/len(all_verdicts):.1f}%)")
    
    if all_summaries:
        avg_score = sum(s["final_score"] for s in all_summaries) / len(all_summaries)
        print(f"  平均分数: {avg_score:.2f}")
    print(f"  LLM 统计: calls={llm_stats['total_calls']}, cache_hit={llm_stats['cache_hits']}, "
          f"retries={llm_stats['retries']}, failures={llm_stats['failures']}, "
          f"p95={llm_stats['p95_latency_s']}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold_set", default="../06_gold_annotation/gold_set/gold_set_50.jsonl")
    parser.add_argument("--output_dir", default="batch_results")
    parser.add_argument("--no_resume", action="store_true", help="禁用断点续跑, 强制全量重跑")
    args = parser.parse_args()
    run_batch(args.gold_set, args.output_dir, resume=not args.no_resume)
