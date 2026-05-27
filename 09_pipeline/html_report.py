"""
HTML 评分报告生成器 (B3)

把 pipeline 输出的 JSON 报告渲染成精美 HTML, 适合:
- 答辩 PPT 截图
- 给评委直接看
- Streamlit UI 嵌入

设计原则:
1. 单文件 HTML (内联 CSS + 自带 SVG, 不需要任何外部依赖)
2. 卡片式布局 + 配色清晰
3. 信息密度高: 一屏看到所有关键信息
"""
import json
import math
from pathlib import Path
from typing import Optional


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>评分报告 - {dialogue_id}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    min-height: 100vh;
    padding: 30px 20px;
    color: #2d3748;
}}
.container {{
    max-width: 1200px;
    margin: 0 auto;
    background: white;
    border-radius: 16px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.1);
    overflow: hidden;
}}
.header {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 30px 40px;
}}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header .subtitle {{ font-size: 14px; opacity: 0.85; }}
.header .meta {{
    display: flex;
    gap: 30px;
    margin-top: 18px;
    font-size: 13px;
    opacity: 0.9;
}}
.score-section {{
    padding: 40px;
    text-align: center;
    background: linear-gradient(180deg, white 0%, #f8fafc 100%);
}}
.score-big {{
    display: inline-block;
    position: relative;
}}
.score-big .number {{
    font-size: 96px;
    font-weight: 900;
    background: linear-gradient(135deg, {score_color1} 0%, {score_color2} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
}}
.score-big .max {{
    font-size: 32px;
    color: #94a3b8;
    margin-left: 8px;
}}
.score-grade {{
    display: inline-block;
    padding: 6px 24px;
    background: {score_color1};
    color: white;
    border-radius: 24px;
    font-size: 16px;
    font-weight: 600;
    margin-top: 12px;
}}
.score-meta {{
    display: flex;
    justify-content: center;
    gap: 40px;
    margin-top: 24px;
    font-size: 13px;
    color: #64748b;
}}
.score-meta .item strong {{ color: #2d3748; }}
.dim-section {{
    padding: 30px 40px;
    border-top: 1px solid #e2e8f0;
}}
.section-title {{
    font-size: 20px;
    margin-bottom: 20px;
    color: #1a202c;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.dim-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 30px;
    align-items: center;
}}
.radar-container {{ text-align: center; }}
.dim-list {{ display: flex; flex-direction: column; gap: 12px; }}
.dim-card {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 18px;
    background: #f8fafc;
    border-left: 4px solid #cbd5e0;
    border-radius: 8px;
}}
.dim-card.good {{ border-left-color: #4ade80; }}
.dim-card.ok {{ border-left-color: #fbbf24; }}
.dim-card.bad {{ border-left-color: #f87171; }}
.dim-card .name {{ flex: 1; font-weight: 600; }}
.dim-card .score {{ font-size: 22px; font-weight: 700; }}
.dim-card.good .score {{ color: #16a34a; }}
.dim-card.ok .score {{ color: #d97706; }}
.dim-card.bad .score {{ color: #dc2626; }}
.dim-card .weight {{ font-size: 11px; color: #94a3b8; }}
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 30px;
}}
.stat-card {{
    padding: 20px;
    text-align: center;
    background: #f8fafc;
    border-radius: 12px;
}}
.stat-card .label {{ font-size: 13px; color: #64748b; margin-bottom: 8px; }}
.stat-card .value {{ font-size: 32px; font-weight: 700; }}
.stat-card.pass .value {{ color: #16a34a; }}
.stat-card.fail .value {{ color: #dc2626; }}
.stat-card.na .value {{ color: #64748b; }}
.stat-card.skip .value {{ color: #d97706; }}
.suggestion-section {{
    padding: 30px 40px;
    border-top: 1px solid #e2e8f0;
    background: #fef3c7;
}}
.suggestion {{
    background: white;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 16px;
    border-left: 5px solid #f59e0b;
}}
.suggestion.p0 {{ border-left-color: #dc2626; background: #fef2f2; }}
.suggestion.p1 {{ border-left-color: #ea580c; }}
.suggestion.p2 {{ border-left-color: #f59e0b; }}
.suggestion.p3 {{ border-left-color: #84cc16; }}
.suggestion .head {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}}
.suggestion .priority-badge {{
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    background: #fee2e2;
    color: #991b1b;
}}
.suggestion .priority-badge.p1 {{ background: #fed7aa; color: #9a3412; }}
.suggestion .priority-badge.p2 {{ background: #fef3c7; color: #92400e; }}
.suggestion .priority-badge.p3 {{ background: #d9f99d; color: #3f6212; }}
.suggestion .cid {{ font-family: monospace; color: #64748b; }}
.suggestion .problem {{ font-size: 15px; font-weight: 600; margin: 4px 0 12px; }}
.suggestion .field {{ margin: 8px 0; font-size: 13px; }}
.suggestion .field strong {{ color: #475569; }}
.suggestion .evidence {{
    font-family: ui-monospace, "SF Mono", monospace;
    background: #f1f5f9;
    padding: 6px 10px;
    border-radius: 6px;
    display: inline-block;
    font-size: 12px;
}}
.suggestion .fix {{ background: #fefce8; padding: 10px 12px; border-radius: 6px; white-space: pre-wrap; }}
.suggestion .example {{ background: #ecfdf5; padding: 10px 12px; border-radius: 6px; font-style: italic; }}
.verdict-section {{
    padding: 30px 40px;
    border-top: 1px solid #e2e8f0;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
th {{
    text-align: left;
    padding: 10px 12px;
    background: #f1f5f9;
    color: #475569;
    font-weight: 600;
    border-bottom: 2px solid #e2e8f0;
}}
td {{
    padding: 10px 12px;
    border-bottom: 1px solid #f1f5f9;
}}
tr.pass {{ background: #f0fdf4; }}
tr.fail {{ background: #fef2f2; }}
tr.na {{ background: #f8fafc; }}
.verdict-badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
}}
.verdict-badge.pass {{ background: #dcfce7; color: #166534; }}
.verdict-badge.fail {{ background: #fee2e2; color: #991b1b; }}
.verdict-badge.na {{ background: #e2e8f0; color: #475569; }}
.verdict-badge.notimpl {{ background: #fef3c7; color: #92400e; }}
.footer {{
    background: #1e293b;
    color: #94a3b8;
    padding: 20px 40px;
    font-size: 12px;
    text-align: center;
}}
.footer a {{ color: #93c5fd; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">

    <!-- 头部 -->
    <div class="header">
        <h1>📊 评分报告</h1>
        <div class="subtitle">美团对话外呼任务评测系统</div>
        <div class="meta">
            <span>📋 对话: {dialogue_id}</span>
            <span>📑 指令: {instruction_id}</span>
            <span>🔢 约束: {n_constraints} 条</span>
        </div>
    </div>

    <!-- 大字评分 -->
    <div class="score-section">
        <div class="score-big">
            <span class="number">{final_score}</span><span class="max">/ 100</span>
        </div>
        <div><span class="score-grade">{grade}</span></div>
        <div class="score-meta">
            <div class="item">原始分: <strong>{raw_score}</strong></div>
            <div class="item">上限: <strong>{ceiling}</strong></div>
            <div class="item">Critical 通过率: <strong>{critical_pct}%</strong></div>
        </div>
    </div>

    <!-- 维度分 + 雷达图 -->
    <div class="dim-section">
        <h2 class="section-title">📐 5 维度评分</h2>
        <div class="dim-grid">
            <div class="radar-container">
                {radar_svg}
            </div>
            <div class="dim-list">
                {dim_cards}
            </div>
        </div>
    </div>

    <!-- 约束统计 -->
    <div class="dim-section">
        <h2 class="section-title">✅ 约束执行情况</h2>
        <div class="stats-grid">
            <div class="stat-card pass">
                <div class="label">Pass ✅</div>
                <div class="value">{n_pass}</div>
            </div>
            <div class="stat-card fail">
                <div class="label">Fail ❌</div>
                <div class="value">{n_fail}</div>
            </div>
            <div class="stat-card na">
                <div class="label">N/A ➖</div>
                <div class="value">{n_na}</div>
            </div>
            <div class="stat-card skip">
                <div class="label">Not Impl ⏳</div>
                <div class="value">{n_notimpl}</div>
            </div>
        </div>
    </div>

    <!-- 优化建议 -->
    {suggestions_html}

    <!-- 详细判定 -->
    <div class="verdict-section">
        <h2 class="section-title">📋 详细判定 (Fail + 主要 Pass)</h2>
        <table>
            <thead>
                <tr>
                    <th>约束 ID</th>
                    <th>类型</th>
                    <th>Verdict</th>
                    <th>名称</th>
                    <th>证据</th>
                </tr>
            </thead>
            <tbody>
                {verdict_rows}
            </tbody>
        </table>
    </div>

    <div class="footer">
        美团黑客松命题二 | 评测系统 v1.0 | 生成时间: {timestamp}
    </div>

</div>
</body>
</html>"""


def render_radar_svg(dim_scores: dict, size: int = 280) -> str:
    """生成 SVG 雷达图 (不依赖外部库)"""
    dims = [
        ("D1_flow_compliance", "D1 流程"),
        ("D2_task_completion", "D2 任务"),
        ("D3_constraint_compliance", "D3 约束"),
        ("D4_knowledge_accuracy", "D4 知识"),
        ("D5_dialogue_quality", "D5 对话"),
    ]
    
    cx, cy = size / 2, size / 2
    max_r = size / 2 - 40
    
    # 5 个轴的角度 (从顶部开始, 顺时针)
    n = 5
    angles = [-math.pi/2 + 2*math.pi*i/n for i in range(n)]
    
    # 背景多边形 (4 圈: 25%/50%/75%/100%)
    grid_polygons = []
    for level in [0.25, 0.5, 0.75, 1.0]:
        r = max_r * level
        points = []
        for a in angles:
            x = cx + r * math.cos(a)
            y = cy + r * math.sin(a)
            points.append(f"{x:.1f},{y:.1f}")
        grid_polygons.append(
            f'<polygon points="{" ".join(points)}" fill="none" stroke="#e2e8f0" stroke-width="1"/>'
        )
    
    # 轴线
    axis_lines = []
    for a in angles:
        x = cx + max_r * math.cos(a)
        y = cy + max_r * math.sin(a)
        axis_lines.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#cbd5e0" stroke-width="1"/>'
        )
    
    # 数据多边形
    data_points = []
    for (key, _), a in zip(dims, angles):
        score = dim_scores.get(key) or 0
        if score is None:
            score = 0
        r = max_r * (score / 100)
        x = cx + r * math.cos(a)
        y = cy + r * math.sin(a)
        data_points.append(f"{x:.1f},{y:.1f}")
    data_polygon = f'<polygon points="{" ".join(data_points)}" fill="rgba(102,126,234,0.3)" stroke="rgb(102,126,234)" stroke-width="2"/>'
    
    # 数据点
    data_dots = []
    for p in data_points:
        x, y = p.split(",")
        data_dots.append(f'<circle cx="{x}" cy="{y}" r="4" fill="rgb(102,126,234)"/>')
    
    # 标签
    labels = []
    for (key, name), a in zip(dims, angles):
        score = dim_scores.get(key)
        label_r = max_r + 22
        x = cx + label_r * math.cos(a)
        y = cy + label_r * math.sin(a)
        # 调整 textAnchor
        if abs(math.cos(a)) < 0.1:
            anchor = "middle"
        elif math.cos(a) > 0:
            anchor = "start"
        else:
            anchor = "end"
        score_text = f"{score:.0f}" if score is not None else "N/A"
        labels.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="12" fill="#475569" dy="4">{name} ({score_text})</text>'
        )
    
    svg = f"""<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
    {''.join(grid_polygons)}
    {''.join(axis_lines)}
    {data_polygon}
    {''.join(data_dots)}
    {''.join(labels)}
</svg>"""
    return svg


def render_dim_cards(dim_scores: dict) -> str:
    """5 维度卡片列表"""
    dims = [
        ("D1_flow_compliance", "D1 流程遵循度", "25%"),
        ("D2_task_completion", "D2 任务完成度", "25%"),
        ("D3_constraint_compliance", "D3 约束遵循度", "20%"),
        ("D4_knowledge_accuracy", "D4 知识准确性", "15%"),
        ("D5_dialogue_quality", "D5 对话质量", "15%"),
    ]
    cards = []
    for key, name, weight in dims:
        score = dim_scores.get(key)
        if score is None:
            cards.append(f"""
                <div class="dim-card">
                    <div class="name">{name}</div>
                    <div class="score">N/A</div>
                    <div class="weight">权重 {weight}</div>
                </div>""")
        else:
            cls = "good" if score >= 80 else ("ok" if score >= 60 else "bad")
            cards.append(f"""
                <div class="dim-card {cls}">
                    <div class="name">{name}</div>
                    <div class="score">{score:.0f}</div>
                    <div class="weight">权重 {weight}</div>
                </div>""")
    return "\n".join(cards)


def render_suggestions(detailed: list) -> str:
    """优化建议 HTML"""
    if not detailed:
        return ""
    
    html_parts = [
        '<div class="suggestion-section">',
        f'<h2 class="section-title">💡 优化建议 ({len(detailed)} 条)</h2>'
    ]
    
    for s in detailed:
        priority = s.get("priority", "P3_LOW")
        p_class = {"P0_CRITICAL": "p0", "P0_RED_LINE": "p0", 
                   "P1_HIGH": "p1", "P2_MEDIUM": "p2", "P3_LOW": "p3"}.get(priority, "p3")
        cid = s.get("constraint_id", "")
        cname = s.get("constraint_name", "")[:50]
        problem = s.get("problem", "")
        evidence = s.get("evidence", "")[:120]
        how_to_fix = s.get("how_to_fix", "")
        expected = s.get("expected_impact", "")
        example = s.get("example", "")
        category = s.get("category", "")
        
        # 简化 priority 显示
        p_short = priority.replace("P0_", "").replace("P1_", "").replace("P2_", "").replace("P3_", "")
        
        html_parts.append(f"""
            <div class="suggestion {p_class}">
                <div class="head">
                    <span class="priority-badge {p_class}">{p_short}</span>
                    <span class="cid">{cid}</span>
                    {'<span style="color:#94a3b8;font-size:12px">| ' + category + '</span>' if category else ''}
                </div>
                <div class="problem">⚠️ {problem}</div>
                {f'<div class="field"><strong>📌 证据:</strong> <span class="evidence">{evidence}</span></div>' if evidence else ''}
                <div class="field"><strong>🔧 改进方法:</strong></div>
                <div class="fix">{how_to_fix}</div>
                {f'<div class="field"><strong>💚 示例:</strong></div><div class="example">{example}</div>' if example else ''}
                {f'<div class="field" style="margin-top:8px;color:#16a34a"><strong>📈 {expected}</strong></div>' if expected else ''}
            </div>""")
    
    html_parts.append('</div>')
    return "\n".join(html_parts)


def render_verdict_rows(verdicts: list, limit: int = 25) -> str:
    """详细判定表格"""
    # 优先显示 fail, 再 pass, 再 na
    sorted_v = sorted(verdicts, key=lambda v: {"fail": 0, "pass": 1, "na": 2, "not_implemented": 3, "error": 4}.get(v.get("verdict"), 5))
    
    rows = []
    for v in sorted_v[:limit]:
        verdict = v.get("verdict", "?")
        v_class = {"pass": "pass", "fail": "fail", "na": "na", "not_implemented": "na"}.get(verdict, "")
        badge_class = {"not_implemented": "notimpl"}.get(verdict, verdict)
        cid = v.get("constraint_id", "")
        vtype = v.get("verifier_type", "")[:14]
        cname = v.get("constraint_name", "")[:50]
        evi = (v.get("evidence", "") or v.get("reason", ""))[:80]
        rows.append(f"""
            <tr class="{v_class}">
                <td><strong>{cid}</strong></td>
                <td>{vtype}</td>
                <td><span class="verdict-badge {badge_class}">{verdict}</span></td>
                <td>{cname}</td>
                <td style="font-size:11px;color:#64748b">{evi}</td>
            </tr>""")
    
    if len(verdicts) > limit:
        rows.append(f'<tr><td colspan="5" style="text-align:center;color:#94a3b8">... 还有 {len(verdicts)-limit} 条未显示</td></tr>')
    
    return "\n".join(rows)


def generate_html_report(pipeline_output: dict, instruction: dict = None) -> str:
    """主入口: 渲染 HTML 报告"""
    from datetime import datetime
    
    score_report = pipeline_output.get("score_report", {})
    final_score = score_report.get("final_score", 0)
    
    # 评级配色
    if final_score >= 90:
        color1, color2 = "#16a34a", "#22c55e"
        grade = "🎉 优秀"
    elif final_score >= 70:
        color1, color2 = "#f59e0b", "#fbbf24"
        grade = "✅ 良好"
    elif final_score >= 50:
        color1, color2 = "#ea580c", "#fb923c"
        grade = "⚠️ 需改进"
    else:
        color1, color2 = "#dc2626", "#f87171"
        grade = "❌ 不合格"
    
    dim_scores = score_report.get("dim_scores", {})
    stats = pipeline_output.get("stats", {})
    detailed_suggestions = pipeline_output.get("detailed_suggestions", [])
    verdicts = pipeline_output.get("verdict_details", [])
    
    n_constraints = stats.get("total_constraints", len(verdicts))
    
    html = HTML_TEMPLATE.format(
        dialogue_id=pipeline_output.get("dialogue_id", "?"),
        instruction_id=pipeline_output.get("instruction_id", "?"),
        n_constraints=n_constraints,
        final_score=final_score,
        score_color1=color1,
        score_color2=color2,
        grade=grade,
        raw_score=f"{score_report.get('raw_score', 0):.1f}",
        ceiling=score_report.get("ceiling", "-"),
        critical_pct=f"{score_report.get('critical_pass_rate', 0)*100:.0f}",
        radar_svg=render_radar_svg(dim_scores),
        dim_cards=render_dim_cards(dim_scores),
        n_pass=stats.get("pass", 0),
        n_fail=stats.get("fail", 0),
        n_na=stats.get("na", 0),
        n_notimpl=stats.get("not_implemented", 0),
        suggestions_html=render_suggestions(detailed_suggestions),
        verdict_rows=render_verdict_rows(verdicts),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return html


# ============================================================
# CLI 入口
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="pipeline 输出的 JSON")
    parser.add_argument("--output", required=True, help="HTML 文件路径")
    args = parser.parse_args()
    
    with open(args.input, encoding="utf-8") as f:
        pipeline_output = json.load(f)
    
    html = generate_html_report(pipeline_output)
    
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"✓ HTML 报告: {args.output}")
    print(f"  大小: {len(html) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
