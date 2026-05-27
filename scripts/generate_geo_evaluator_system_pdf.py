from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from textwrap import shorten

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "geo_evaluator_flow_method_pathmap.pdf"
LATEST_RUN = ROOT / "runs" / "manual_ai_recommendations_fixed_query_latest"


def register_font() -> str:
    for font_path in (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simsun.ttc")):
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("CJK", str(font_path)))
            return "CJK"
    return "Helvetica"


FONT = register_font()


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName=FONT,
            fontSize=23,
            leading=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#102033"),
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=10.5,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#5B6675"),
            spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName=FONT,
            fontSize=16,
            leading=22,
            textColor=colors.HexColor("#102033"),
            spaceBefore=10,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName=FONT,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#23415F"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9.4,
            leading=14,
            textColor=colors.HexColor("#1F2933"),
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=7.8,
            leading=10.5,
            textColor=colors.HexColor("#354152"),
        ),
        "cell": ParagraphStyle(
            "cell",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=7.4,
            leading=9.6,
            textColor=colors.HexColor("#1F2933"),
        ),
        "cell_head": ParagraphStyle(
            "cell_head",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=7.7,
            leading=9.8,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "flow_box": ParagraphStyle(
            "flow_box",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#102033"),
        ),
        "arrow": ParagraphStyle(
            "arrow",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=11,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#697386"),
        ),
    }


S = styles()


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text.replace("\n", "<br/>"), S[style])


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, "body"), bulletColor=colors.HexColor("#355C7D")) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=12,
    )


def table(rows: list[list[str | Paragraph]], widths: list[float], header: bool = True) -> Table:
    prepared = []
    for row_index, row in enumerate(rows):
        prepared.append([
            item if isinstance(item, Paragraph) else p(str(item), "cell_head" if header and row_index == 0 else "cell")
            for item in row
        ])
    t = Table(prepared, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#23415F") if header else colors.white),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#CAD3DF")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DFE5EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
            ]
        )
    )
    return t


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def flow_diagram() -> list:
    steps = [
        ("1. 资源库构建", "discover_site_urls / crawl_pages / paid_fetch_fallback\n收集官网、博客、文档和竞品页面"),
        ("2. 清洗与质量门", "clean_documents / score_content_quality\n过滤短正文、空内容、captcha、403 等低质量页面"),
        ("3. 切分与索引", "chunk_documents / build_keyword_index / build_vector_index\n生成 documents、chunks、BM25/vector index"),
        ("4. 模型独立场景", "client_acquisition_simulator\n每个模型独立生成 200 个客户问题，clean context"),
        ("5. 候选召回", "candidate_recall + keyword_search\n从本地资源库取 candidate_pool_size 个候选"),
        ("6. 同模型 rerank", "rerank_candidates\n生成问题的同一个模型排序候选，得到 Recall@5 / rank / winner"),
        ("7. 同模型答案", "build_answer_rows\n同一个模型基于 Top evidence 输出最终答案"),
        ("8. 汇总报告", "brand_performance / dimension_breakdown / competitive_gap_report\n输出品牌表现、弱维度、内容缺口"),
    ]
    story = []
    for idx, (title, body) in enumerate(steps):
        box = Table(
            [[p(f"<b>{title}</b><br/>{body}", "flow_box")]],
            colWidths=[170 * mm],
            hAlign="CENTER",
        )
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF5FB")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#4C78A8")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(box)
        if idx < len(steps) - 1:
            story.append(p("↓", "arrow"))
    return story


