#!/usr/bin/env python3
"""Build the self-contained HTML report for the validated v4 direct regrade."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "direct-result-v7"
MANIFEST = ROOT / "rubrics/document-rubrics.v4.json"
REPORT = ROOT / "direct-v4-report.html"


def load(path: Path):
    return json.loads(path.read_text())


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


evaluation = load(RESULT / "document-evaluation.json")
validation = load(RESULT / "validation.json")
manifest = load(MANIFEST)
reward = evaluation["rewards"]
by_id = {row["rubric_id"]: row for row in evaluation["results"]}
raw = evaluation["judge"]["raw_results"]
adjudicated = set(evaluation["judge"]["adjudicated_groups"])
labels = {
    "prd": "PRD",
    "tech_design": "技术设计",
    "test_design": "测试设计",
}

cards = []
for group in manifest["groups"]:
    group_id = group["group_id"]
    for rubric in group["rubrics"]:
        row = by_id[rubric["rubric_id"]]
        initial = [
            next(item["verdict"] for item in run["results"]
                 if item["rubric_id"] == rubric["rubric_id"])
            for run in raw[group_id]
        ]
        disagreement = len(set(initial)) > 1
        judge_note = (
            "单项分歧后裁决" if disagreement else
            "所在组分歧，裁决轮复核" if group_id in adjudicated else
            "双 Judge 一致"
        )
        evidence = "".join(
            f"<tr><td><code>{esc(item['path'])}</code></td>"
            f"<td>{esc(item['location'])}</td><td>{esc(item['quote'])}</td></tr>"
            for item in row["evidence"]
        )
        verdict = row["verdict"]
        cards.append(f"""
<article class="rubric" data-verdict="{verdict}" data-critical="{str(row['critical']).lower()}"
 data-search="{esc((rubric['rubric_id'] + ' ' + rubric['title'] + ' ' + rubric['criteria'] + ' ' + row['reason']).lower())}">
  <div class="rubric-head"><div><code>{esc(rubric['rubric_id'])}</code><h3>{esc(rubric['title'])}</h3></div>
  <div><span class="badge llm">LLM Judge</span><span class="badge {'pass' if verdict == 'P' else 'fail'}">{verdict}</span>{'<span class="badge critical">关键项</span>' if row['critical'] else ''}</div></div>
  <p class="meta">{esc(labels[group_id])} · 首轮 {'/'.join(initial)} · {judge_note}</p>
  <div class="grid"><section><h4>评分条件</h4><p>{esc(rubric['criteria'])}</p></section>
  <section><h4>最终判定</h4><p>{esc(row['reason'])}</p><p>Issue：<code>{esc(row.get('issue_id') or '—')}</code></p></section></div>
  <details><summary>证据 {len(row['evidence'])} 条</summary><div class="table"><table><thead><tr><th>路径</th><th>位置</th><th>摘录</th></tr></thead><tbody>{evidence}</tbody></table></div></details>
