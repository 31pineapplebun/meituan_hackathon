import { Link } from 'react-router-dom'
import styles from './AboutPage.module.css'

const RELIABILITY = [
  ['客观约束 kappa', '1.0000', '完美对齐人工'],
  ['D3 约束遵循 kappa', '0.84', '顶级一致'],
  ['整体 vs 人工 kappa', '0.4483', '业界标准区间'],
  ['三路 LLM 互查 kappa', '0.81', '跨模型对照'],
]

const ENGINEERING = [
  ['自动重试', 'LLM 调用失败自动重试 3 次(指数退避)', 'API 抖动不再污染评分'],
  ['可复现', '固定 seed + temperature=0 + 记录模型版本', '今天评和明天评结果一致'],
  ['结果缓存', '(对话+约束+模型) 哈希缓存', '重复评测秒出、省 API 费用'],
  ['并发评测', '多约束并发判定(线程池)', '单通从 ~30 秒降到 ~5 秒'],
  ['自一致性投票', '关键约束判 3 次取多数票', '抹平单次 LLM 判定抖动'],
  ['鲁棒解析', '容错 markdown 围栏/转义/截断的 JSON', '输出格式异常不致评测失败'],
  ['语义容错', '流程识别支持同义词(告知≈通知)', '减少用词不同的误判'],
  ['空对话保护', '区分「无法评测」与「真实低分」', '不给误导性 0 分'],
]

