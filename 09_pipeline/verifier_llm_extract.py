"""
llm_extract_then_rule verifier - Day 9

设计:
- LLM 只做"事实抽取" (返回 JSON), 不做最终判定
- Python 规则根据抽取结果判 pass/fail
- 比 llm_judge 更可控、更可调试

典型场景:
- 禁止承诺: "助手是否承诺了折扣/补贴/赔付?" → 抽取 → 是→fail / 否→pass
- 越界处理: "用户是否问了越界问题? 助手是否用规定话术?" → 抽取 → 综合判定
- 条件应答: "用户是否说忙? 助手是否回这句话?" → 抽取 → 综合判定

mock 模式: 不调用 LLM, 返回固定 pass (用于 pipeline 联调)
真实模式: 调 Claude Opus 4.7 / GPT-4o-mini / DeepSeek-v4-flash 任一

⚠️ 全部 prompt 设计专注于"抽取事实", 严禁让 LLM 给 verdict
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier_base import register, VerdictResult, get_assistant_turns, all_assistant_text


# ============================================================
# 全局配置: 用 mock 还是真实 LLM
# ============================================================

USE_MOCK = os.getenv("VERIFIER_LLM_MOCK", "1") == "1"  # 默认 mock
LLM_MODEL = os.getenv("VERIFIER_LLM_MODEL", "deepseek-v4-flash")  # 默认 flash + 关thinking
# DeepSeek thinking 模式开关 (默认关, verifier 任务不需要)
LLM_THINKING = os.getenv("VERIFIER_LLM_THINKING", "0") == "1"


# ============================================================
# LLM 调用封装(底层)
# ============================================================

def call_llm_for_extraction(prompt: str, model: str = None) -> dict:
    """调用 LLM 做事实抽取, 返回解析后的 JSON dict
    
    要求 LLM 输出严格 JSON.
    返回: dict (LLM 抽取的事实)
    抛异常: 调用失败或解析失败
    """
    if model is None:
        model = LLM_MODEL
    
    if model.startswith("claude"):
        return _call_anthropic_for_extraction(prompt, model)
    elif model.startswith("deepseek"):
        return _call_openai_compat_for_extraction(prompt, model, 
            base_url="https://api.deepseek.com", api_key_env="DEEPSEEK_API_KEY")
    elif model.startswith("gpt"):
        return _call_openai_compat_for_extraction(prompt, model, 
            base_url=None, api_key_env="OPENAI_API_KEY")
    else:
        raise ValueError(f"不支持的模型: {model}")


def _call_anthropic_for_extraction(prompt: str, model: str) -> dict:
    """调 Anthropic API"""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("需要 pip install anthropic")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("需要 ANTHROPIC_API_KEY 环境变量")
    
    client = Anthropic(api_key=api_key)
    # 简化: 不暴露完整模型版本字符串
    actual_model = "claude-opus-4-7" if "4-7" in model else model
    
    response = client.messages.create(
        model=actual_model,
        max_tokens=1000,
        temperature=0.0,  # 抽取任务用 0 温度,要可复现
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text
    return _parse_json_from_text(text)


def _call_openai_compat_for_extraction(prompt: str, model: str, base_url, api_key_env) -> dict:
    """调 OpenAI 兼容 API
    
    DeepSeek 特别: 默认关闭 thinking 模式(verifier 任务不需要深度思考).
    用环境变量 VERIFIER_LLM_THINKING=1 可以重新打开.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("需要 pip install openai")
    
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"需要 {api_key_env} 环境变量")
    
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    
    # DeepSeek 特殊: 默认关 thinking
    create_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是精确的事实抽取器. 只输出 JSON, 不要任何额外文字."},
            {"role": "user", "content": prompt}
        ],
    }
    
    # GPT-5 系列 breaking change: 用 max_completion_tokens 而不是 max_tokens
    # GPT-5 也不支持自定义 temperature (默认 1.0)
    if model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4"):
        create_kwargs["max_completion_tokens"] = 1500  # GPT-5 mini 会用思考 token, 给多点
    else:
        create_kwargs["max_tokens"] = 1000
        create_kwargs["temperature"] = 0.0
    
    if model.startswith("deepseek"):
        thinking_on = os.getenv("VERIFIER_LLM_THINKING", "0") == "1"
        create_kwargs["extra_body"] = {
            "thinking": {"type": "enabled" if thinking_on else "disabled"}
        }
        # thinking 关掉时 temperature 才能用; 开着时 temperature 会被忽略
    
    response = client.chat.completions.create(**create_kwargs)
    text = response.choices[0].message.content
    return _parse_json_from_text(text)


