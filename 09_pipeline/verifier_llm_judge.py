"""
llm_judge verifier - Day 9.2

设计:
- LLM 直接判 pass/fail (跟 llm_extract_then_rule 不同)
- 适用主观约束: 口语化/避免重复/适时结束/FAQ 准确性
- prompt 核心: anchor examples 锚定判定标准

Day 5 Gold Set 数据显示这是 kappa 最低的类别:
- 主观判断 kappa 0.606
- 流程结束 kappa 0.103
- FAQ 知识 kappa 0.000

prompt 工程目标: 用具体例子拉高一致性
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier_base import register, VerdictResult, get_assistant_turns, all_assistant_text

# 复用 llm_extract 的 LLM 调用基础设施
from verifier_llm_extract import (
    call_llm_for_extraction,
    USE_MOCK,
    LLM_MODEL,
    _parse_json_from_text,
)


# ============================================================
# 子类型识别
# ============================================================

def classify_judge_constraint(constraint: dict) -> str:
    """根据约束推断 judge 子类型"""
    name = constraint.get("name", "") + " " + constraint.get("source_text", "")
    name_lower = name.lower()
    
    # 适时结束 (优先检查, 因为 V*_C15 通常是"适时终结对话")
    if "适时" in name or "终结" in name or "结束通话" in name or "礼貌挂断" in name or "适时结束" in name or "对话结束" in name:
        return "timely_end"
    # 口语化/自然
    if "口语" in name or "自然" in name or "随意" in name:
        return "oral_natural"
    # 避免重复
    if "重复" in name or "灵活" in name:
        return "no_repeat"
    # FAQ 知识
    if "faq" in name_lower or "知识" in name:
        return "faq"
    # 任务核心意图
    if "核心意图" in name or "任务完成" in name or "意图完成" in name or "核心" in name:
        return "core_intent"
    # 频繁给发言机会
    if "发言" in name or "提问机会" in name or "暂停等" in name:
        return "give_floor"
    # 过渡语
    if "过渡" in name or "被打断" in name:
        return "transition"
    
    return "generic"


# ============================================================
# Mock 实现 (Day 9.2 优先, 简单启发)
# ============================================================

def _mock_judge_oral_natural(dialogue: dict) -> dict:
    """Mock: 看 assistant 是否含书面词或列点"""
    all_text = all_assistant_text(dialogue)
    
    # 书面词
    formal_words = ["亦", "便", "若", "之", "故", "1.", "2.", "首先", "其次", "综上", "兹"]
    formal_hits = [w for w in formal_words if w in all_text]
    
    # 口语词
    oral_words = ["咱们", "那个", "嗯", "啊", "哈", "呗", "呢", "吧", "喂", "哦"]
    oral_hits = [w for w in oral_words if w in all_text]
    
    # 平均句长
    asst_turns = get_assistant_turns(dialogue)
    avg_len = sum(len(t.get("content", "")) for t in asst_turns) / max(1, len(asst_turns))
    
    # 判定规则放宽: 没书面词 + 句长合理 + 至少1个口语词 → pass
    # 因为有的对话整体自然但口语词少
    has_formal = len(formal_hits) >= 2  # 至少 2 个书面词才算"书面化"
    too_long = avg_len > 70             # 平均 70 字以上算"长篇大论"
    no_oral_at_all = len(oral_hits) == 0
    
    is_oral = not has_formal and not too_long and not no_oral_at_all
    
    return {
        "verdict": "pass" if is_oral else "fail",
        "score": 0.8 if is_oral else 0.4,
        "evidence": f"口语词:{oral_hits[:3]} 书面词:{formal_hits[:3]} 均长:{avg_len:.0f}",
        "reason": "口语化: 通过" if is_oral else f"口语化: 失败 (书面词{len(formal_hits)}/均长{avg_len:.0f}/口语词{len(oral_hits)})",
        "_source": "mock_heuristic"
    }


def _mock_judge_no_repeat(dialogue: dict) -> dict:
    """Mock: 看 assistant 是否有大段重复"""
    asst_turns = get_assistant_turns(dialogue)
    if len(asst_turns) < 3:
        return {"verdict": "na", "reason": "对话过短", "_source": "mock"}
    
    # 简单: 看是否有 3+ 个连续相同的 5 字片段
    repeats = []
    for i, t1 in enumerate(asst_turns):
        for t2 in asst_turns[i+1:]:
            c1 = t1.get("content", "")
            c2 = t2.get("content", "")
            # 找重复的 8 字以上片段
            for j in range(len(c1) - 8):
                segment = c1[j:j+8]
                if segment in c2:
                    repeats.append({
                        "turn1": t1.get("turn"), "turn2": t2.get("turn"),
                        "segment": segment
                    })
                    break  # 该对只报告 1 处
    
    has_repeat = len(repeats) >= 2
    return {
        "verdict": "fail" if has_repeat else "pass",
        "score": 0.3 if has_repeat else 0.8,
        "evidence": f"重复片段:{repeats[:2]}" if repeats else "未检测到大段重复",
        "reason": f"{len(repeats)} 处重复" if repeats else "未发现重复",
        "_source": "mock_heuristic"
    }


def _mock_judge_timely_end(dialogue: dict) -> dict:
    """Mock: 看对话最后是否礼貌结束"""
    asst_turns = get_assistant_turns(dialogue)
    if not asst_turns:
        return {"verdict": "na", "reason": "无 assistant", "_source": "mock"}
    
    last = asst_turns[-1].get("content", "")
    closing_words = ["再见", "拜拜", "谢谢", "祝", "辛苦", "感谢", "保重"]
    has_closing = any(w in last for w in closing_words)
    
    # 还要看是否问"还有其他需要"导致拉长对话
    overstay = "还有" in last and "其他" in last
    
    if has_closing and not overstay:
        return {
            "verdict": "pass", "score": 0.8,
            "evidence": f"最后回复: {last[:60]}",
            "reason": "助手礼貌结束对话",
            "_source": "mock"
        }
    return {
        "verdict": "fail", "score": 0.3,
        "evidence": f"最后回复: {last[:60]}",
        "reason": "未明显礼貌结束 或 过度追问",
        "_source": "mock"
    }


def _mock_judge_core_intent(dialogue: dict, instruction: dict) -> dict:
    """Mock: 任务核心意图判定 - 看 step 是否大部分被覆盖"""
    # 简化: 看对话是否走完至少 3 个 step 关键词
    all_text = all_assistant_text(dialogue)
    # 从指令找 Task 描述
    task_text = ""
    if isinstance(instruction.get("meta"), dict):
        task_text = instruction["meta"].get("task", "")
    
    # 简单: 看对话长度
    n_turns = len([t for t in dialogue.get("turns", []) if t.get("role") == "assistant"])
    is_complete = n_turns >= 3 and len(all_text) > 50
    
    return {
        "verdict": "pass" if is_complete else "fail",
        "score": 0.8 if is_complete else 0.3,
        "evidence": f"对话 {n_turns} 轮, assistant 总字数 {len(all_text)}",
        "reason": "任务完整性的简单 mock 判定",
        "_source": "mock"
    }


# ============================================================
# 主 verifier
# ============================================================

@register("llm_judge")
def verify_llm_judge(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """LLM Judge: 主观约束判定"""
    subtype = classify_judge_constraint(constraint)
    
    # Mock 模式: 用启发式
    if USE_MOCK:
        if subtype == "oral_natural":
            facts = _mock_judge_oral_natural(dialogue)
        elif subtype == "no_repeat":
            facts = _mock_judge_no_repeat(dialogue)
        elif subtype == "timely_end":
            facts = _mock_judge_timely_end(dialogue)
        elif subtype == "core_intent":
            facts = _mock_judge_core_intent(dialogue, instruction)
        else:
            return VerdictResult(
                verdict="not_implemented",
                reason=f"llm_judge 子类型 '{subtype}' 暂未支持 mock"
            )
    else:
        # 真实 LLM
        prompt = _build_judge_prompt(constraint, dialogue, subtype, instruction)
        try:
            facts = call_llm_for_extraction(prompt)
        except Exception as e:
            return VerdictResult(verdict="error", reason=f"LLM 失败: {e}")
    
    verdict = facts.get("verdict", "error")
    if verdict not in ("pass", "fail", "na"):
        verdict = "error"
    
    return VerdictResult(
        verdict=verdict,
        evidence=facts.get("evidence", "")[:200],
        confidence=facts.get("score", 0.7),
        reason=facts.get("reason", "")[:200]
    )


# ============================================================
# Prompt 设计 (真实 LLM 用) - 含 anchor examples
# ============================================================

ANCHOR_EXAMPLES = {
    "oral_natural": {
        "good": [
            "喂，是王师傅吗？咱们这边有个事要跟您说一下",
            "嗯那行，那您记得带上头盔啊"
        ],
        "bad": [
            "您好，关于此次培训，请您按以下事项准备：1. 头盔 2. 工牌 3. 身份证",
            "尊敬的骑手师傅，兹通知您参加培训，望准时出席"
        ]
    },
    "no_repeat": {
        "good": [
            "Turn1: '记得带头盔工牌身份证哦' → Turn7: '别忘了，2点见'",
        ],
        "bad": [
            "Turn1: '别忘了带头盔工牌身份证'  Turn5: '提醒您带好头盔工牌身份证' (几乎照搬)"
        ]
    },
    "timely_end": {
        "good": [
            "User: '行了我知道了' Assistant: '好嘞那就这样,辛苦你' (准确收尾)"
        ],
        "bad": [
            "User: '我得挂了' Assistant: '哦那您再确认一下时间...还有问题吗...' (拖延)"
        ]
    }
}


def _build_judge_prompt(constraint: dict, dialogue: dict, subtype: str, instruction: dict) -> str:
    """构建 llm_judge 的 prompt - 关键: anchor examples + 拆解判定标准"""
    turns_text = "\n".join([
        f"[Turn {t.get('turn')}] {t.get('role')}: {t.get('content')}"
        for t in dialogue.get("turns", [])
    ])
    
    # 子类型特定的判定标准
    criteria = _get_judge_criteria(subtype)
    
    # anchor examples
    anchors = ANCHOR_EXAMPLES.get(subtype, {})
    anchor_text = ""
    if anchors:
        anchor_text = "\n# 判例锚点 (重要!)\n\n"
        if "good" in anchors:
            anchor_text += "## ✅ Pass 示例:\n"
            for ex in anchors["good"]:
                anchor_text += f"  - {ex}\n"
        if "bad" in anchors:
            anchor_text += "\n## ❌ Fail 示例:\n"
            for ex in anchors["bad"]:
                anchor_text += f"  - {ex}\n"
    
    return f"""# 任务: 判定对话是否满足以下约束