def latest_run_summary() -> list:
    retrieval = read_csv(LATEST_RUN / "retrieval_by_model.csv")
    brand_rows = read_csv(LATEST_RUN / "brand_performance_by_model.csv")
    answers = read_csv(LATEST_RUN / "model_answer_evaluations.csv")

    rows = [["模型", "赢家", "Alpha Top5", "Alpha Top10", "答案提到 Alpha", "错误"]]
    answer_by_model = {row["model"]: row for row in answers}
    for row in retrieval:
        answer = answer_by_model.get(row["model"], {})
        rows.append(
            [
                row.get("model", ""),
                row.get("winning_brand", ""),
                row.get("own_brand_in_top_5", ""),
                row.get("own_brand_in_top_10", ""),
                answer.get("brand_mentioned", ""),
                shorten(answer.get("error", "") or "-", width=58, placeholder="..."),
            ]
        )

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in brand_rows:
        if row.get("brand") == "AlphaXXXX":
            continue
        grouped.setdefault(row.get("brand", ""), []).append(row)
    leaders = []
    for brand, rows_for_brand in grouped.items():
        query_count = sum(int(row.get("query_count") or 0) for row in rows_for_brand)
        top5 = sum(int(row.get("top5_count") or 0) for row in rows_for_brand)
        top10 = sum(int(row.get("top10_count") or 0) for row in rows_for_brand)
        mentions = sum(int(row.get("model_mention_count") or 0) for row in rows_for_brand)
        ranks = [int(row["best_rank"]) for row in rows_for_brand if str(row.get("best_rank", "")).isdigit()]
        top5_share = top5 / query_count if query_count else 0
        mention_rate = mentions / len(rows_for_brand) if rows_for_brand else 0
        if top5_share > 0 or mention_rate > 0:
            leaders.append(
                {
                    "brand": brand,
                    "top5_query_share": f"{top5_share:.1%}",
                    "top10_query_share": f"{(top10 / query_count if query_count else 0):.1%}",
                    "model_mention_rate": f"{mention_rate:.1%}",
                    "best_rank": min(ranks) if ranks else "",
                }
            )
    leaders.sort(
        key=lambda r: (
            -float(r.get("top5_query_share", "0").rstrip("%") or 0),
            -float(r.get("model_mention_rate", "0").rstrip("%") or 0),
            r.get("brand", ""),
        )
    )
    leader_rows = [["品牌", "Top5 Share", "Top10 Share", "Mention Rate", "Best Rank"]]
    for row in leaders[:6]:
        leader_rows.append(
            [
                row.get("brand", ""),
                row.get("top5_query_share", ""),
                row.get("top10_query_share", ""),
                row.get("model_mention_rate", ""),
                row.get("best_rank", "") or "not ranked",
            ]
        )
    return [
        p("最近固定问题样例：<b>I want my company to get AI recommendations.</b>", "body"),
        table(rows, [43 * mm, 40 * mm, 22 * mm, 23 * mm, 27 * mm, 25 * mm]),
        Spacer(1, 5 * mm),
        p("当前样例中压过 AlphaXXXX 的主要品牌：", "body"),
        table(leader_rows, [55 * mm, 28 * mm, 28 * mm, 32 * mm, 25 * mm]),
    ]


def corpus_summary() -> list[list[str]]:
    docs = read_jsonl(ROOT / "data" / "processed" / "documents.jsonl")
    chunks = read_jsonl(ROOT / "data" / "processed" / "chunks.jsonl")
    urls_by_brand: dict[str, set[str]] = {}
    chunks_by_brand = Counter()
    for doc in docs:
        brand = str(doc.get("brand") or "Unknown")
        urls_by_brand.setdefault(brand, set()).add(str(doc.get("url") or ""))
    for chunk in chunks:
        chunks_by_brand[str(chunk.get("brand") or "Unknown")] += 1
    rows = [["品牌", "URL 数", "Chunk 数"]]
    for brand, urls in sorted(urls_by_brand.items(), key=lambda item: (-len(item[1]), item[0]))[:12]:
        rows.append([brand, str(len([url for url in urls if url])), str(chunks_by_brand.get(brand, 0))])
    return rows