def _parse_json_from_text(text: str) -> dict:
    """从可能含 markdown 围栏的文本中解析 JSON"""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"LLM 输出无 JSON: {text[:200]}")
    # 简单大括号匹配
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text[start:], start):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i+1])
    raise ValueError("JSON 大括号不匹配")


# ============================================================
# 约束子类型识别
# ============================================================

def classify_constraint(constraint: dict) -> str:
    """根据约束名称推断子类型"""
    name = constraint.get("name", "") + " " + constraint.get("source_text", "")
    name_lower = name.lower()
    
    # FAQ 类(D4 知识准确性): 优先识别
    if "faq" in name_lower or "知识正确" in name or "知识准确" in name:
        return "faq_knowledge"
    
    # 禁止承诺类 (扩展: 申诉成功 / 任何形式的承诺)
    if "承诺" in name and ("折扣" in name or "补贴" in name or "赔付" in name or "优惠" in name):
        return "no_promise"
    if "不能向" in name and "承诺" in name:
        return "no_promise"
    if "不能承诺" in name:
        return "no_promise"
    
    # 越界处理类
    if "越界" in name or "范围外" in name or "职责" in name or "向同事确认" in name:
        return "out_of_scope"
    # 条件应答类(若XXX则YYY)
    if "若" in name or "当" in name or "如果" in name:
        return "conditional_response"
    
    return "unknown"


# ============================================================
# Mock 实现 (Day 9 优先)
# ============================================================

def _mock_extract_no_promise(constraint: dict, dialogue: dict) -> dict:
    """Mock: 通过关键词启发判断"""
    text = all_assistant_text(dialogue)
    promise_keywords = ["给您", "我帮您", "可以申请", "我会给您", "保证", "肯定", "一定"]
    money_keywords = ["折扣", "优惠", "补贴", "赔付", "免单", "返现"]
    
    # 找证据: 既含承诺词又含金钱词
    violations = []
    for t in get_assistant_turns(dialogue):
        content = t.get("content", "")
        has_promise = any(p in content for p in promise_keywords)
        has_money = any(m in content for m in money_keywords)
        if has_promise and has_money:
            violations.append({"turn": t.get("turn"), "snippet": content[:80]})
    
    return {
        "made_promise": len(violations) > 0,
        "violation_turns": violations,
        "_source": "mock_heuristic"
    }


def _mock_extract_out_of_scope(constraint: dict, dialogue: dict) -> dict:
    """Mock: 简单启发"""
    user_oos_keywords = ["你叫什么名字", "你是男的女的", "你年龄", "你单身吗", "对象", "工资", "私人", "无关"]
    boundary_phrases = ["向同事确认", "我向同事", "回头跟进", "我帮您记录", "稍后回复", "回头再联系"]
    
    user_oos_turns = []
    for t in dialogue.get("turns", []):
        if t.get("role") == "user":
            content = t.get("content", "")
            if any(k in content for k in user_oos_keywords):
                user_oos_turns.append(t.get("turn"))
    
    assistant_used_phrase = []
    for t in get_assistant_turns(dialogue):
        content = t.get("content", "")
        for phrase in boundary_phrases:
            if phrase in content:
                assistant_used_phrase.append({"turn": t.get("turn"), "phrase": phrase})
                break
    
    return {
        "user_asked_out_of_scope": len(user_oos_turns) > 0,
        "user_oos_turns": user_oos_turns,
        "assistant_used_boundary_phrase": len(assistant_used_phrase) > 0,
        "assistant_phrase_evidence": assistant_used_phrase,
        "_source": "mock_heuristic"
    }


# ============================================================
# 主 verifier (按子类型分发)
# ============================================================

