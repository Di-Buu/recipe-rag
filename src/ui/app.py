"""
Gradio Web UI

职责：
- 提供交互式 Web 界面供导师演示
- 展示 RAG 查询结果和检索来源
"""

import gradio as gr

from src.pipeline.rag_pipeline import RAGPipeline


def _format_sources(sources: list) -> str:
    """将检索来源格式化为 Markdown"""
    if not sources:
        return "*未检索到相关来源*"

    lines = []
    for i, s in enumerate(sources, 1):
        score_str = f"（相似度: {s['score']}）" if s["score"] else ""
        lines.append(f"### {i}. {s['name']} {score_str}")

        if s.get("dish") and s["dish"] != "未知":
            lines.append(f"**菜名：** {s['dish']}")

        if s.get("keywords"):
            lines.append(f"**标签：** {s['keywords']}")

        # 用折叠块展示完整食谱内容
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>查看完整食谱内容</summary>")
        lines.append("")
        lines.append(s["text"])
        lines.append("")
        lines.append("</details>")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _handle_query(question: str, pipeline: RAGPipeline):
    """处理用户查询"""
    if not question.strip():
        return "请输入您的问题", ""

    try:
        result = pipeline.query(question)
        answer = result["answer"]
        sources_md = _format_sources(result["sources"])
        return answer, sources_md
    except Exception as e:
        return f"查询出错: {e}", ""


def create_app(pipeline: RAGPipeline) -> gr.Blocks:
    """
    创建 Gradio 应用

    Args:
        pipeline: 已初始化的 RAG Pipeline

    Returns:
        Gradio Blocks 应用实例
    """
    with gr.Blocks(title="食谱推荐系统 - RAG") as app:
        gr.Markdown(
            "# 食谱推荐系统\n"
            "基于 RAG（检索增强生成）的智能食谱推荐。\n\n"
            "输入你的需求，系统会从知识库中检索相关食谱并生成推荐。"
        )

        with gr.Row():
            question_input = gr.Textbox(
                label="你想吃什么？",
                placeholder="例如：简单的家常红烧肉怎么做？/ 有什么适合减脂的低卡晚餐？",
                lines=2,
            )

        submit_btn = gr.Button("查询推荐", variant="primary")

        with gr.Row():
            with gr.Column(scale=3):
                answer_output = gr.Markdown(label="推荐结果")
            with gr.Column(scale=2):
                sources_output = gr.Markdown(label="检索来源")

        # 示例查询
        gr.Examples(
            examples=[
                "简单的家常红烧肉怎么做？",
                "有什么适合减脂的低卡晚餐？",
                "天气冷了，推荐几道暖身汤",
                "给小朋友做什么早餐好？",
            ],
            inputs=question_input,
        )

        # 绑定事件
        submit_btn.click(
            fn=lambda q: _handle_query(q, pipeline),
            inputs=question_input,
            outputs=[answer_output, sources_output],
        )
        question_input.submit(
            fn=lambda q: _handle_query(q, pipeline),
            inputs=question_input,
            outputs=[answer_output, sources_output],
        )

    return app