</article>""")

group_rows = "".join(
    f"<tr><td>{esc(labels[group])}</td><td>{score * 100:.2f}%</td></tr>"
    for group, score in evaluation["groups"].items()
)

doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SDLC v4 Direct Judge 验收报告</title>
<style>
:root{{--ink:#182230;--muted:#667085;--line:#d9e1ec;--paper:#f5f7fb;--blue:#155eef;--green:#087443;--red:#b42318;--amber:#93370d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}}
header{{padding:48px max(24px,calc((100vw - 1180px)/2));background:linear-gradient(120deg,#101828,#1849a9);color:#fff}}header h1{{margin:6px 0;font-size:34px}}header p{{max-width:880px;color:#d6e4ff}}main{{max-width:1180px;margin:auto;padding:28px 24px 72px}}h2{{margin-top:34px;font-size:24px}}h3{{margin:0;font-size:17px}}h4{{margin:0 0 7px;font-size:12px;text-transform:uppercase;color:#475467}}.metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}.metric,.panel,.rubric{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px}}.metric span,.meta,.muted{{color:var(--muted)}}.metric b{{display:block;font-size:25px;margin-top:4px}}.cols,.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.flow{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}.flow div{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:13px}}.flow b{{display:block;color:var(--blue)}}.table{{overflow:auto;border:1px solid var(--line);border-radius:9px}}table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#eef3fb}}.filters{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}}button,input{{border:1px solid var(--line);border-radius:999px;background:#fff;padding:7px 12px}}button{{cursor:pointer}}button.active{{background:#101828;color:#fff}}input{{min-width:280px}}.rubric{{margin:11px 0}}.rubric.hidden{{display:none}}.rubric-head{{display:flex;justify-content:space-between;gap:12px}}.rubric-head>div{{display:flex;align-items:center;gap:9px;flex-wrap:wrap}}.rubric-head>div:first-child>code{{background:#edf2f8;padding:6px;border-radius:6px;font-weight:700}}.badge{{padding:3px 8px;border-radius:999px;font-size:12px}}.llm{{background:#eee9ff;color:#5925dc}}.pass{{background:#e7f6ec;color:var(--green)}}.fail{{background:#feeceb;color:var(--red)}}.critical{{background:#fff4e5;color:var(--amber)}}.grid section{{background:#f8fafc;border-radius:8px;padding:12px}}details{{margin-top:10px}}summary{{cursor:pointer;font-weight:600}}.callout{{border-left:4px solid var(--blue);background:#eef4ff;padding:14px 16px;border-radius:8px}}@media(max-width:850px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.cols,.grid{{grid-template-columns:1fr}}.flow{{grid-template-columns:1fr}}}}@media print{{.filters{{display:none}}body{{background:#fff}}}}
</style></head><body>
<header><div>HARBOR · VKE · FIXED INLINE EVIDENCE</div><h1>SDLC v4 Direct Judge 验收报告</h1><p>正式运行 {esc(validation['run_id'])}。复用 source trial 文档，不重新调用 Runner；文档 Judge 直接调用 gpt-5.6-sol，不启动 Judge Agent。</p></header>
<main>
<section><h2>结论</h2><div class="callout"><strong>完整技术链路通过，文档验收未全通过。</strong> 1/1 trial 完成、0 exception、交付完整；{reward['rubric_passed']}/{reward['rubric_total']} 条 Rubric 通过，最终 reward 为最低分组 {reward['reward']:.3f}。</div>
<div class="metrics" style="margin-top:14px"><div class="metric"><span>Reward</span><b>{reward['reward']:.3f}</b></div><div class="metric"><span>Rubric</span><b>{reward['rubric_passed']}/{reward['rubric_total']}</b></div><div class="metric"><span>Critical</span><b>{reward['critical_pass_rate']*100:.2f}%</b></div><div class="metric"><span>Delivery</span><b>{reward['delivery_completeness']}</b></div><div class="metric"><span>Acceptance</span><b>{reward['document_acceptance']}</b></div></div></section>
<section class="cols"><div><h2>分组结果</h2><div class="table"><table><thead><tr><th>分组</th><th>通过率</th></tr></thead><tbody>{group_rows}</tbody></table></div></div>
<div><h2>运行验证</h2><div class="panel"><ul><li>实际模型：gpt-5.6-sol（{validation['judge']['calls']}/{validation['judge']['calls']}）</li><li>双 Judge：3 组；裁决：{esc('、'.join(validation['judge']['adjudicated_groups']) or '无')}</li><li>协议重试：{validation['judge']['protocol_retries']}；非空 stderr：{validation['judge']['nonempty_stderr_files']}</li><li>GraphQL / Base / 模板结构：不进入 LLM Judge</li><li>凭证模式：一次性 0600 文件，读取后删除</li></ul></div></div></section>
<section><h2>评分流程</h2><div class="flow"><div><b>1 · 冻结产物</b>读取 source trial 已接受的 PRD、技术设计与测试设计。</div><div><b>2 · 固定证据包</b>代码按 manifest 注入声明文件与 SHA-256。</div><div><b>3 · Direct Judge ×2</b>SSE Chat Completions，严格 JSON Schema。</div><div><b>4 · 分歧裁决</b>仅分歧组追加一次 direct Judge。</div><div><b>5 · 聚合</b>确定性计算分组通过率与 Harbor reward。</div></div></section>
<section><h2>范围边界</h2><div class="panel"><ul><li><code>target-schema.graphql</code> 未提供给 LLM；GraphQL GT checker 后续独立实现。</li><li>TDD4 明确禁止以目标 SDL 未进入证据包作为失败依据。</li><li>不评价 Markdown 章节或模板格式。</li><li>不执行代码、测试、部署或迁移。</li><li>v4 与历史 v1/v2/v3 的 Rubric 定义不同，分数不可直接作为模型能力增益比较。</li></ul></div></section>
<section><h2>22 条 Rubric</h2><div class="filters"><button class="active" data-filter="all">全部</button><button data-filter="P">通过</button><button data-filter="F">失败</button><button data-filter="critical">关键项</button><input id="search" placeholder="搜索 ID、标题或理由"></div>{''.join(cards)}</section>
<footer class="muted">Evaluation SHA-256：<code>{digest(RESULT/'document-evaluation.json')}</code><br>Reward SHA-256：<code>{digest(RESULT/'reward.json')}</code></footer>
</main><script>
const buttons=[...document.querySelectorAll('button[data-filter]')],cards=[...document.querySelectorAll('.rubric')],search=document.getElementById('search');let filter='all';function apply(){{const q=search.value.trim().toLowerCase();for(const c of cards){{const f=filter==='all'||c.dataset.verdict===filter||(filter==='critical'&&c.dataset.critical==='true');c.classList.toggle('hidden',!(f&&(!q||c.dataset.search.includes(q))))}}}}buttons.forEach(b=>b.onclick=()=>{{buttons.forEach(x=>x.classList.remove('active'));b.classList.add('active');filter=b.dataset.filter;apply()}});search.oninput=apply;
</script></body></html>"""

REPORT.write_text(doc)
print(REPORT)
print(f"bytes={REPORT.stat().st_size}")
print(f"sha256={digest(REPORT)}")