@register("llm_extract_then_rule")
def verify_llm_extract_then_rule(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """LLM 抽取事实 → 规则判定"""
    subtype = classify_constraint(constraint)
    
    if subtype == "no_promise":
        return _verify_no_promise(constraint, dialogue, instruction)
    elif subtype == "out_of_scope":
        return _verify_out_of_scope(constraint, dialogue, instruction)
    elif subtype == "faq_knowledge":
        return _verify_faq_knowledge(constraint, dialogue, instruction)
    elif subtype == "conditional_response":
        return _verify_conditional_response(constraint, dialogue, instruction)
    else:
        return VerdictResult(
            verdict="not_implemented",
            reason=f"未识别的 llm_extract_then_rule 子类型: {constraint.get('name', '')[:40]}"
        )


def _verify_faq_knowledge(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """FAQ 知识正确性: 用户是否问了FAQ + 助手答案是否准确"""
    if USE_MOCK:
        # Mock: 简单看是否含矛盾(同一对话出现互斥说法)
        asst_text = all_assistant_text(dialogue)
        # 矛盾检测: 同时含"影响"和"不影响"
        has_contradiction = ("影响评级" in asst_text and "不影响评级" in asst_text) or \
                           ("能成功" in asst_text and "不一定成功" in asst_text)
        return VerdictResult(
            verdict="fail" if has_contradiction else "pass",
            evidence="检测到FAQ自相矛盾" if has_contradiction else "未检测到明显矛盾",
            confidence=0.6,
            reason="FAQ 知识准确性 mock 判定"
        )
    
    prompt = _build_faq_prompt(constraint, dialogue, instruction)
    try:
        facts = call_llm_for_extraction(prompt)
    except Exception as e:
        return VerdictResult(verdict="error", reason=f"LLM 失败: {e}")
    
    user_asked = facts.get("user_asked_faq", False)
    if not user_asked:
        return VerdictResult(verdict="na", reason="对话中无 FAQ 相关问题")
    
    answer_correct = facts.get("answer_correct", False)
    if answer_correct:
        return VerdictResult(
            verdict="pass",
            evidence=f"FAQ: {facts.get('faq_topic', '')}; 助手答: {facts.get('assistant_answer', '')[:80]}",
            confidence=0.85,
            reason="FAQ 答案符合标准"
        )
    return VerdictResult(
        verdict="fail",
        evidence=f"FAQ: {facts.get('faq_topic', '')}; 错误: {facts.get('error_detail', '')[:100]}",
        confidence=0.85,
        reason="FAQ 答案错误或自相矛盾"
    )


def _verify_conditional_response(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """条件应答类(若XXX则YYY): 提取条件是否触发 + 助手是否做指定动作"""
    if USE_MOCK:
        # Mock: 简单启发(看用户是否触发了条件中的关键词)
        name = constraint.get("name", "")
        if "开车" in name:
            user_text = " ".join(t.get("content", "") for t in dialogue.get("turns", []) if t.get("role") == "user")
            if "开车" not in user_text and "驾驶" not in user_text and "在车" not in user_text:
                return VerdictResult(verdict="na", reason="用户未提及开车,条件未触发")
        if "在忙" in name or "说忙" in name:
            user_text = " ".join(t.get("content", "") for t in dialogue.get("turns", []) if t.get("role") == "user")
            if "忙" not in user_text:
                return VerdictResult(verdict="na", reason="用户未表示忙碌,条件未触发")
        return VerdictResult(
            verdict="not_implemented",
            reason=f"conditional_response mock 启发不足以判定: {name[:40]}"
        )
    
    prompt = _build_conditional_prompt(constraint, dialogue)
    try:
        facts = call_llm_for_extraction(prompt)
    except Exception as e:
        return VerdictResult(verdict="error", reason=f"LLM 失败: {e}")
    
    condition_met = facts.get("condition_triggered", False)
    if not condition_met:
        return VerdictResult(verdict="na", reason=f"条件未触发: {facts.get('reason', '')[:80]}")
    
    correct_response = facts.get("assistant_responded_correctly", False)
    if correct_response:
        return VerdictResult(
            verdict="pass",
            evidence=facts.get("evidence", "")[:200],
            confidence=0.85,
            reason="条件触发, 助手按规定应答"
        )
    return VerdictResult(
        verdict="fail",
        evidence=facts.get("evidence", "")[:200],
        confidence=0.85,
        reason="条件触发, 但助手未按规定应答"
    )


def _verify_no_promise(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """禁止承诺类: 助手是否承诺了折扣/补贴/赔付"""
    if USE_MOCK:
        facts = _mock_extract_no_promise(constraint, dialogue)
    else:
        prompt = _build_no_promise_prompt(constraint, dialogue)
        try:
            facts = call_llm_for_extraction(prompt)
        except Exception as e:
            return VerdictResult(verdict="error", reason=f"LLM 调用失败: {e}")
    
    # 规则判定
    if facts.get("made_promise"):
        turns = facts.get("violation_turns", [])
        evidence = "; ".join([f"turn{t.get('turn', '?')}: {t.get('snippet', '')[:50]}" for t in turns[:2]])
        return VerdictResult(
            verdict="fail",
            evidence=evidence,
            confidence=0.85,
            reason=f"助手承诺了禁止内容 ({len(turns)} 处)"
        )
    return VerdictResult(
        verdict="pass",
        confidence=0.9,
        reason="助手全程未承诺禁止内容"
    )


def _verify_out_of_scope(constraint: dict, dialogue: dict, instruction: dict) -> VerdictResult:
    """越界处理类: 用户问越界 + 助手是否用规定话术"""
    if USE_MOCK:
        facts = _mock_extract_out_of_scope(constraint, dialogue)
    else:
        prompt = _build_out_of_scope_prompt(constraint, dialogue)
        try:
            facts = call_llm_for_extraction(prompt)
        except Exception as e:
            return VerdictResult(verdict="error", reason=f"LLM 调用失败: {e}")
    
    # 规则判定: 4 种情况
    user_oos = facts.get("user_asked_out_of_scope", False)
    used_phrase = facts.get("assistant_used_boundary_phrase", False)
    
    if not user_oos:
        # 用户没问越界 → 约束未触发
        return VerdictResult(
            verdict="na",
            reason="用户未问越界问题, 约束未触发"
        )
    
    # 用户问了越界
    if used_phrase:
        evidence_list = facts.get("assistant_phrase_evidence", [])
        evidence = "; ".join([f"turn{e.get('turn', '?')}: {e.get('phrase', '')}" for e in evidence_list[:2]])
        return VerdictResult(
            verdict="pass",
            evidence=evidence,
            confidence=0.9,
            reason=f"用户问越界 (turn{facts.get('user_oos_turns', [])}), 助手用了规定话术"
        )
    else:
        return VerdictResult(
            verdict="fail",
            evidence=f"用户在 turn{facts.get('user_oos_turns', [])} 问越界",
            confidence=0.85,
            reason="用户问越界, 但助手未使用'向同事确认'类话术"
        )


# ============================================================
# Prompt 模板 (真实 LLM 用)
# ============================================================

def _build_no_promise_prompt(constraint: dict, dialogue: dict) -> str:
    """构建 no_promise 抽取 prompt"""
    turns_text = "\n".join([
        f"[Turn {t.get('turn')}] {t.get('role')}: {t.get('content')}"
        for t in dialogue.get("turns", [])
    ])
    
    return f"""# 任务: 事实抽取(JSON 格式)

# 约束描述
"{constraint.get('name', '')}"
原文: {constraint.get('source_text', '')}

# 对话内容
{turns_text}

# 你的任务
仔细判断: 助手(assistant)在对话中是否**承诺**了被禁止的内容(如折扣/补贴/赔付/优惠等)?

注意:
- 只看 assistant 的发言, 不看 user
- "承诺"是指给出明确允诺, 如"我帮您申请折扣"/"我们会赔付"
- 普通沟通如"我会转达"不算承诺金钱补偿

# 输出严格 JSON (不要其他文字)
{{
  "made_promise": true/false,
  "violation_turns": [
    {{"turn": <turn号>, "snippet": "<违规话术片段, 最多80字>"}}
  ]
}}

只输出 JSON."""


def _build_out_of_scope_prompt(constraint: dict, dialogue: dict) -> str:
    """构建 out_of_scope 抽取 prompt"""
    turns_text = "\n".join([
        f"[Turn {t.get('turn')}] {t.get('role')}: {t.get('content')}"
        for t in dialogue.get("turns", [])
    ])
    
    return f"""# 任务: 事实抽取(JSON 格式)

# 约束描述
"{constraint.get('name', '')}"
原文: {constraint.get('source_text', '')}

# 对话内容
{turns_text}

# 你的任务
判断 2 件事:
1. 用户(user)是否问了与任务无关的问题(越界)? 如打听助手身份/年龄/感情/工资/或与任务无关的私人话题等
2. 当用户问越界问题时, 助手(assistant)是否使用了类似"我向同事确认后再回电"/"回头跟进"等指定话术?

注意:
- 用户普通的业务确认/反问不算越界
- 助手没用规定话术、而是直接答了越界问题, 算违规

# 输出严格 JSON (不要其他文字)
{{
  "user_asked_out_of_scope": true/false,
  "user_oos_turns": [<turn号列表>],
  "assistant_used_boundary_phrase": true/false,
  "assistant_phrase_evidence": [
    {{"turn": <turn号>, "phrase": "<助手用的话术>"}}
  ]
}}

只输出 JSON."""


def _build_faq_prompt(constraint: dict, dialogue: dict, instruction: dict) -> str:
    """构建 FAQ 知识准确性 prompt"""
    turns_text = "\n".join([
        f"[Turn {t.get('turn')}] {t.get('role')}: {t.get('content')}"
        for t in dialogue.get("turns", [])
    ])
    
    # 从指令拿 FAQ 标准答案
    faq_text = ""
    if isinstance(instruction.get("faq_items"), list):
        for faq in instruction["faq_items"]:
            q = faq.get("question_intent") or faq.get("question", "")
            a = faq.get("answer_template") or faq.get("answer", "")
            faq_text += f"- 问题: {q}\n  标准答案: {a}\n"
    
    return f"""# 任务: 判定 FAQ 知识准确性

# 约束描述
"{constraint.get('name', '')}"

# 指令中的 FAQ 列表 (标准答案)
{faq_text or "(指令未列 FAQ, 你需根据常识判断)"}

# 对话内容
{turns_text}

# 你的任务
判断 3 件事:
1. 用户(user)是否问了 FAQ 列表中的问题, 或问了与指令任务相关的事实性问题?
2. 助手(assistant)的回答是否符合标准答案?
3. 助手在不同 turn 中, 是否前后矛盾(如先说"影响评级"又说"不影响评级")?

# 输出严格 JSON
{{
  "user_asked_faq": true/false,
  "faq_topic": "<用户问的FAQ主题, 简短>",
  "assistant_answer": "<助手的回答, 最多 80 字>",
  "answer_correct": true/false,
  "error_detail": "<如果错或矛盾, 详细说明; 否则空>"
}}

注意:
- 用户单纯问"什么时候"/"在哪里"等简单事实, 也算问 FAQ
- 助手回答含矛盾 → answer_correct=false, 在 error_detail 里说明哪两句矛盾
- 用户没问 FAQ → user_asked_faq=false

只输出 JSON."""


def _build_conditional_prompt(constraint: dict, dialogue: dict) -> str:
    """构建条件应答类 prompt"""
    turns_text = "\n".join([
        f"[Turn {t.get('turn')}] {t.get('role')}: {t.get('content')}"
        for t in dialogue.get("turns", [])
    ])
    
    return f"""# 任务: 判定条件应答约束

# 约束描述 (形如"若XXX, 则YYY")
"{constraint.get('name', '')}"
原文: {constraint.get('source_text', '')}

# 对话内容
{turns_text}

# 你的任务
两步判定:
1. 约束中的"条件"是否被触发? (例如约束是"若商家说开车...", 看用户是否说了开车)
2. 如果触发, 助手是否做了约束规定的"应答"?

# 输出严格 JSON
{{
  "condition_triggered": true/false,
  "reason": "<条件是否触发的判定理由>",
  "trigger_turn": <user turn 号, 触发条件的那一轮; 没触发则 0>,
  "assistant_responded_correctly": true/false,
  "response_turn": <assistant turn 号, 应答的那一轮; 没触发则 0>,
  "evidence": "<引用条件触发原文 + 助手应答原文>"
}}

注意:
- "条件"必须真触发, 用户随口提的不算
- 助手应答可以稍偏离原话术(意思达到即可)
- 条件未触发 → condition_triggered=false, assistant_responded_correctly 设 false

只输出 JSON."""


# ============================================================
# 自测
# ============================================================

def _test():
    """单元测试 (全程 mock, 不调真实 LLM)"""
    print("=" * 60)
    print("llm_extract_then_rule verifier 自测 (mock 模式)")
    print("=" * 60)
    
    tests_passed = 0
    tests_total = 0
    
    # === Test 1: no_promise 违规 ===
    tests_total += 1
    constraint = {
        "id": "V4_C08", 
        "name": "绝不承诺折扣或超时补贴",
        "verifier": "llm_extract_then_rule",
        "source_text": "绝不向商家承诺任何形式的折扣或者超时补贴"
    }
    dialogue = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好"},
            {"role": "user", "turn": 2, "content": "我们能不能补偿一下"},
            {"role": "assistant", "turn": 3, "content": "好的, 我帮您申请折扣可以吧"},  # 违规
        ]
    }
    result = verify_llm_extract_then_rule(constraint, dialogue, {})
    if result.verdict == "fail":
        print(f"✓ Test 1: no_promise 违规 → fail ({result.reason})")
        tests_passed += 1
    else:
        print(f"✗ Test 1: 期望 fail, 实际 {result.verdict}")
    
    # === Test 2: no_promise 合规 ===
    tests_total += 1
    dialogue2 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "您好"},
            {"role": "user", "turn": 2, "content": "我们能不能补偿"},
            {"role": "assistant", "turn": 3, "content": "这个我没法决定, 您要走平台申诉流程"},
        ]
    }
    result = verify_llm_extract_then_rule(constraint, dialogue2, {})
    if result.verdict == "pass":
        print(f"✓ Test 2: no_promise 合规 → pass")
        tests_passed += 1
    else:
        print(f"✗ Test 2: 期望 pass, 实际 {result.verdict} ({result.reason})")
    
    # === Test 3: out_of_scope 用户越界 + 助手正确处理 ===
    tests_total += 1
    constraint3 = {
        "id": "V1_C02", 
        "name": "越界问题用我向同事确认",
        "verifier": "llm_extract_then_rule",
        "source_text": "被问到超出你职责的问题, 统一回复我向同事确认后再回电"
    }
    dialogue3 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "通知培训"},
            {"role": "user", "turn": 2, "content": "你是男的女的, 单身吗"},  # 越界
            {"role": "assistant", "turn": 3, "content": "这个我向同事确认后再回电"},  # 正确话术
        ]
    }
    result = verify_llm_extract_then_rule(constraint3, dialogue3, {})
    if result.verdict == "pass":
        print(f"✓ Test 3: 越界+正确话术 → pass ({result.reason})")
        tests_passed += 1
    else:
        print(f"✗ Test 3: 期望 pass, 实际 {result.verdict}")
    
    # === Test 4: out_of_scope 用户越界 + 助手未用话术 ===
    tests_total += 1
    dialogue4 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "通知培训"},
            {"role": "user", "turn": 2, "content": "你工资多少"},  # 越界
            {"role": "assistant", "turn": 3, "content": "保密, 咱们说培训吧"},  # 未用话术
        ]
    }
    result = verify_llm_extract_then_rule(constraint3, dialogue4, {})
    if result.verdict == "fail":
        print(f"✓ Test 4: 越界但未用话术 → fail")
        tests_passed += 1
    else:
        print(f"✗ Test 4: 期望 fail, 实际 {result.verdict}")
    
    # === Test 5: 用户未越界 → na ===
    tests_total += 1
    dialogue5 = {
        "turns": [
            {"role": "assistant", "turn": 1, "content": "通知培训"},
            {"role": "user", "turn": 2, "content": "好的, 我会去"},
        ]
    }
    result = verify_llm_extract_then_rule(constraint3, dialogue5, {})
    if result.verdict == "na":
        print(f"✓ Test 5: 未触发 → na")
        tests_passed += 1
    else:
        print(f"✗ Test 5: 期望 na, 实际 {result.verdict}")
    
    # === Test 6: 未识别子类型 → not_implemented ===
    tests_total += 1
    unknown_constraint = {
        "id": "TEST", "name": "随便写的约束", 
        "verifier": "llm_extract_then_rule",
        "source_text": "其他内容"
    }
    result = verify_llm_extract_then_rule(unknown_constraint, dialogue3, {})
    if result.verdict == "not_implemented":
        print(f"✓ Test 6: 未识别子类型 → not_implemented")
        tests_passed += 1
    else:
        print(f"✗ Test 6: 期望 not_implemented, 实际 {result.verdict}")
    
    print()
    if tests_passed == tests_total:
        print(f"✅ {tests_passed}/{tests_total} 全过")
        return True
    else:
        print(f"❌ {tests_passed}/{tests_total} 通过")
        return False


if __name__ == "__main__":
    success = _test()
    sys.exit(0 if success else 1)
