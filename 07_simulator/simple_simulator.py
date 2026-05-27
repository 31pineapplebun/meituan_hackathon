"""
临时模拟器 (Temp Simulator) - Day 3 用

用途:
- 跑出大约 30-50 通对话作为 Gold Set 数据来源
- 不追求完美，能跑、能输出、能stop即可
- W3 会替换为完整的 8 persona 模拟器，但本脚本提供基础框架

架构:
[用户模拟器] ←→ [被测对话模型]
   ↑                ↑
GPT-4 + persona    GPT-4 / Claude / Qwen (用户指定)

输出: JSONL 文件，每行一通对话

⚠️ 注意:
- 本脚本需要 OPENAI_API_KEY 或 ANTHROPIC_API_KEY 环境变量
- 单次跑 30 通对话预估 200-500 万 token, 成本 $5-20 (取决于模型)
- 建议先小批量测试(2-3通),确认行为正常再批量跑

用法:
    python simple_simulator.py --instruction example_1.md \\
                                --persona cooperative \\
                                --tested_model gpt-4o \\
                                --user_model gpt-4o \\
                                --num_dialogues 5 \\
                                --output dialogues.jsonl
"""
import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# =====================================================================
# Persona 定义 (4 个核心)
# Day 3 临时版本，W3 会扩展为 8 persona 完整框架
# =====================================================================

PERSONAS = {
    "cooperative": {
        "name": "配合型",
        "description": "测试 happy path 主流程",
        "system_prompt": """你正在扮演一位接到外呼电话的用户。
你的目标: 配合对方完成对话,正常推进流程。

行为规则:
1. 第一轮: 简短确认身份(如"嗯,是的"或"对,我是")
2. 后续: 跟随对方引导,给出符合常理的回应
3. 偶尔(1/3 概率)问一些范围内的合理问题
4. 整通对话 8-15 轮

输出格式: 纯用户回复文本,不要旁白,不要引号,15-30字之间
""",
        "max_turns": 15
    },
    
    "refuse_persistent": {
        "name": "拒绝型",
        "description": "测试模型在用户坚持拒绝时是否会安慰后挂断",
        "system_prompt": """你正在扮演一位接到外呼电话的用户,你今天身体不舒服/没空,坚决拒绝配合。

行为规则:
1. 第一轮: 简短确认身份
2. 第二轮: 礼貌但明确表示"今天身体不舒服,没法配合"
3. 第三轮: 对方会试图挽留,你回复"我真的不行,改天吧"
4. 第四轮+: 如果对方还在游说,语气变急"你这样我就挂了"
5. 永远不要松口说能配合
6. 不要主动挂断(看模型会不会按指令主动结束)

输出格式: 纯用户回复,15-30字
""",
        "max_turns": 10
    },
    
    "out_of_scope": {
        "name": "越界型",
        "description": "测试模型遇到越界问题时是否用指定话术",
        "system_prompt": """你正在扮演一位接到外呼电话的用户。
你的目标: 故意问与当前任务无关的问题,看对方怎么回应。

行为规则:
1. 第一轮: 配合确认身份
2. 第二轮起: 开始问越界问题,例如:
   - "今天天气真好,你那边怎么样"
   - "你们公司股票最近怎么样啊"
   - "我之前另一个业务的事能问你吗"
   - "你能告诉我XX的联系方式吗"
3. 每轮换一个越界问题
4. 整通 8-12 轮

输出格式: 纯用户回复,模仿真实用户口语
""",
        "max_turns": 12
    },
    
    "interruption": {
        "name": "打断型",
        "description": "测试模型被打断时是否用过渡语回到主线",
        "system_prompt": """你正在扮演接到外呼电话的用户,你性格急躁,经常打断对方。

行为规则:
1. 第一轮: 确认身份
2. 后续轮: 大约 50% 的时间,在对方说话中段强行插入新话题
   - 例如对方在说升级内容,你插嘴问"那这个功能多少钱"
   - 或对方在解释步骤,你插嘴问"这个能跳过吗"
3. 看对方会不会用过渡语(如"您刚才提到...")回到主线
4. 整通 10-15 轮

输出格式: 纯用户回复,语气急促,15-30字
""",
        "max_turns": 15
    }
}


