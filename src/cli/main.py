"""
命令行入口

用法：
    python -m src.cli.main --build --limit 100    构建索引（限100条，调试用）
    python -m src.cli.main --build                 构建全量索引
    python -m src.cli.main --query "红烧肉怎么做"   单次查询
    python -m src.cli.main --ui                    启动 Gradio Web UI（默认）
    python -m src.cli.main                         启动 Gradio Web UI
"""

import argparse

from src.pipeline.rag_pipeline import RAGPipeline


def main():
    parser = argparse.ArgumentParser(description="食谱推荐系统 - RAG")
    parser.add_argument("--build", action="store_true", help="构建向量索引")
    parser.add_argument("--limit", type=int, default=None, help="限制处理数量（调试用）")
    parser.add_argument("--query", type=str, default=None, help="单次查询")
    parser.add_argument("--ui", action="store_true", help="启动 Gradio Web UI")
    args = parser.parse_args()

    pipeline = RAGPipeline()

    if args.build:
        pipeline.build_index(limit=args.limit)
        return

    if args.query:
        pipeline.load_index()
        result = pipeline.query(args.query)
        print(f"\n{'='*60}")
        print(f"问题：{args.query}")
        print(f"{'='*60}")
        print(f"\n{result['answer']}\n")
        print(f"{'='*60}")
        print(f"检索来源（Top {len(result['sources'])}）：")
        for i, s in enumerate(result["sources"], 1):
            score = f" (相似度: {s['score']})" if s["score"] else ""
            print(f"\n  {i}. {s['name']}{score}")
            if s.get("dish") and s["dish"] != "未知":
                print(f"     菜名：{s['dish']}")
            if s.get("keywords"):
                print(f"     标签：{s['keywords']}")
        return

    # 默认启动 Gradio Web UI
    from src.ui.app import create_app

    pipeline.load_index()
    app = create_app(pipeline)
    app.launch()


if __name__ == "__main__":
    main()
