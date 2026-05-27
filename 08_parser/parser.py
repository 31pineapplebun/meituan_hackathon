"""指令解析器主体

输入: 指令 Markdown 文本(V1.md / V2.md / 示例1.md 等)
输出: ParsedInstruction (含 atomic_constraints + faq_items + flow_steps + meta)

架构 (三层):
1. 规则提取层 (确定性): 抽取 ${变量}, Constraints 编号项, FAQ 项, Step 项
2. LLM 增强层: 用 LLM 给每条约束打 scoring_dimension / verifier / is_critical
3. 校验层: 输出经过 dataclass.validate() 严格校验

设计选择:
- 不依赖 pydantic, 用标准库 + 自定义校验
- LLM 调用支持 mock 模式 (--mock)
- 支持 DeepSeek / OpenAI / Anthropic 三种 API
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# 让脚本能从 day6/ 直接 import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser_schema import (
    ParsedInstruction, AtomicConstraint, FAQItem, FlowStep, InstructionMeta,
    VALID_DIMENSIONS, VALID_VERIFIERS
)


# =====================================================================
# 第一层: 规则提取(确定性)
# =====================================================================

def extract_section(text: str, section_name: str) -> str:
    """从 Markdown 中提取某个 # Section 下的内容
    
    兼容:
    - # Section / ## Section
    - # Section: (官方 sample 2 格式)
    - # Section (FAQ) (官方 sample 1 的 'Knowledge Points (FAQ)')
    """
    # header 后允许有 : 或括号说明, 但不允许有其他文字直接跟在 section_name 后
    pattern = rf"^#{{1,3}}\s*{re.escape(section_name)}\s*[:\:]?\s*\n+(.+?)(?=\n#[^#]|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_variables(text: str) -> list[str]:
    """提取所有 ${变量} 占位符"""
    return sorted(set(re.findall(r"\$\{([^}]+)\}", text)))


def extract_constraints_raw(text: str) -> list[str]:
    """从 # Constraints 段提取编号项的原文
    
    支持两种格式:
    - 数字编号: "1. xxx\n2. xxx"
    - 短横线列表: "- xxx\n- xxx"
    """
    cs_text = extract_section(text, "Constraints")
    if not cs_text:
        return []
    
    # 优先用数字编号
    items = re.findall(r"^\s*\d+\.\s*(.+?)(?=\n\s*\d+\.|\Z)", cs_text, re.MULTILINE | re.DOTALL)
    if items:
        return [item.strip().replace("\n", " ") for item in items]
    
    # 备选: 短横线列表 (兼容官方 sample 格式)
    items = []
    current = []
    for line in cs_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            # 新条目开始
            if current:
                items.append(" ".join(current).strip())
            current = [stripped[2:].strip()]
        elif stripped and current and not stripped.startswith("#"):
            # 继续上一条 (多行)
            current.append(stripped)
    if current:
        items.append(" ".join(current).strip())
    # 去除空项 + 粗体标记
    items = [re.sub(r"\*\*([^*]+)\*\*", r"\1", item) for item in items if item]
    return items


def extract_faq_raw(text: str) -> list[tuple[str, str]]:
    """提取 # Knowledge Points / FAQ 部分,返回 [(问题意图, 答案), ...]"""
    # 尝试多种段标题
    faq_text = None
    for header in ["Knowledge Points (FAQ)", "Knowledge Points", "FAQ"]:
        faq_text = extract_section(text, header)
        if faq_text:
            break
    if not faq_text:
        return []
    
    # 每条 FAQ: 支持多种格式
    #   - 问题 → 答案
    #   - 问题: 答案 (中英文冒号)
    #   - 问题陈述句 (无分隔符, 整条作为一条 FAQ 知识点)
    items = []
    for line in faq_text.split("\n"):
        line = line.strip()
        if not line.startswith("-"):
            continue
        content = line[1:].strip()
        # 去掉 markdown 粗体
        content_clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", content)
        
        # 尝试用 → / -> / 中文冒号 / 英文冒号 切分
        for sep in ["→", "->", "：", ":"]:
            if sep in content_clean:
                parts = content_clean.split(sep, 1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    items.append((parts[0].strip(), parts[1].strip()))
                    break
        else:
            # 没找到分隔符, 整条作为知识点 (问题意图 = 前 20 字, 答案 = 全文)
            if len(content_clean) >= 10:
                summary = content_clean[:30].rstrip("，。") + ("..." if len(content_clean) > 30 else "")
                items.append((summary, content_clean))
    return items


def extract_flow_steps_raw(text: str) -> list[tuple[str, str]]:
    """提取 # Call Flow 中的 step,返回 [(step_id, 描述), ...]
    
    支持嵌套(3.1 3.2)和分支标记(**分支**)
    """
    cf_text = extract_section(text, "Call Flow")
    if not cf_text:
        return []
    
    steps = []
    for line in cf_text.split("\n"):
        line_stripped = line.strip()
        # 匹配 "1. ..." 或 "3.1 ..." 或 "- 3.1 ..." 等
        # 主步骤: 单数字
        m_main = re.match(r"^(\d+)\.\s+(.+)$", line_stripped)
        # 子步骤: x.y 格式
        m_sub = re.match(r"^[-\s]*(\d+\.\d+)\s+(.+)$", line_stripped)
        
        if m_sub:
            sid = m_sub.group(1)
            desc = m_sub.group(2).strip()
            steps.append((f"S{sid}", desc))
        elif m_main:
            sid = m_main.group(1)
            desc = m_main.group(2).strip()
            steps.append((f"S{sid}", desc))
    
    return steps


# =====================================================================
# 标准元约束库 (项目级通用约束,所有指令都注入)
# =====================================================================

META_CONSTRAINTS_TEMPLATE = [
    {
        "name_suffix": "开场白含必要变量",
        "scoring_dimension": "D2_task_completion",
        "verifier": "rule_pattern",
        "is_critical": True,
        "weight": 3,
        "source_text_template": "首轮(Opening Line)应包含: {variables}",
    },
    {
        "name_suffix": "所有变量正确替换无残留 ${}",
        "scoring_dimension": "D3_constraint_compliance",
        "verifier": "rule",
        "is_critical": True,
        "weight": 3,
        "source_text_template": "对话中不能出现未替换的 ${{var}} 占位符",
    },
    {
        "name_suffix": "任务核心意图完成",
        "scoring_dimension": "D2_task_completion",
        "verifier": "llm_judge",
        "is_critical": True,
        "weight": 4,
        "source_text_template": "任务目标: {task}",
    },
    {
        "name_suffix": "适时终结对话",
        "scoring_dimension": "D5_dialogue_quality",
        "verifier": "llm_judge",
        "is_critical": False,
        "weight": 2,
        "source_text_template": "对话应在任务完成后自然结束,不冗长拖沓",
    },
    {
        "name_suffix": "FAQ知识正确",
        "scoring_dimension": "D4_knowledge_accuracy",
        "verifier": "llm_extract_then_rule",
        "is_critical": False,
        "weight": 2,
        "source_text_template": "对FAQ问题的回答应准确,关键事实: {key_facts}",
    },
]


def add_meta_constraints(parsed: ParsedInstruction) -> None:
    """注入标准元约束(原地修改 atomic_constraints)"""
    offset = len(parsed.atomic_constraints)
    
    for idx, tpl in enumerate(META_CONSTRAINTS_TEMPLATE, 1):
        # 渲染 source_text
        source_text = tpl["source_text_template"]
        if "{variables}" in source_text:
            source_text = source_text.format(
                variables=", ".join(f"${{{v}}}" for v in parsed.meta.variables) or "(无)"
            )
        elif "{task}" in source_text:
            source_text = source_text.format(task=parsed.meta.task or "(未指定)")
        elif "{key_facts}" in source_text:
            all_facts = []
            for faq in parsed.faq_items:
                all_facts.extend(faq.key_facts)
            source_text = source_text.format(key_facts=", ".join(all_facts) or "(无)")
        
        # 跳过没有变量时的"变量替换"约束(没意义)
        if tpl["name_suffix"] == "所有变量正确替换无残留 ${}" and not parsed.meta.variables:
            continue
        if tpl["name_suffix"] == "开场白含必要变量" and not parsed.meta.variables:
            continue
        # 跳过没有 FAQ 时的"FAQ知识正确"约束
        if tpl["name_suffix"] == "FAQ知识正确" and not parsed.faq_items:
            continue
        
        parsed.atomic_constraints.append(AtomicConstraint(
            id=f"{parsed.meta.instruction_id}_C{offset + idx:02d}",
            name=f"[META] {tpl['name_suffix']}"[:60],
            scoring_dimension=tpl["scoring_dimension"],
            verifier=tpl["verifier"],
            is_critical=tpl["is_critical"],
            weight=tpl["weight"],
            source_text=source_text[:200],
        ))

LLM_PROMPT_TEMPLATE = """你是一个对话指令分析专家。任务: 给一条约束打标签。

约束原文:
{constraint_text}

请输出严格的 JSON,包含以下字段:
- name: 约束的简短名称(不超过30字,中文)
- scoring_dimension: 5选1
  * D1_flow_compliance (流程遵循,如Step覆盖)
  * D2_task_completion (任务完成,如核心意图达成)
  * D3_constraint_compliance (约束遵循,如字数/禁用词/承诺禁令)
  * D4_knowledge_accuracy (知识准确性,如FAQ正确)
  * D5_dialogue_quality (对话质量,如自然/礼貌/适时结束)
- verifier: 5选1
  * rule (完全确定性规则,如字数<=N)
  * rule_pattern (关键词/正则匹配,如禁用词)
  * state_tracker (跨turn状态追踪,如Step覆盖)
  * llm_judge (纯LLM主观判定,如语气自然度)
  * llm_extract_then_rule (LLM抽取后规则比对,如越界话术)
- is_critical: true/false(违反是否显著扣分)
- weight: 1-5整数(重要性)

只输出 JSON,不要其他文本。

示例输入: "每次回复控制在 30 字以内"
示例输出: {{"name": "每次回复<=30字", "scoring_dimension": "D3_constraint_compliance", "verifier": "rule", "is_critical": false, "weight": 2}}
"""


def heuristic_classify(constraint_text: str) -> dict:
    """规则兜底: 当 LLM 失败时,用启发式规则给约束打标签
    
    这是 mock 模式和 LLM 调用失败时的 fallback,准确率约 60-70%
    """
    text_lower = constraint_text.lower()
    
    # 默认值
    result = {
        "name": constraint_text[:40] if len(constraint_text) <= 40 else constraint_text[:37] + "...",
        "scoring_dimension": "D3_constraint_compliance",
        "verifier": "llm_judge",
        "is_critical": False,
        "weight": 2,
    }
    
    # 1. 字数限制 → rule + D3
    if re.search(r"\d+\s*字", constraint_text) or "字数" in constraint_text or "长度" in constraint_text:
        result["scoring_dimension"] = "D3_constraint_compliance"
        result["verifier"] = "rule"
        result["weight"] = 3
        return result
    
    # 2. 禁用词 → rule_pattern + D3
    if "好的" in constraint_text or "禁" in constraint_text or "不说" in constraint_text:
        result["scoring_dimension"] = "D3_constraint_compliance"
        result["verifier"] = "rule_pattern"
        result["weight"] = 3
        return result
    
    # 3. 流程 Step → state_tracker + D1
    if re.search(r"step\s*\d+", text_lower) or "覆盖" in constraint_text:
        result["scoring_dimension"] = "D1_flow_compliance"
        result["verifier"] = "state_tracker"
        result["is_critical"] = True
        result["weight"] = 3
        return result
    
    # 4. 承诺禁令 → llm_extract_then_rule + D3
    if "承诺" in constraint_text or "不能向" in constraint_text or "绝不" in constraint_text:
        result["scoring_dimension"] = "D3_constraint_compliance"
        result["verifier"] = "llm_extract_then_rule"
        result["is_critical"] = True
        result["weight"] = 4
        return result
    
    # 5. 越界处理 → llm_extract_then_rule + D3
    if "越界" in constraint_text or "范围外" in constraint_text or "向同事" in constraint_text or "我帮您记录" in constraint_text:
        result["scoring_dimension"] = "D3_constraint_compliance"
        result["verifier"] = "llm_extract_then_rule"
        result["is_critical"] = True
        result["weight"] = 3
        return result
    
    # 6. 挂断 → llm_judge + D5
    if "挂断" in constraint_text or "结束" in constraint_text or "终结" in constraint_text:
        result["scoring_dimension"] = "D5_dialogue_quality"
        result["verifier"] = "llm_judge"
        result["weight"] = 3
        return result
    
    # 7. 口语化/语气 → llm_judge + D5
    if "口语" in constraint_text or "自然" in constraint_text or "语气" in constraint_text:
        result["scoring_dimension"] = "D5_dialogue_quality"
        result["verifier"] = "llm_judge"
        result["weight"] = 2
        return result
    
    # 8. 重复 → llm_judge + D5
    if "重复" in constraint_text or "灵活" in constraint_text:
        result["scoring_dimension"] = "D5_dialogue_quality"
        result["verifier"] = "llm_judge"
        result["weight"] = 2
        return result
    
    # 9. 给商家发言机会 / 打断 / 暂停 → llm_judge + D5
    if "打断" in constraint_text or "发言" in constraint_text or "暂停" in constraint_text:
        result["scoring_dimension"] = "D5_dialogue_quality"
        result["verifier"] = "llm_judge"
        result["weight"] = 2
        return result
    
    # 默认: D3 + llm_judge
    return result


def call_llm_classify(constraint_text: str, model: str = "gpt-4o-mini") -> dict:
    """调用 LLM 给约束打标签
    
    Returns: dict with name/scoring_dimension/verifier/is_critical/weight
    Falls back to heuristic_classify on failure.
    """
    prompt = LLM_PROMPT_TEMPLATE.format(constraint_text=constraint_text)
    
    try:
        if model.startswith("gpt-") or model.startswith("deepseek-"):
            from openai import OpenAI
            if model.startswith("deepseek-"):
                client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"),
                                base_url="https://api.deepseek.com")
            else:
                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
        elif "claude" in model.lower():
            from anthropic import Anthropic
            client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model=model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
        else:
            raise ValueError(f"不支持的模型: {model}")
        
        # 解析 JSON
        # 兼容 ```json ... ``` 包裹
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"```\s*$", "", content)
        data = json.loads(content)
        
        # 校验关键字段
        if data.get("scoring_dimension") not in VALID_DIMENSIONS:
            raise ValueError(f"LLM 返回非法维度: {data.get('scoring_dimension')}")
        if data.get("verifier") not in VALID_VERIFIERS:
            raise ValueError(f"LLM 返回非法 verifier: {data.get('verifier')}")
        
        return data
    
    except Exception as e:
        # 兜底用规则
        print(f"  ⚠️ LLM 调用失败 ({e}), 用启发式规则", file=sys.stderr)
        return heuristic_classify(constraint_text)


