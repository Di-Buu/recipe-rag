"""
索引构建入口脚本

用法：
    # 构建完整索引（全部食谱）
    python -m src.pipeline.run_build_index

    # 调试模式（仅处理 100 条食谱）
    python -m src.pipeline.run_build_index --limit 100

    # 构建后执行测试查询
    python -m src.pipeline.run_build_index --test-query "推荐一道简单的家常菜"

    # 仅加载已有索引并测试查询
    python -m src.pipeline.run_build_index --load-only --test-query "低脂高蛋白的菜"
"""

import argparse
import logging
import time

from src.pipeline.rag_pipeline import RAGPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="食谱 RAG 索引构建工具")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="限制处理食谱数量（调试用）",
    )
    parser.add_argument(
        "--test-query", type=str, default=None,
        help="构建完成后执行一条测试查询",
    )
    parser.add_argument(
        "--load-only", action="store_true",
        help="仅加载已有索引（不重新构建）",
    )
    args = parser.parse_args()

    pipeline = RAGPipeline()

    if args.load_only:
        logger.info("正在加载已有索引...")
        start = time.time()
        pipeline.load_index()
        elapsed = time.time() - start
        logger.info(f"索引加载完成，耗时 {elapsed:.1f}s")
    else:
        logger.info("开始构建索引...")
        start = time.time()
        pipeline.build_index(limit=args.limit)
        elapsed = time.time() - start
        logger.info(f"索引构建完成，耗时 {elapsed:.1f}s")

    if args.test_query:
        logger.info(f"执行测试查询: {args.test_query}")
        start = time.time()
        result = pipeline.query(args.test_query)
        elapsed = time.time() - start

        print("\n" + "=" * 60)
        print(f"查询: {result['query']}")
        print(f"耗时: {elapsed:.2f}s")
        print(f"检索到 {len(result['sources'])} 个来源")
        print("=" * 60)
        print(f"\n{result['answer']}\n")

        if result["sources"]:
            print("--- 检索来源 ---")
            for i, src in enumerate(result["sources"], 1):
                print(f"  {i}. {src['title']}（相关度: {src['relevance']:.4f}, "
                      f"匹配子块: {src['matched_chunks']}）")
        print()


if __name__ == "__main__":
    main()