def build_story() -> list:
    story: list = []
    story.append(p("GEO Evaluator 系统流程、评测方法与 Path Map", "title"))
    story.append(p("面向 AlphaXXXX 的 GEO / AI Search Visibility 资源库与多模型模拟评测框架", "subtitle"))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CAD3DF")))
    story.append(Spacer(1, 5 * mm))
    story.append(p("一页摘要", "h1"))
    story.append(
        p(
            "这个系统的目标不是做通用搜索引擎，而是构建一个可复现实验环境：把 AlphaXXXX 和竞品网站内容抓取到本地资源库，"
            "再让不同大模型在干净上下文里独立生成客户问题、模拟检索排序、生成最终答案，最后统计 AlphaXXXX 是否进入 Top5、"
            "是否被答案提到、哪些竞品压过它，以及内容缺口集中在哪里。"
        )
    )
    story.append(
        bullets(
            [
                "模型独立性：每个模型有自己的问题池、rerank、answer 和统计口径，避免上下文串扰。",
                "核心指标：own_brand_rank、Recall@5/Top5 share、Top10 share、Brand Mention Rate、Competitor Win Rate、matched URLs。",
                "报告输出：brand_performance_by_model.csv、dimension_breakdown.csv、competitive_gap_report.md，以及本 PDF 说明。",
                "当前正式配置：每个模型 200 个问题；3 persona × 5 journey stage 自动均匀分配。",
            ]
        )
    )
    story.append(PageBreak())

    story.append(p("1. 总体流程图", "h1"))
    story.extend(flow_diagram())
    story.append(PageBreak())

    story.append(p("2. 核心评测方法", "h1"))
    story.append(p("2.1 实验对象", "h2"))
    story.append(
        p(
            "评测对象是 AlphaXXXX 在不同 LLM 入口中的可见性。系统把本地资源库当作模拟 AI Search/RAG 的候选知识空间，"
            "再让具体模型对候选内容进行排序和最终回答。这样可以同时看到检索层问题和答案层问题。"
        )
    )
    story.append(p("2.2 模型独立评测", "h2"))
    story.append(
        bullets(
            [
                "场景生成：每个模型用 clean context 独立生成客户问题。配置项为 client_acquisition.queries_per_model。",
                "检索排序：同一个模型只 rerank 自己生成的问题，不评估其他模型的问题池。",
                "最终答案：同一个模型基于自己的 Top evidence 生成答案，用于统计 mention / recommendation。",
                "错误隔离：某个模型 API 失败只记录到 attempt/error，不中断其他模型。",
            ]
        )
    )
    story.append(p("2.3 指标定义", "h2"))
    metric_rows = [
        ["指标", "含义", "主要文件"],
        ["own_brand_rank", "AlphaXXXX 在模型排序结果中的名次；空值表示未召回或未进入结果。", "retrieval_by_model.csv"],
        ["Recall@5 / Top5 share", "AlphaXXXX 是否进入前 5 个检索候选；按模型/品牌聚合成 top5_query_share。", "retrieval_by_model.csv / brand_performance_by_model.csv"],
        ["Brand Mention Rate", "最终答案文本是否提到对应品牌。", "model_answer_evaluations.csv / brand_performance_by_model.csv"],
        ["Competitor Win Rate", "竞品排在 AlphaXXXX 之上或成为 winning_brand 的比例。", "retrieval_by_model.csv"],
        ["matched_urls", "进入候选或 TopN 的具体 URL，用于追踪是哪类页面赢了。", "retrieval_evidence_by_model.jsonl"],
        ["Answer Coverage", "通过答案、Top evidence 和 gap signals 判断是否覆盖用户真正关心的意图。", "competitive_gap_report.md"],
    ]
    story.append(table(metric_rows, [34 * mm, 93 * mm, 46 * mm]))
    story.append(PageBreak())

    story.append(p("3. 脚本框架结构", "h1"))
    structure_rows = [
        ["层级", "核心脚本/模块", "职责"],
        ["采集层", "discover_site_urls.py, crawl_pages.py, paid_fetch_fallback.py", "全站发现、分级抓取、本地失败后 Firecrawl/付费 fallback。"],
        ["质量层", "score_content_quality.py, clean_documents.py, merge_pages.py", "正文抽取、质量评分、去重、合并页面记录。"],
        ["索引层", "chunk_documents.py, build_keyword_index.py, build_vector_index.py", "生成 chunks、BM25 keyword index 和向量索引状态。"],
        ["评测主入口", "client_acquisition_simulator.py", "独立场景生成、candidate recall、模型 rerank、答案生成、品牌统计、竞争缺口报告。"],
        ["GeoEvaluator 模块", "scripts/geo_eval/*.py", "旧框架/通用 CLI：scenario、retrieval、model calls、answer evaluation、reports。"],
        ["分析层", "compare_brands.py, compare_run_performance.py, generate_report.py", "品牌对比、run 对比、补充报告。"],
        ["当前 PDF", "generate_geo_evaluator_system_pdf.py", "将流程、方法、结构和 path map 输出为 PDF。"],
    ]
    story.append(table(structure_rows, [25 * mm, 59 * mm, 88 * mm]))
    story.append(p("3.1 client_acquisition_simulator.py 内部主流程", "h2"))
    story.append(
        bullets(
            [
                "default_scenario_matrix / scenario_counts_for_model：读取配置并精确分配每模型 200 个问题。",
                "generate_query_rows：调用模型生成问题，记录 api_scenario_attempts。",
                "candidate_recall：从 BM25 index 召回候选页面。",
                "rerank_candidates：同模型 clean context rerank，输出 retrieval_by_model 和 evidence。",
                "build_answer_rows：同模型生成最终答案，输出 model_answer_evaluations。",
                "build_brand_performance_by_model / build_competitive_gap_report：聚合品牌表现、弱维度和内容缺口。",
            ]
        )
    )
    story.append(PageBreak())

    story.append(p("4. Path Map", "h1"))
    path_rows = [
        ["路径", "用途", "备注"],
        ["config/client_acquisition_simulator.yaml", "正式多模型配置", "queries_per_model=200；配置模型、目标品牌、竞品、输出目录。"],
        ["config/client_acquisition_simulator_smoke.yaml", "低成本 smoke test", "单模型、小样本，用于检查流程是否可跑。"],
        ["config/crawler.yaml", "爬虫配置", "本地抓取、Playwright fallback、Firecrawl/付费 fallback。"],
        ["data/processed/documents.jsonl", "页面级资源库", "每条记录代表一个抓取/清洗后的页面。"],
        ["data/processed/chunks.jsonl", "chunk 级资源库", "检索和 rerank 的主要候选文本。"],
        ["data/processed/bm25_index.pkl", "关键词召回索引", "candidate_recall 默认读取该文件。"],
        ["runs/client_acquisition_simulator/", "正式批量评测输出", "每模型 200 个问题时的默认输出目录。"],
        ["runs/manual_ai_recommendations_fixed_query_latest/", "最近固定问题样例输出", "问题为 I want my company to get AI recommendations."],
        [".env", "API key 本地持久化", "只保存密钥，不进入报告或 CSV。"],
        ["output/pdf/geo_evaluator_flow_method_pathmap.pdf", "本 PDF", "流程图、评测方法、脚本结构、path map。"],
    ]
    story.append(table(path_rows, [62 * mm, 48 * mm, 62 * mm]))
    story.append(p("4.1 资源库当前样例体量 Top 品牌", "h2"))
    story.append(table(corpus_summary(), [70 * mm, 35 * mm, 35 * mm]))
    story.append(PageBreak())

    story.append(p("5. 输出文件说明", "h1"))
    output_rows = [
        ["文件", "解释"],
        ["api_queries.csv", "模型生成或手动注入的问题池，包含 persona、journey_stage、scenario_model。"],
        ["api_rerank_attempts.jsonl", "每次 rerank API 调用状态，含失败原因。"],
        ["retrieval_by_model.csv", "每个模型/问题的 rank、Top5/Top10、winning_brand、matched_urls。"],
        ["retrieval_evidence_by_model.jsonl", "模型排序后的 Top evidence，含 URL、brand、title、text_preview。"],
        ["model_answer_evaluations.csv", "最终答案、是否提到 AlphaXXXX、是否推荐 AlphaXXXX、API 错误。"],
        ["brand_performance_by_model.csv", "按模型和品牌聚合 Top5 share、Top10 share、mention rate、top URLs。"],
        ["dimension_breakdown.csv", "按模型、persona、journey_stage 展示 AlphaXXXX 弱维度。"],
        ["competitive_gap_report.md", "可读竞争报告：哪些品牌在上面、可能缺口、内容信号。"],
    ]
    story.append(table(output_rows, [61 * mm, 112 * mm]))
    story.append(p("5.1 最近固定问题样例结果", "h2"))
    story.extend(latest_run_summary())
    story.append(PageBreak())

    story.append(p("6. 运行与扩展建议", "h1"))
    story.append(p("正式运行命令：", "h2"))
    story.append(p("python scripts/client_acquisition_simulator.py --config config/client_acquisition_simulator.yaml", "body"))
    story.append(p("建议的扩展方向：", "h2"))
    story.append(
        bullets(
            [
                "当数据增大时，把 JSONL/CSV 输出迁移到 DuckDB 或 SQLite，保留 run_id、model、query_id、brand 作为核心索引。",
                "将 crawler、index builder、simulator 拆成可重复 job，避免每次评测都重建资源库。",
                "增加 domain/topic taxonomy，让 gap signals 从关键词升级为主题维度，例如 pricing、case study、local proof、platform coverage。",
                "加入语义召回或 hybrid retrieval，避免 BM25 对同义表达过于敏感。",
                "为 API 调用增加缓存、重试、限速和成本日志，但保持 clean context 和模型独立统计不变。",
            ]
        )
    )
    return story


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 7)
    canvas.setFillColor(colors.HexColor("#697386"))
    canvas.drawString(18 * mm, 10 * mm, "AlphaXXXX GEO Evaluator - System Flow, Evaluation Method and Path Map")
    canvas.drawRightString(195 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=17 * mm,
        title="GEO Evaluator System Flow Method Path Map",
        author="Codex",
    )
    doc.build(build_story(), onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