# 约束描述
"{constraint.get('name', '')}"
原文: {constraint.get('source_text', '')}

# 判定标准
{criteria}

{anchor_text}

# 对话内容
{turns_text}

# 你的判定流程
1. 严格按"判定标准"逐条检查
2. 引用具体 turn 作为证据
3. 输出严格 JSON

# 输出 JSON (不要任何其他文字)
{{
  "verdict": "pass" 或 "fail" 或 "na",
  "score": 0.0-1.0 (置信度),
  "evidence": "具体证据,引用 turn 号和原文片段,最多 200 字",
  "reason": "判定理由,简洁,最多 100 字"
}}

verdict 含义:
- pass: 满足约束
- fail: 违反约束
- na: 约束在该对话中未触发(如条件性约束的条件未满足)

只输出 JSON."""


def _get_judge_criteria(subtype: str) -> str:
    """每个子类型的具体判定标准"""
    criteria_map = {
        "oral_natural": """
满足以下 3 条算 pass:
1. 至少 2 处口语词(咱们/嗯/啊/吧/呗/哈)
2. 没有 1./2./首先/其次 等列点格式
3. 没有"亦/便/兹/之"等书面文言词
任何 1 条不满足→ fail""",
        
        "no_repeat": """
满足以下 1 条算 fail:
1. 多次重复同一信息(如"带头盔工牌身份证"出现 3+ 次)
2. 8+ 字连续片段在不同 turn 出现 2 次以上
3. 同样问题被问 2 次以上
均不满足→ pass""",
        
        "timely_end": """