# =====================================================================
# 主解析函数
# =====================================================================

def parse_instruction(
    md_text: str,
    instruction_id: str,
    instruction_name: str = "",
    mock: bool = False,
    llm_model: str = "gpt-4o-mini",
) -> ParsedInstruction:
    """解析指令 Markdown,返回 ParsedInstruction"""
    
    # === 第一层: 规则提取 ===
    role = extract_section(md_text, "Role")
    task = extract_section(md_text, "Task")
    variables = extract_variables(md_text)
    constraint_texts = extract_constraints_raw(md_text)
    faq_raw = extract_faq_raw(md_text)
    flow_raw = extract_flow_steps_raw(md_text)
    
    # === 第二层: LLM 给约束打标签 ===
    atomic_constraints = []
    for idx, ctext in enumerate(constraint_texts, 1):
        if mock:
            labels = heuristic_classify(ctext)
        else:
            labels = call_llm_classify(ctext, model=llm_model)
        
        # 容错: LLM 没返回某些字段时,用启发式补齐
        if "scoring_dimension" not in labels or labels["scoring_dimension"] not in VALID_DIMENSIONS:
            labels["scoring_dimension"] = heuristic_classify(ctext)["scoring_dimension"]
        if "verifier" not in labels or labels["verifier"] not in VALID_VERIFIERS:
            labels["verifier"] = heuristic_classify(ctext)["verifier"]
        
        atomic_constraints.append(AtomicConstraint(
            id=f"{instruction_id}_C{idx:02d}",
            name=labels.get("name", ctext[:30])[:60],
            scoring_dimension=labels["scoring_dimension"],
            verifier=labels["verifier"],
            is_critical=bool(labels.get("is_critical", False)),
            weight=int(labels.get("weight", 2)),
            source_text=ctext[:200],
        ))
    
    # === FAQ 项 ===
    faq_items = []
    for idx, (q, a) in enumerate(faq_raw, 1):
        # 提取关键事实(粗略: 数字 + 名词)
        key_facts = re.findall(r"\d+[%元天分钟小时倍]?|\d+", a)
        faq_items.append(FAQItem(
            id=f"{instruction_id}_FAQ{idx:02d}",
            question_intent=q[:100],
            answer_template=a[:200],
            key_facts=key_facts[:5],
        ))
    
    # === Flow Steps ===
    flow_steps = []
    for sid, desc in flow_raw:
        is_branch = "分支" in desc or "若" in desc or "→" in desc
        flow_steps.append(FlowStep(
            step_id=sid,
            label=desc[:40],
            purpose=desc[:200],
            is_branch=is_branch,
        ))
    
    # === 关键设计: 流程 Step 自动转成 atomic_constraints (D1 维度) ===
    # 否则会出现 V1 的 Constraints 段没有 D1 约束的情况
    flow_constraint_offset = len(atomic_constraints)
    for idx, step in enumerate(flow_steps, 1):
        atomic_constraints.append(AtomicConstraint(
            id=f"{instruction_id}_C{flow_constraint_offset + idx:02d}",
            name=f"{step.step_id} {step.label[:40]}"[:60],
            scoring_dimension="D1_flow_compliance",
            verifier="state_tracker",
            is_critical=True,
            weight=3,
            source_text=step.purpose[:200],
        ))
    
    # === 构造完整对象 ===
    parsed = ParsedInstruction(
        meta=InstructionMeta(
            instruction_id=instruction_id,
            instruction_name=instruction_name or instruction_id,
            role=role[:200],
            task=task[:200],
            variables=variables,
        ),
        atomic_constraints=atomic_constraints,
        faq_items=faq_items,
        flow_steps=flow_steps,
    )
    
    # === 注入元约束(项目级标准约束) ===
    add_meta_constraints(parsed)
    
    return parsed


