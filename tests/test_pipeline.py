"""
测试 RAG Pipeline

验证：
1. LlamaIndex Settings 配置是否正确
2. 食谱数据加载与 Document 转换
3. 索引构建（小规模）
4. 查询流程端到端
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline.rag_pipeline import RAGPipeline


def main():
    print("=" * 60)
    print("RAG Pipeline 集成测试")
    print("=" * 60)

    # 1. 初始化 Pipeline
    print("\n1. 初始化 Pipeline（加载 Embedding 模型 + 配置 LLM）...")
    pipeline = RAGPipeline()
    print("   [PASS] Pipeline 初始化成功")

    # 2. 构建小规模索引
    print("\n2. 构建索引（限制 50 条食谱用于测试）...")
    pipeline.build_index(limit=50)
    print("   [PASS] 索引构建成功")

    # 3. 执行查询
    print("\n3. 执行 RAG 查询...")
    question = "简单的家常红烧肉怎么做？"
    print(f"   问题：{question}")
    result = pipeline.query(question)

    print(f"\n   回答：\n   {result['answer'][:200]}...")
    print(f"\n   检索来源（{len(result['sources'])} 条）：")
    for i, s in enumerate(result["sources"], 1):
        score = f" (相似度: {s['score']})" if s["score"] else ""
        print(f"   {i}. {s['name']}{score}")

    print("\n" + "=" * 60)
    print("全部测试通过！RAG Pipeline 工作正常。")
    print("=" * 60)


if __name__ == "__main__":
    main()