@dataclass
class DialogueTurn:
    turn: int
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = ""


@dataclass
class Dialogue:
    dialogue_id: str
    instruction_name: str
    persona_id: str
    tested_model: str
    user_model: str
    turns: List[DialogueTurn] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    def to_jsonl(self) -> str:
        return json.dumps({
            "dialogue_id": self.dialogue_id,
            "instruction_name": self.instruction_name,
            "persona_id": self.persona_id,
            "tested_model": self.tested_model,
            "user_model": self.user_model,
            "turns": [asdict(t) for t in self.turns],
            "metadata": self.metadata
        }, ensure_ascii=False)


# =====================================================================
# API 调用接口（统一封装）
# =====================================================================

def call_openai(model: str, messages: list, max_tokens: int = 500) -> str:
    """调用 OpenAI 兼容 API（含 GPT-4o, GPT-4o-mini 等）"""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("需要安装 openai: pip install openai")
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()


def call_anthropic(model: str, messages: list, system: str = "", max_tokens: int = 500) -> str:
    """调用 Anthropic API（Claude 系列）"""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("需要安装 anthropic: pip install anthropic")
    
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=model,
        system=system,
        messages=messages,
        max_tokens=max_tokens
    )
    return response.content[0].text.strip()


def dispatch_llm_call(model: str, system: str, user_messages: list) -> str:
    """根据 model 名称分发到不同 API"""
    if model.startswith("gpt-") or model.startswith("o1"):
        msgs = [{"role": "system", "content": system}] + user_messages
        return call_openai(model, msgs)
    elif "claude" in model.lower():
        return call_anthropic(model, user_messages, system=system)
    else:
        raise ValueError(f"未知模型: {model}. 支持 gpt-*, claude-*")


# =====================================================================
# 对话生成主逻辑
# =====================================================================

def load_instruction(path: str) -> str:
    """加载指令 Markdown 文件"""
    return Path(path).read_text(encoding="utf-8")


def run_one_dialogue(
    instruction_text: str,
    instruction_name: str,
    persona_id: str,
    tested_model: str,
    user_model: str,
    dialogue_id: str
) -> Dialogue:
    """跑一通完整对话"""
    
    persona = PERSONAS[persona_id]
    
    # 被测模型的 system prompt = 用户给的指令
    tested_system = instruction_text
    
    # 用户模拟器的 system prompt = persona prompt
    user_system = persona["system_prompt"]
    
    dialogue = Dialogue(
        dialogue_id=dialogue_id,
        instruction_name=instruction_name,
        persona_id=persona_id,
        tested_model=tested_model,
        user_model=user_model,
    )
    
    # 对话历史: 被测模型视角(用户->助手), 用户视角(助手->用户)
    tested_history = []  # [{role: user/assistant, content: ...}]
    user_history = []
    
    max_turns = persona["max_turns"]
    
    for turn_num in range(1, max_turns + 1):
        # === assistant 先说 (第1轮是开场白) ===
        try:
            asst_msg = dispatch_llm_call(
                model=tested_model,
                system=tested_system,
                user_messages=tested_history if tested_history else [
                    {"role": "user", "content": "开始外呼"}
                ]
            )
        except Exception as e:
            dialogue.metadata["error"] = f"被测模型错误 turn {turn_num}: {e}"
            break
        
        dialogue.turns.append(DialogueTurn(
            turn=turn_num * 2 - 1,
            role="assistant",
            content=asst_msg,
            timestamp=datetime.now().isoformat()
        ))
        
        # 加入两个历史
        tested_history.append({"role": "assistant", "content": asst_msg})
        user_history.append({"role": "user", "content": asst_msg})  # 用户视角:对方说的
        
        # 终止检测: 助手主动结束的关键词
        end_keywords = ["再见", "挂断", "稍后再打", "祝您", "祝你", "再联系"]
        if any(kw in asst_msg for kw in end_keywords) and turn_num >= 3:
            dialogue.metadata["end_reason"] = "assistant_initiated"
            break
        
        # === 用户回复 ===
        try:
            user_msg = dispatch_llm_call(
                model=user_model,
                system=user_system,
                user_messages=user_history
            )
        except Exception as e:
            dialogue.metadata["error"] = f"用户模型错误 turn {turn_num}: {e}"
            break
        
        dialogue.turns.append(DialogueTurn(
            turn=turn_num * 2,
            role="user",
            content=user_msg,
            timestamp=datetime.now().isoformat()
        ))
        
        tested_history.append({"role": "user", "content": user_msg})
        user_history.append({"role": "assistant", "content": user_msg})  # 用户视角:自己说的
        
        # 终止检测: 用户主动挂断
        user_end_keywords = ["挂了", "再见", "拜拜"]
        if any(kw in user_msg for kw in user_end_keywords):
            dialogue.metadata["end_reason"] = "user_initiated"
            break
    
    if "end_reason" not in dialogue.metadata:
        dialogue.metadata["end_reason"] = "max_turns_reached"
    
    dialogue.metadata["total_turns"] = len(dialogue.turns)
    return dialogue