# =====================================================================
# CLI
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="指令解析器")
    parser.add_argument("--input", required=True, help="指令 Markdown 文件路径")
    parser.add_argument("--output", help="输出 JSON 路径(默认同名 .json)")
    parser.add_argument("--mock", action="store_true", help="Mock 模式(不调LLM,用规则兜底)")
    parser.add_argument("--llm_model", default="gpt-4o-mini", help="LLM 模型")
    parser.add_argument("--instruction_id", help="指令ID(默认用文件名)")
    args = parser.parse_args()
    
    md_path = Path(args.input)
    if not md_path.exists():
        print(f"❌ 文件不存在: {args.input}")
        sys.exit(1)
    
    md_text = md_path.read_text(encoding="utf-8")
    instr_id = args.instruction_id or md_path.stem
    
    print(f"解析: {md_path.name}")
    print(f"  模式: {'MOCK(规则)' if args.mock else f'LLM({args.llm_model})'}")
    
    parsed = parse_instruction(
        md_text=md_text,
        instruction_id=instr_id,
        instruction_name=instr_id,
        mock=args.mock,
        llm_model=args.llm_model,
    )
    
    # 校验
    errors = parsed.validate()
    if errors:
        print(f"\n⚠️ 校验发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
    else:
        print(f"\n✓ 校验通过")
    
    # 统计
    print(f"\n统计:")
    print(f"  变量: {len(parsed.meta.variables)} ({parsed.meta.variables})")
    print(f"  约束: {len(parsed.atomic_constraints)} 条")
    print(f"  FAQ: {len(parsed.faq_items)} 条")
    print(f"  Flow steps: {len(parsed.flow_steps)} 个")
    
    # 输出
    out_path = Path(args.output) if args.output else md_path.with_suffix(".parsed.json")
    out_path.write_text(json.dumps(parsed.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n输出: {out_path}")


if __name__ == "__main__":
    main()