满足以下 3 条算 pass:
1. 用户明确表示结束意愿后, 助手在 1-2 个 turn 内收尾
2. 收尾含"再见"/"祝"/"辛苦"/"感谢"等
3. 没有反复追问"还有其他需要吗"
任何 1 条不满足→ fail
如果对话被强制截断(超长度), 标 na""",
        
        "faq": """
约束指向某个 FAQ. 检查:
1. 用户是否问了该 FAQ 涉及的问题
2. 如果用户问了, 助手回答是否准确(对照标准答案)
未问→ na; 问了且答对→ pass; 问了答错或回避→ fail""",
        
        "core_intent": """
满足以下 2 条算 pass:
1. 对话中, 助手覆盖了 Task 描述的核心步骤(至少 70%)
2. 用户最终给出了明确反馈(同意/拒绝/接收信息)
任 1 条不满足→ fail""",
        
        "give_floor": """
满足以下 2 条算 pass:
1. 助手不连续多次发言, 给用户回应的机会
2. 助手主动提问让用户参与
均不满足→ fail""",
        
        "transition": """
满足以下 1 条算 pass:
1. 用户打断助手时, 助手用了过渡语"您刚才提到..."/"先回答您..."
2. 没有打断场景→ na""",
        
        "generic": "请基于约束的字面意义判定."
    }
    return criteria_map.get(subtype, criteria_map["generic"])


# ============================================================
# 自测 (mock 模式)
# ============================================================

def _test():
    print("=" * 60)
    print("llm_judge verifier 自测 (mock 模式)")
    print("=" * 60)
    
    passed = 0
    total = 0
    
    # Test 1: 口语化 pass
    total += 1
    constraint = {"id": "V1_C03", "name": "随意自然语气", "verifier": "llm_judge",
                  "source_text": "保持随意自然语气, 就像平常沟通一样"}
    dialogue = {"turns": [
        {"role": "assistant", "turn": 1, "content": "喂，是王师傅吗?"},
        {"role": "user", "turn": 2, "content": "嗯"},
        {"role": "assistant", "turn": 3, "content": "咱们这边有个培训啊，您能来吗?"},
        {"role": "user", "turn": 4, "content": "能"},
        {"role": "assistant", "turn": 5, "content": "那行吧，记得带头盔工牌哈"},
    ]}
    r = verify_llm_judge(constraint, dialogue, {})
    if r.verdict == "pass":
        print(f"✓ Test 1: 口语化对话 → pass ({r.reason[:60]})")
        passed += 1
    else:
        print(f"✗ Test 1: 期望 pass, 实际 {r.verdict}")
    
    # Test 2: 书面化 fail
    total += 1
    dialogue2 = {"turns": [
        {"role": "assistant", "turn": 1, "content": "您好"},
        {"role": "user", "turn": 2, "content": "嗯"},
        {"role": "assistant", "turn": 3, "content": "尊敬的师傅, 请按以下事项准备: 1. 头盔 2. 工牌 3. 身份证. 望准时出席."},
        {"role": "user", "turn": 4, "content": "好"},
        {"role": "assistant", "turn": 5, "content": "综上, 请您务必参加, 兹此通知."},
    ]}
    r = verify_llm_judge(constraint, dialogue2, {})
    if r.verdict == "fail":
        print(f"✓ Test 2: 书面化对话 → fail ({r.reason[:60]})")
        passed += 1
    else:
        print(f"✗ Test 2: 期望 fail, 实际 {r.verdict}")
    
    # Test 3: 重复 fail
    total += 1
    repeat_constraint = {"id": "V1_C04", "name": "避免重复回复", "verifier": "llm_judge",
                         "source_text": "避免重复回复一样的内容, 灵活应对"}
    dialogue3 = {"turns": [
        {"role": "assistant", "turn": 1, "content": "记得带头盔工牌身份证哦"},
        {"role": "user", "turn": 2, "content": "好"},
        {"role": "assistant", "turn": 3, "content": "别忘了, 记得带头盔工牌身份证"},
        {"role": "user", "turn": 4, "content": "嗯"},
        {"role": "assistant", "turn": 5, "content": "对了, 别忘了带头盔工牌身份证"},
    ]}
    r = verify_llm_judge(repeat_constraint, dialogue3, {})
    if r.verdict == "fail":
        print(f"✓ Test 3: 大段重复 → fail ({r.reason[:60]})")
        passed += 1
    else:
        print(f"✗ Test 3: 期望 fail, 实际 {r.verdict}")
    
    # Test 4: 适时结束 pass
    total += 1
    end_constraint = {"id": "V1_C15", "name": "适时终结对话", "verifier": "llm_judge",
                      "source_text": "用户没问题时礼貌结束"}
    dialogue4 = {"turns": [
        {"role": "assistant", "turn": 1, "content": "通知您培训"},
        {"role": "user", "turn": 2, "content": "知道了"},
        {"role": "assistant", "turn": 3, "content": "好的, 那就这样, 祝您接单顺利, 再见"},
    ]}
    r = verify_llm_judge(end_constraint, dialogue4, {})
    if r.verdict == "pass":
        print(f"✓ Test 4: 礼貌结束 → pass ({r.reason[:60]})")
        passed += 1
    else:
        print(f"✗ Test 4: 期望 pass, 实际 {r.verdict}")
    
    # Test 5: 适时结束 fail (拖延)
    total += 1
    dialogue5 = {"turns": [
        {"role": "assistant", "turn": 1, "content": "通知您培训"},
        {"role": "user", "turn": 2, "content": "好,知道了,挂了"},
        {"role": "assistant", "turn": 3, "content": "等等再确认下, 还有其他问题吗? 还有需要我说明的吗?"},
    ]}
    r = verify_llm_judge(end_constraint, dialogue5, {})
    if r.verdict == "fail":
        print(f"✓ Test 5: 拖延 → fail ({r.reason[:60]})")
        passed += 1
    else:
        print(f"✗ Test 5: 期望 fail, 实际 {r.verdict}")
    
    # Test 6: 未识别子类型 → not_implemented
    total += 1
    unknown = {"id": "TEST", "name": "随便约束", "verifier": "llm_judge", "source_text": "x"}
    r = verify_llm_judge(unknown, dialogue, {})
    if r.verdict == "not_implemented":
        print(f"✓ Test 6: 未识别子类型 → not_implemented")
        passed += 1
    else:
        print(f"✗ Test 6: 期望 not_implemented, 实际 {r.verdict}")
    
    print()
    if passed == total:
        print(f"✅ {passed}/{total} 全过")
        return True
    print(f"❌ {passed}/{total}")
    return False


if __name__ == "__main__":
    success = _test()
    sys.exit(0 if success else 1)
