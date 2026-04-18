"""
RAG 流程编排模块（混合检索版本）

职责：
- 配置 LlamaIndex 全局设置（Embedding、LLM）
- 整合 RecipeIndexer（向量索引 + 父文档存储）与 RecipeRetriever（混合检索）
- 提供完整的 RAG 查询接口：混合检索 → Prompt 构建 → LLM 生成

核心流程：
    用户查询
        → RecipeRetriever.retrieve()（Dense + BM25 + RRF + 父文档聚合）
        → 评估结果质量 → 选择 Prompt 模板
        → format_context() + format_constraints() → 构建上下文
        → Settings.llm.chat() → 生成推荐回答
        → 结构化返回（answer + sources + query + filters）
"""

import json
import logging
from typing import Optional

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.dashscope import DashScope

from src import config
from src.pipeline.indexer import RecipeIndexer
from src.pipeline.retriever import RecipeRetriever
from src.pipeline.prompt_templates import (
    build_system_prompt,
    build_qa_prompt,
    build_weak_result_prompt,
    format_context,
    format_constraints,
)

logger = logging.getLogger(__name__)


class RAGPipeline:
    """基于 LlamaIndex 的 RAG Pipeline（混合检索版本）"""

    # 弱结果阈值：最高 relevance 低于此值则认为检索结果较弱
    WEAK_RESULT_THRESHOLD = 0.01

    def __init__(self):
        """
        初始化 Pipeline：
        1. 配置 LlamaIndex 全局设置（Embedding + LLM）
        2. 创建 RecipeIndexer 实例（但不加载索引）
        3. RecipeRetriever 将在索引加载后创建
        """
        self._configure_settings()
        self._indexer = RecipeIndexer(embedding_model=Settings.embed_model)
        self._retriever: Optional[RecipeRetriever] = None

    def _configure_settings(self):
        """
        配置 LlamaIndex 全局设置：
        - Embedding: 本地 Qwen3-Embedding-0.6B
        - LLM: 通义千问 DashScope API
        """
        # Embedding 模型（本地 Qwen3-Embedding）
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=config.EMBEDDING_MODEL,
            device="cpu",
            max_length=config.EMBEDDING_MAX_LENGTH,
        )
        # 清除 Qwen3-Embedding 内置英文 prompt，避免破坏中文匹配
        Settings.embed_model._model.prompts = {"query": "", "text": ""}

        # LLM（通义千问 DashScope API）
        Settings.llm = DashScope(
            model_name=config.DASHSCOPE_MODEL,
            api_key=config.DASHSCOPE_API_KEY,
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS,
            timeout=90,
        )

    def build_index(self, limit: int | None = None):
        """
        构建完整索引。

        流程：
        1. 加载富化食谱数据（recipes_enriched.json）
        2. RecipeIndexer.build_index() → Qdrant 向量索引 + 父文档存储
        3. RecipeRetriever.build_bm25_index() → BM25 稀疏索引

        参数:
            limit: 限制食谱数量（调试用），None 表示全部
        """
        # 加载富化食谱数据
        logger.info(f"正在加载富化食谱数据: {config.ENRICHED_DATA_PATH}")
        with open(config.ENRICHED_DATA_PATH, "r", encoding="utf-8") as f:
            recipes = json.load(f)

        if limit is not None:
            recipes = recipes[:limit]
            logger.info(f"限制处理 {limit} 条食谱（调试模式）")

        logger.info(f"共加载 {len(recipes)} 条食谱，开始构建索引...")

        # 构建 Qdrant 向量索引 + 父文档存储
        result = self._indexer.build_index(recipes, force_rebuild=True)
        logger.info(f"索引构建结果: {result}")

        # 创建混合检索器并构建 BM25 索引
        self._retriever = RecipeRetriever(self._indexer)
        self._retriever.build_bm25_index(force_rebuild=True)

        logger.info("Pipeline 索引构建完成")

    def load_index(self):
        """
        加载已有索引。

        流程：
        1. RecipeIndexer.load_index() → 加载 Qdrant + 父文档
        2. RecipeRetriever.build_bm25_index() → 从缓存加载 BM25
        """
        success = self._indexer.load_index()
        if not success:
            raise RuntimeError(
                "索引加载失败，请先运行 build_index() 构建索引"
            )

        # 创建混合检索器并加载 BM25 索引（优先从缓存）
        self._retriever = RecipeRetriever(self._indexer)
        self._retriever.build_bm25_index()

        logger.info("Pipeline 索引加载完成")

    def query(self, question: str, filters: dict | None = None) -> dict:
        """
        执行 RAG 查询。

        流程：
        1. 混合检索（Dense + BM25 + RRF + 父文档聚合）
        2. 评估结果质量，选择对应 Prompt 模板
        3. 调用 LLM 生成回答
        4. 返回结构化结果

        参数:
            question: 用户的自然语言问题
            filters: 可选的过滤条件（营养标签、食材禁忌等）

        返回:
            {
                "answer": str,         # LLM 生成的回答
                "sources": list[dict], # 检索来源列表
                "query": str,          # 原始查询
                "filters": dict|None,  # 使用的过滤条件
            }
        """
        if not self.is_loaded:
            raise RuntimeError("索引未加载，请先调用 build_index() 或 load_index()")

        # 1. 混合检索 → 父文档列表
        parent_docs = self._retriever.retrieve(
            query=question,
            top_k=config.TOP_K,
            filters=filters,
        )

        # 2. 无结果：直接返回，不调用 LLM
        if not parent_docs:
            return {
                "answer": "抱歉，未找到与您需求相关的食谱。"
                          "请尝试调整搜索关键词或放宽筛选条件。",
                "sources": [],
                "query": question,
                "filters": filters,
            }

        # 3. 格式化上下文和约束
        context = format_context(parent_docs, top_k=config.TOP_K)
        constraints = format_constraints(filters)
        system_prompt = build_system_prompt()

        # 4. 评估结果质量，选择 Prompt 模板
        max_relevance = max(doc["relevance"] for doc in parent_docs)
        if max_relevance < self.WEAK_RESULT_THRESHOLD:
            user_prompt = build_weak_result_prompt(context, question)
        else:
            user_prompt = build_qa_prompt(context, question, constraints)

        # 5. 调用 LLM 生成回答
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]
        response = Settings.llm.chat(messages)
        answer = response.message.content

        # 6. 构建来源列表
        sources = []
        for doc in parent_docs:
            sources.append({
                "recipe_id": doc["recipe_id"],
                "title": doc.get("metadata", {}).get("title", "未知菜谱"),
                "relevance": doc["relevance"],
                "matched_chunks": doc["matched_chunks"],
                "metadata": doc.get("metadata", {}),
            })

        return {
            "answer": answer,
            "sources": sources,
            "query": question,
            "filters": filters,
        }

    def query_stream(
        self,
        question: str,
        filters: Optional[dict] = None,
    ):
        """流式 RAG 查询：先返回检索结果，再逐 token 生成 LLM 回答

        Yields:
            第 1 次 yield: {"type": "sources", "sources": [...], "query": ...}
            后续 yield:    {"type": "token", "token": "..."}
            最后 yield:    {"type": "done"}
        """
        if not self.is_loaded:
            raise RuntimeError("索引未加载，请先调用 build_index() 或 load_index()")

        # 1. 混合检索
        parent_docs = self._retriever.retrieve(
            query=question,
            top_k=config.TOP_K,
            filters=filters,
        )

        # 2. 构建来源列表并先返回
        sources = []
        for doc in parent_docs:
            sources.append({
                "recipe_id": doc["recipe_id"],
                "title": doc.get("metadata", {}).get("title", "未知菜谱"),
                "relevance": doc["relevance"],
                "matched_chunks": doc["matched_chunks"],
                "metadata": doc.get("metadata", {}),
            })

        yield {"type": "sources", "sources": sources, "query": question}

        # 无结果
        if not parent_docs:
            yield {
                "type": "token",
                "token": "抱歉，未找到与您需求相关的食谱。请尝试调整搜索关键词或放宽筛选条件。",
            }
            yield {"type": "done"}
            return

        # 3. 构建 Prompt
        context = format_context(parent_docs, top_k=config.TOP_K)
        constraints = format_constraints(filters)
        system_prompt = build_system_prompt()

        max_relevance = max(doc["relevance"] for doc in parent_docs)
        if max_relevance < self.WEAK_RESULT_THRESHOLD:
            user_prompt = build_weak_result_prompt(context, question)
        else:
            user_prompt = build_qa_prompt(context, question, constraints)

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        # 4. 流式调用 LLM
        stream_response = Settings.llm.stream_chat(messages)
        for chunk in stream_response:
            delta = chunk.delta
            if delta:
                yield {"type": "token", "token": delta}

        yield {"type": "done"}

    @property
    def is_loaded(self) -> bool:
        """索引是否已加载（检索器是否就绪）"""
        return self._retriever is not None