# =====================================================================
# 主入口
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="临时对话模拟器")
    parser.add_argument("--instruction", required=True, help="指令 markdown 文件路径")
    parser.add_argument("--persona", required=True, choices=list(PERSONAS.keys()), help="用户 persona")
    parser.add_argument("--tested_model", default="gpt-4o-mini", help="被测对话模型")
    parser.add_argument("--user_model", default="gpt-4o-mini", help="用户模拟器模型")
    parser.add_argument("--num_dialogues", type=int, default=5, help="生成对话数")
    parser.add_argument("--output", default="dialogues.jsonl", help="输出文件")
    parser.add_argument("--dry_run", action="store_true", help="只检查环境，不调用API")
    args = parser.parse_args()
    
    # 加载指令
    instr_path = Path(args.instruction)
    if not instr_path.exists():
        print(f"❌ 指令文件不存在: {args.instruction}")
        sys.exit(1)
    instruction_text = load_instruction(args.instruction)
    instruction_name = Path(args.instruction).stem
    
    print(f"配置:")
    print(f"  指令: {instruction_name}")
    print(f"  Persona: {args.persona} ({PERSONAS[args.persona]['name']})")
    print(f"  被测模型: {args.tested_model}")
    print(f"  用户模型: {args.user_model}")
    print(f"  对话数: {args.num_dialogues}")
    print(f"  输出: {args.output}")
    
    if args.dry_run:
        print("\n[Dry run] 跳过 API 调用")
        # 检查 API key
        if "gpt" in args.tested_model.lower() and not os.getenv("OPENAI_API_KEY"):
            print("⚠️ OPENAI_API_KEY 未设置")
        if "claude" in args.tested_model.lower() and not os.getenv("ANTHROPIC_API_KEY"):
            print("⚠️ ANTHROPIC_API_KEY 未设置")
        return
    
    # 跑对话
    output_path = Path(args.output)
    with open(output_path, "a", encoding="utf-8") as fout:
        for i in range(args.num_dialogues):
            dlg_id = f"{instruction_name}_{args.persona}_{int(time.time())}_{i:03d}"
            print(f"\n[{i+1}/{args.num_dialogues}] 生成 {dlg_id}...")
            
            try:
                dialogue = run_one_dialogue(
                    instruction_text=instruction_text,
                    instruction_name=instruction_name,
                    persona_id=args.persona,
                    tested_model=args.tested_model,
                    user_model=args.user_model,
                    dialogue_id=dlg_id
                )
                fout.write(dialogue.to_jsonl() + "\n")
                fout.flush()
                
                print(f"  ✓ 完成 {dialogue.metadata.get('total_turns', 0)} 轮, "
                      f"原因: {dialogue.metadata.get('end_reason', 'unknown')}")
                
                # 防止 API 限流
                time.sleep(1)
                
            except Exception as e:
                print(f"  ✗ 失败: {e}")
                continue
    
    print(f"\n完成，输出到 {output_path}")


if __name__ == "__main__":
    main()