export default function AboutPage() {
  return (
    <div className={styles.page}>
      <div>
        <h2 className={styles.title}>关于本系统</h2>
        <p className={styles.sub}>技术原理 · 评测可靠性 · 数据来源</p>
      </div>

      <section className={styles.card}>
        <h3>💡 系统定位</h3>
        <p>
          <b>美团对话外呼任务评测系统</b> —— 针对 AI 数字人外呼场景的指令遵循能力自动评测。
        </p>
        <p>
          输入一个任务指令 + 一个待测模型,系统自动模拟多种用户场景与模型对话,评测模型的指令遵循程度,
          产出 <b>0–100 分 + 可解释报告 + 优化方向</b>。
        </p>
      </section>

      <section className={styles.card}>
        <h3>🏗️ 技术架构</h3>
        <pre className={styles.arch}>{`[任务指令 .md] → [Parser 解析] → [约束清单 16-36 条, 5 类 verifier]
                                        ↓
[待测模型 M] → [用户模拟器 8 persona] → 多通对话
                                        ↓
                              [5 类 Verifier 分层判定]
                                        ↓
                              [P3 三层评分 → 0-100 分]
                                        ↓
                       [模型级聚合 → 能力画像 + 优化方向]`}</pre>
        <div className={styles.grid2}>
          <div className={styles.subcard}>
            <h4>5 类 Verifier(按成本分层)</h4>
            <ul>
              <li><code>rule</code> 字数/占位符 — 0 次 LLM</li>
              <li><code>rule_pattern</code> 禁用词 — 0 次 LLM</li>
              <li><code>state_tracker</code> 流程步骤 — 关键词优先 + LLM 兜底</li>
              <li><code>llm_extract_then_rule</code> 事实抽取 — 1 次</li>
              <li><code>llm_judge</code> 主观判断 — 1 次</li>
            </ul>
            <p className={styles.em}>客观约束用规则零成本判定(更准更稳),LLM 预算集中花在主观约束上。</p>
          </div>
          <div className={styles.subcard}>
            <h4>P3 三层评分防御</h4>
            <ul>
              <li>L1 加权分:D1(25%)+D2(25%)+D3(20%)+D4(15%)+D5(15%)</li>
              <li>L2 Critical 钳制:关键约束通过率 &lt;90% → 上限 85</li>
              <li>L3 红线钳制:任何红线违规 → 上限 40</li>
            </ul>
            <p className={styles.em}>防止「D3 满分但 D1 全 fail」的虚高分。</p>
          </div>
        </div>
      </section>

      <section className={styles.card}>
        <h3>📊 评测可靠性(50 通真实对话 × 1055 条约束)</h3>
        <div className={styles.metrics}>
          {RELIABILITY.map(([label, value, delta]) => (
            <div className={styles.metric} key={label}>
              <div className={styles.mLabel}>{label}</div>
              <div className={styles.mValue}>{value}</div>
              <div className={styles.mDelta}>{delta}</div>
            </div>
          ))}
        </div>
        <p className={styles.note}>
          <b>如何理解 kappa = 0.45</b>:按 LLM-as-Judge 学术标准,模型与人工 kappa 在 <b>0.3–0.6</b>{' '}
          是行业常态(超过 0.7 反而要警惕数据泄露)。我们整体 0.45 落在合理区间偏上,且
          <b>客观约束达到完美的 1.0</b>。
        </p>
      </section>

      <section className={styles.card}>
        <h3>🛡️ 工程可靠性(生产级保障)</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>能力</th>
              <th>实现</th>
              <th>解决什么</th>
            </tr>
          </thead>
          <tbody>
            {ENGINEERING.map(([cap, impl, why]) => (
              <tr key={cap}>
                <td><b>{cap}</b></td>
                <td>{impl}</td>
                <td>{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className={styles.card}>
        <h3>🔄 4 轮标注迭代 — 评测系统反过来发现人类盲区</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>版本</th>
              <th>阶段</th>
              <th>操作</th>
              <th>与人工 kappa</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>v3</td><td>Day 5</td><td>初标</td><td>0.72 ⚠️ 虚高(两人犯同样错误)</td></tr>
            <tr><td>v4</td><td>Day 9</td><td>LLM 评测<b>独立发现</b> 5 条标注瑕疵 → 自动修订 73 处</td><td>—</td></tr>
            <tr><td>v5</td><td>Day 9 末</td><td>手工复核 12 处</td><td>—</td></tr>
            <tr><td>v6</td><td>Day 10</td><td>全量重标 1055 条</td><td><b>0.45(真实可靠)</b></td></tr>
          </tbody>
        </table>
        <p className={styles.note}>
          <b>关键发现</b>:LLM 评测在 v4 阶段独立发现了人工标注的系统性错误,抽样 5/5 case{' '}
          <b>机器对、人错</b>。系统不只是模仿人,<b>还能纠正人</b> —— 这正是可解释、可量化评测的价值。
        </p>
      </section>

      <section className={styles.card}>
        <h3>🎭 8 种用户场景(Persona)</h3>
        <div className={styles.grid2}>
          <div className={styles.subcard}>
            <h4>核心 4 种</h4>
            <ul>
              <li>🤝 合作型 — happy path 主流程</li>
              <li>😤 坚持拒绝型 — 能否礼貌挂断</li>
              <li>🌀 越界提问型 — 能否守住边界</li>
              <li>✋ 打断型 — 能否优雅恢复</li>
            </ul>
          </div>
          <div className={styles.subcard}>
            <h4>扩展 4 种</h4>
            <ul>
              <li>🚗 状态型(忙/开车) — 识别状态 + 规定话术</li>
              <li>🤔 模糊型 — 能否推动含糊对话</li>
              <li>⚔️ 对抗型 — 挑刺/诱导承诺时守边界</li>
              <li>❓ 提问型 — FAQ 知识覆盖度</li>
            </ul>
          </div>
        </div>
      </section>

      <section className={styles.card}>
        <h3>⚙️ 数据来源</h3>
        <ul>
          <li><b>真实评测数据</b>:Day 9 用 deepseek-v4-flash 跑出的 1055 条 verdict(pass 率约 58%)</li>
          <li><b>三路对照</b>:DeepSeek-Flash / DeepSeek-Pro / GPT-5-mini 跨模型族验证</li>
          <li><b>快速演示模式</b>:读取上述真实评测结果聚合(非 mock,非手工编造)</li>
          <li><b>完整运行模式</b>:实时调用待测模型真跑(需配置 API key)</li>
        </ul>
      </section>

      <Link className={styles.back} to="/config">
        ← 回到配置
      </Link>
    </div>
  )
}
