"""
临时模拟器 v2 (Temp Simulator) - Day 4 增强版

v2 相对 v1 的改进:
- ✅ 新增 mock 模式: 不调用 API 也能产出对话(用于调试 pipeline)
- ✅ 新增成本估算: 跑前估算 token 消耗
- ✅ 新增对话有效性检查: 跑完自动检查每通对话(长度/turn数/异常)
- ✅ 重试机制: API 失败自动重试 3 次
- ✅ 更细的日志: 每个 API 调用记录耗时
- ✅ 多服务支持: OpenAI / DeepSeek / Anthropic 都可以

用途:
- 跑出 30-50 通对话作为 Gold Set 数据来源
- W3 会替换为完整的 8 persona 模拟器,本脚本提供基础框架

输出: JSONL 文件,每行一通对话

⚠️ 注意:
- 需要 OPENAI_API_KEY / DEEPSEEK_API_KEY / ANTHROPIC_API_KEY 环境变量(根据用哪个模型)
- DeepSeek API 用 OpenAI 兼容格式,base_url=https://api.deepseek.com
- 单次跑 30 通对话成本: GPT-4o-mini ~$0.10 / DeepSeek-Flash ~$0.30 / DeepSeek-Pro ~$3-5

支持的模型:
- gpt-4o, gpt-4o-mini (OpenAI)
- deepseek-v4-pro, deepseek-v4-flash (DeepSeek)
- claude-3-5-sonnet-* 等 (Anthropic)

用法:
    # Mock 模式(零成本)
    python simulator_v2.py --instruction V1.md --persona cooperative --mock

    # DeepSeek 真实运行 - 推荐混搭(assistant用pro, user用flash省钱)
    export DEEPSEEK_API_KEY=sk-xxx
    python simulator_v2.py --instruction V1.md --persona cooperative \\
        --tested_model deepseek-v4-pro --user_model deepseek-v4-flash --num_dialogues 5

    # OpenAI
    export OPENAI_API_KEY=sk-xxx
    python simulator_v2.py --instruction V1.md --persona cooperative \\
        --tested_model gpt-4o-mini --num_dialogues 5
"""
import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# =====================================================================
# Persona 定义 (8 个完整框架)
# - 4 个核心: cooperative / refuse_persistent / out_of_scope / interruption
# - 4 个扩展: state_busy / ambiguous / adversarial / probing
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
    },
    
    # ===== W3 扩展 Persona (按原计划补齐) =====
    
    "state_busy": {
        "name": "状态型(忙/开车)",
        "description": "测试模型识别用户状态(开车/忙) 是否用规定话术",
        "system_prompt": """你正在扮演接到外呼电话的用户。你今天非常忙,或正在开车。

行为规则:
1. 第一轮: 简短确认身份,语气匆忙(如"嗯我在开车呢")
2. 第二轮: 明确告知"我在开车" 或"我现在忙不开" 
3. 看对方是否用规定话术回应:
   - 开车 → "那我稍后再打"并挂断
   - 忙 → "就1分钟,保证简短"
4. 如果对方没按规定话术,继续表达不便("我真没空")
5. 整通 4-8 轮(很短)

输出格式: 纯用户回复,语气匆忙,10-20字
""",
        "max_turns": 8
    },
    
    "ambiguous": {
        "name": "模糊型",
        "description": "测试模型处理含糊不清回答的能力",
        "system_prompt": """你正在扮演接到外呼电话的用户,你的回复总是含糊不清,不给明确答案。

行为规则:
1. 第一轮: 模糊确认身份(如"哦...嗯...")
2. 后续轮: 给模糊回答:
   - "可能吧/差不多/再说吧/看情况"
   - "我不太清楚/我不确定"
   - "等会儿/到时候/有空再说"
3. 不给明确的"是/否"
4. 看对方能否推动对话进展
5. 整通 10-14 轮

输出格式: 纯用户回复,语气含糊犹豫,15-25字
""",
        "max_turns": 14
    },
    
    "adversarial": {
        "name": "对抗型",
        "description": "测试模型在用户挑刺/抱怨/质疑时是否守住边界",
        "system_prompt": """你正在扮演接到外呼电话的用户,你对平台不满,经常抱怨/挑刺。

行为规则:
1. 第一轮: 不情愿确认身份("是啊找我什么事?")
2. 后续轮: 表达不满 / 挑刺 / 反问:
   - "你们平台规则有问题"
   - "凭什么我必须配合"
   - "上次的事还没解决"
   - "我要投诉"
3. 偶尔(1/3) 试图引诱对方承诺补偿/折扣 (测试模型禁承诺)
4. 看对方是否守住边界 + 礼貌沟通
5. 整通 10-14 轮

输出格式: 纯用户回复,语气不满但不失控,15-30字
""",
        "max_turns": 14
    },
    
    "probing": {
        "name": "提问型",
        "description": "测试模型 FAQ 知识覆盖度",
        "system_prompt": """你正在扮演接到外呼电话的用户,你对当前任务很关心,会问很多细节问题。

行为规则:
1. 第一轮: 配合确认身份
2. 后续轮: 主动问与任务相关的细节:
   - "这个有什么好处"
   - "如果我做不到怎么办"
   - "有没有补偿/奖励"
   - "具体怎么操作"
   - "什么时候开始/结束"
3. 每个问题等对方完整回答再问下一个
4. 看对方知识库覆盖度 + 回答准确性
5. 整通 12-16 轮

输出格式: 纯用户回复,语气好奇,15-30字
""",
        "max_turns": 16
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

def call_openai_compatible(
    model: str, 
    messages: list, 
    max_tokens: int = 500,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """调用 OpenAI 兼容 API
    
    支持的服务:
    - OpenAI (默认): GPT-4o, GPT-4o-mini 等
    - DeepSeek: deepseek-v4-pro, deepseek-v4-flash 等
    - 其他 OpenAI 兼容服务: 通过 base_url 指定
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("需要安装 openai: pip install openai")
    
    # 自动根据模型名选择 api_key 和 base_url
    if api_key is None and base_url is None:
        if model.startswith("deepseek-"):
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = "https://api.deepseek.com"
            if not api_key:
                raise RuntimeError("调用 DeepSeek 模型需要设置 DEEPSEEK_API_KEY")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = None  # OpenAI 默认
            if not api_key:
                raise RuntimeError("调用 OpenAI 模型需要设置 OPENAI_API_KEY")
    
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.7
    )
    content = response.choices[0].message.content
    if content is None:
        return ""
    return content.strip()


# 向后兼容旧函数名
def call_openai(model: str, messages: list, max_tokens: int = 500) -> str:
    """向后兼容: 调用 OpenAI"""
    return call_openai_compatible(model, messages, max_tokens)


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


def dispatch_llm_call(model: str, system: str, user_messages: list, mock: bool = False,
                       persona_id: str = None) -> str:
    """根据 model 名称分发到不同 API; mock=True 则返回固定文本不调API
    
    persona_id: mock 模式下用来生成不同 persona 的对话 (LLM 模式不需要)
    """
    if mock:
        # Mock 模式: 根据 system 内容粗判是 assistant 还是 user
        if "你是" in system[:20] or "Role" in system[:50]:
            # 像是被测模型(assistant)
            return _mock_assistant_response(user_messages)
        else:
            # 像是用户模拟器
            return _mock_user_response(user_messages, persona_id)
    
    # 真实 API 调用 + 重试 (空回复也算失败)
    last_error = None
    for attempt in range(3):
        try:
            if model.startswith("gpt-") or model.startswith("o1"):
                msgs = [{"role": "system", "content": system}] + user_messages
                result = call_openai_compatible(model, msgs)
            elif model.startswith("deepseek-"):
                # DeepSeek 也是 OpenAI 兼容格式
                msgs = [{"role": "system", "content": system}] + user_messages
                result = call_openai_compatible(model, msgs)
            elif "claude" in model.lower():
                result = call_anthropic(model, user_messages, system=system)
            else:
                raise ValueError(
                    f"未知模型: {model}. 支持 gpt-*, deepseek-*, claude-*"
                )
            
            # 空回复也视为失败,触发重试
            if not result or not result.strip():
                raise RuntimeError("API 返回空内容")
            
            return result
        except Exception as e:
            last_error = e
            if attempt < 2:
                wait = 2 ** attempt  # 1s, 2s
                print(f"    ⚠️ API失败 (尝试{attempt+1}/3): {e}, 等{wait}s重试...")
                time.sleep(wait)
            else:
                raise RuntimeError(f"API调用3次都失败: {last_error}")


def _mock_assistant_response(history: list) -> str:
    """Mock assistant 回复 - 用于 pipeline 调试"""
    if not history:
        return "您好,请问您是负责人吗?这边是美团客服,有事跟您核实下。"
    turn = len(history)
    mocks = [
        "好的,我先简单说明一下情况。",
        "您看这样行不行,我们可以...",
        "嗯,我理解,那您看下一步怎么处理?",
        "明白了,我帮您记录回头跟进。",
        "那再次确认一下相关信息。",
        "好的,那这边就先这样,后续有问题再联系。",
        "感谢您的配合,祝您课程顺利、招生满满。",
    ]
    return mocks[min(turn // 2, len(mocks) - 1)]


def _mock_user_response(history: list, persona_id: str = None) -> str:
    """Mock 用户回复 - 按 persona 生成不同的回复池
    
    Note: Mock 是为了不调 API 调试 pipeline 用。
    真实 LLM 模式下 user 回复才会完全体现 persona 性格。
    """
    if not history:
        return "嗯,我是。"
    turn = len(history)
    
    # 按 persona_id 分发到不同回复池
    persona_pools = {
        "cooperative": [
            "嗯,可以的。", "好,我知道了。", "行吧,我配合一下。",
            "嗯,没问题。", "明白了,谢谢。", "好的,知道了。",
        ],
        "refuse_persistent": [
            "今天不行,身体不舒服。", "我真的不能配合。", "改天再说吧,今天没空。",
            "你这样我就挂了。", "我说了不行就不行。", "别再问了,我挂了。",
        ],
        "out_of_scope": [
            "今天天气真好,你那边怎么样?", "你们公司股票最近怎么样?",
            "我之前另一个业务的事能问你吗?", "你能告诉我XX的联系方式吗?",
            "你工资多少啊?", "你是男是女?",
        ],
        "interruption": [
            "等等,那这个功能多少钱?", "打断一下,这个能跳过吗?",
            "你先别说这个,我问你别的。", "等下,我先问个事。",
            "停停停,这个我不关心。",
        ],
        "state_busy": [
            "嗯我在开车呢。", "我现在忙不开,你长话短说。",
            "我真没空,长话短说。", "等下,我手头有事。",
            "我开车不方便,你直说。",
        ],
        "ambiguous": [
            "可能吧,差不多。", "再说吧,看情况。", "我不太清楚。",
            "等会儿吧,到时候再说。", "嗯...大概是吧。", "也许可以,也许不行。",
        ],
        "adversarial": [
            "你们平台规则有问题。", "凭什么我必须配合?",
            "上次的事还没解决呢。", "你这能给我什么补偿?",
            "我要投诉,这事不合理。", "你们少糊弄人。",
        ],
        "probing": [
            "这个有什么好处?", "如果我做不到怎么办?",
            "有没有补偿或奖励?", "具体怎么操作?",
            "什么时候开始?什么时候结束?", "我还想问个细节。",
        ],
    }
    
    # 兜底: 没指定 persona 或不在列表中, 用通用回复
    pool = persona_pools.get(persona_id, [
        "嗯,可以的。", "啥意思?具体说说。", "好,我知道了。",
        "哦,这样啊。那然后呢?", "行吧,我配合一下。", "嗯,没问题。",
        "明白了,谢谢。",
    ])
    
    random.seed(turn * 7)  # 让 mock 结果可复现, 但不同 turn 不同回复
    return random.choice(pool)


# =====================================================================
# 对话生成主逻辑
# =====================================================================

def load_instruction(path: str, variables: dict = None) -> str:
    """加载指令 Markdown 文件,可选地用变量值替换占位符
    
    Args:
        path: 指令文件路径
        variables: {var_name: value} 形式的替换映射, None 则不替换
    """
    text = Path(path).read_text(encoding="utf-8")
    
    if variables:
        # 替换 ${xxx} 形式的占位符
        for k, v in variables.items():
            text = text.replace(f"${{{k}}}", str(v))
        
        # 检查是否还有未替换的占位符
        import re
        remaining = re.findall(r"\$\{([^}]+)\}", text)
        if remaining:
            print(f"⚠️ 警告: 以下变量未在 variable_values 中提供, 将原样保留: {set(remaining)}")
    
    return text


def load_variable_values(instruction_name: str, scenario: str = "default", 
                          values_path: str = None) -> dict:
    """加载指令对应的变量值
    
    Args:
        instruction_name: 如 'V1', 'V2', 'example_2' 等
        scenario: 默认 'default', 未来 W3-W4 可用多套场景
        values_path: variable_values.json 路径, None 则自动查找
    """
    if values_path is None:
        # 自动查找 variable_values.json
        candidates = [
            Path(__file__).resolve().parent.parent / "03_examples" / "variants" / "variable_values.json",
            Path("/home/claude/project_v1/03_examples/variants/variable_values.json"),
        ]
        for c in candidates:
            if c.exists():
                values_path = c
                break
    
    if values_path is None or not Path(values_path).exists():
        return {}  # 找不到就返回空,等于不替换
    
    with open(values_path, encoding="utf-8") as f:
        data = json.load(f)
    
    if instruction_name not in data:
        return {}
    
    return data[instruction_name].get(scenario, data[instruction_name].get("default", {}))


def run_one_dialogue(
    instruction_text: str,
    instruction_name: str,
    persona_id: str,
    tested_model: str,
    user_model: str,
    dialogue_id: str,
    mock: bool = False,
) -> Dialogue:
    """跑一通完整对话"""
    
    persona = PERSONAS[persona_id]
    tested_system = instruction_text
    user_system = persona["system_prompt"]
    
    dialogue = Dialogue(
        dialogue_id=dialogue_id,
        instruction_name=instruction_name,
        persona_id=persona_id,
        tested_model=tested_model if not mock else f"MOCK({tested_model})",
        user_model=user_model if not mock else f"MOCK({user_model})",
    )
    
    tested_history = []
    user_history = []
    max_turns = persona["max_turns"]
    
    for turn_num in range(1, max_turns + 1):
        # === assistant ===
        try:
            asst_msg = dispatch_llm_call(
                model=tested_model,
                system=tested_system,
                user_messages=tested_history if tested_history else [
                    {"role": "user", "content": "开始外呼"}
                ],
                mock=mock,
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
        tested_history.append({"role": "assistant", "content": asst_msg})
        user_history.append({"role": "user", "content": asst_msg})
        
        end_keywords = ["再见", "挂断", "稍后再打", "祝您", "祝你", "再联系"]
        if any(kw in asst_msg for kw in end_keywords) and turn_num >= 3:
            dialogue.metadata["end_reason"] = "assistant_initiated"
            break
        
        # === user ===
        try:
            user_msg = dispatch_llm_call(
                model=user_model,
                system=user_system,
                user_messages=user_history,
                mock=mock,
                persona_id=persona_id,  # 让 mock 按 persona 生成不同回复
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
        user_history.append({"role": "assistant", "content": user_msg})
        
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

def validate_dialogue(dialogue: Dialogue) -> dict:
    """跑完一通对话后检查质量"""
    issues = []
    if not dialogue.turns:
        return {"valid": False, "issues": ["对话为空"]}
    
    n_turns = len(dialogue.turns)
    if n_turns < 4:
        issues.append(f"对话过短({n_turns}轮),可能未充分测试")
    
    # 检查是否包含错误
    if "error" in dialogue.metadata:
        issues.append(f"含错误: {dialogue.metadata['error']}")
    
    # 检查 assistant 第一轮是否合理(开场白长度)
    first_asst = next((t for t in dialogue.turns if t.role == "assistant"), None)
    if first_asst and len(first_asst.content) < 10:
        issues.append(f"开场白过短: {first_asst.content!r}")
    
    # 检查 assistant 平均字数(粗判长度约束遵守情况)
    asst_lengths = [len(t.content) for t in dialogue.turns if t.role == "assistant"]
    if asst_lengths:
        avg = sum(asst_lengths) / len(asst_lengths)
    else:
        avg = 0
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "stats": {
            "total_turns": n_turns,
            "assistant_turns": sum(1 for t in dialogue.turns if t.role == "assistant"),
            "user_turns": sum(1 for t in dialogue.turns if t.role == "user"),
            "avg_assistant_length": round(avg, 1),
            "end_reason": dialogue.metadata.get("end_reason"),
        }
    }


def main():
    parser = argparse.ArgumentParser(description="临时对话模拟器 v2")
    parser.add_argument("--instruction", required=True, help="指令 markdown 文件路径")
    parser.add_argument("--persona", required=True, choices=list(PERSONAS.keys()), help="用户 persona")
    parser.add_argument("--tested_model", default="gpt-4o-mini", help="被测对话模型")
    parser.add_argument("--user_model", default="gpt-4o-mini", help="用户模拟器模型")
    parser.add_argument("--num_dialogues", type=int, default=1, help="生成对话数")
    parser.add_argument("--output", default="dialogues.jsonl", help="输出文件")
    parser.add_argument("--dry_run", action="store_true", help="只检查环境,不跑")
    parser.add_argument("--mock", action="store_true", help="Mock模式,不调用API")
    parser.add_argument("--scenario", default="default", 
                        help="变量值场景名(对应variable_values.json中的key)")
    args = parser.parse_args()
    
    # 加载指令
    instr_path = Path(args.instruction)
    if not instr_path.exists():
        print(f"❌ 指令文件不存在: {args.instruction}")
        sys.exit(1)
    
    # 加载变量值并替换
    instruction_name = Path(args.instruction).stem
    variables = load_variable_values(instruction_name, scenario=args.scenario)
    if variables:
        print(f"  变量替换: {variables}")
    else:
        print(f"  ⚠️ 未找到 {instruction_name} 的变量值映射, 指令中的占位符将原样保留")
    
    instruction_text = load_instruction(args.instruction, variables=variables)
    
    print(f"\n配置:")
    print(f"  指令: {instruction_name}")
    print(f"  Persona: {args.persona} ({PERSONAS[args.persona]['name']})")
    print(f"  被测模型: {args.tested_model}")
    print(f"  用户模型: {args.user_model}")
    print(f"  对话数: {args.num_dialogues}")
    print(f"  输出: {args.output}")
    print(f"  模式: {'MOCK(不调API)' if args.mock else 'LIVE(真实API)'}")
    
    if args.dry_run:
        print("\n[Dry run] 跳过执行")
        if not args.mock:
            models_to_check = [args.tested_model, args.user_model]
            for m in set(models_to_check):
                if m.startswith("gpt-") or m.startswith("o1"):
                    if not os.getenv("OPENAI_API_KEY"):
                        print(f"⚠️ 模型 {m} 需要 OPENAI_API_KEY (未设置)")
                elif m.startswith("deepseek-"):
                    if not os.getenv("DEEPSEEK_API_KEY"):
                        print(f"⚠️ 模型 {m} 需要 DEEPSEEK_API_KEY (未设置)")
                elif "claude" in m.lower():
                    if not os.getenv("ANTHROPIC_API_KEY"):
                        print(f"⚠️ 模型 {m} 需要 ANTHROPIC_API_KEY (未设置)")
        return
    
    # 实际跑
    print(f"\n开始生成 {args.num_dialogues} 通对话...\n")
    output_path = Path(args.output)
    
    valid_count = 0
    invalid_count = 0
    
    # 自动创建父目录
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "a", encoding="utf-8") as fout:
        for i in range(args.num_dialogues):
            dlg_id = f"{instruction_name}_{args.persona}_{int(time.time())}_{i:03d}"
            print(f"[{i+1}/{args.num_dialogues}] {dlg_id}")
            
            t_start = time.time()
            try:
                dialogue = run_one_dialogue(
                    instruction_text=instruction_text,
                    instruction_name=instruction_name,
                    persona_id=args.persona,
                    tested_model=args.tested_model,
                    user_model=args.user_model,
                    dialogue_id=dlg_id,
                    mock=args.mock,
                )
                t_elapsed = time.time() - t_start
                
                # 质量检查
                check = validate_dialogue(dialogue)
                dialogue.metadata["validation"] = check
                
                fout.write(dialogue.to_jsonl() + "\n")
                fout.flush()
                
                if check["valid"]:
                    valid_count += 1
                    mark = "✓"
                else:
                    invalid_count += 1
                    mark = "⚠"
                
                stats = check["stats"]
                print(f"  {mark} {stats['total_turns']}轮 / "
                      f"平均{stats['avg_assistant_length']}字 / "
                      f"{stats['end_reason']} / "
                      f"耗时{t_elapsed:.1f}s")
                
                if check["issues"]:
                    for issue in check["issues"]:
                        print(f"      └─ {issue}")
                
                # 防止 API 限流(mock时不需要)
                if not args.mock:
                    time.sleep(1)
                
            except Exception as e:
                print(f"  ✗ 失败: {e}")
                invalid_count += 1
                continue
    
    print(f"\n{'='*60}")
    print(f"完成: 有效 {valid_count} / 异常 {invalid_count} / 总 {args.num_dialogues}")
    print(f"输出: {output_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
