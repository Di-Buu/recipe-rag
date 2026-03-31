"""
RAG 流程编排（基于 LlamaIndex）

职责：
- 配置 LlamaIndex 全局设置（Embedding、LLM）
- 管理 Qdrant 向量数据库的索引构建与加载
- 提供完整的 RAG 查询接口（含自定义中文 Prompt）
"""

from typing import Dict, Any, Optional

from qdrant_client import QdrantClient
from llama_index.core import Settings, VectorStoreIndex, StorageContext, PromptTemplate
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.dashscope import DashScope
from llama_index.vector_stores.qdrant import QdrantVectorStore

from src import config
from src.data.loader import load_recipes, build_text_nodes


# =============================================================================
# 自定义中文 Prompt 模板
# =============================================================================

RECIPE_QA_PROMPT = PromptTemplate("""\
你是一个专业的中文食谱推荐助手。请根据以下检索到的食谱信息回答用户问题。

## 检索到的食谱信息
{context_str}

## 回答要求
1. 仅基于上述食谱信息回答，不要编造不存在的食谱
2. 推荐时包含：菜名、所需食材、关键步骤概括
3. 如果检索结果与用户需求不相关，请诚实告知

## 用户问题
{query_str}
""")


class RAGPipeline:
    """基于 LlamaIndex 的 RAG Pipeline"""

    def __init__(self):
        self._configure_settings()
        self._vector_store = None
        self._index = None

    def _configure_settings(self):
        """配置 LlamaIndex 全局设置"""
        # Embedding 模型（本地 Qwen3-Embedding）
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=config.EMBEDDING_MODEL,
            device="cpu",
            max_length=config.EMBEDDING_MAX_LENGTH,
        )
        # Qwen3-Embedding 内置英文 query instruction 会破坏中文匹配
        # 将 prompts 设为空字符串，query 和 document 使用相同的 encoding 方式
        Settings.embed_model._model.prompts = {"query": "", "text": ""}

        # LLM（通义千问 DashScope API）
        Settings.llm = DashScope(
            model_name=config.DASHSCOPE_MODEL,
            api_key=config.DASHSCOPE_API_KEY,
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS,
        )

        # 不配置 text_splitter —— 每个食谱作为完整节点，不分块

    def _init_vector_store(self):
        """初始化 Qdrant 向量存储"""
        client = QdrantClient(path=config.QDRANT_PATH)
        self._vector_store = QdrantVectorStore(
            client=client,
            collection_name=config.QDRANT_COLLECTION_NAME,
        )

    def build_index(self, limit: Optional[int] = None):
        """
        构建向量索引

        流程：加载食谱 → 转为 TextNode（不分块）→ 向量化 → 写入 Qdrant

        Args:
            limit: 限制处理数量（调试用），None 表示全部
        """
        # 确保输出目录存在
        config.INDEX_DIR.mkdir(parents=True, exist_ok=True)

        # 加载食谱数据
        print(f"正在加载食谱数据（limit={limit}）...")
        recipes = load_recipes(config.RECIPES_FILE, limit=limit)
        print(f"已加载 {len(recipes)} 条食谱")

        # 转为 TextNode（每个食谱一个完整节点，不分块）
        print("正在转换为 TextNode（每个食谱一个完整节点）...")
        nodes = build_text_nodes(recipes, config.MAX_RECIPE_TEXT_LENGTH)
        print(f"已生成 {len(nodes)} 个节点")

        # 清空旧数据并重建
        client = QdrantClient(path=config.QDRANT_PATH)
        if client.collection_exists(config.QDRANT_COLLECTION_NAME):
            client.delete_collection(config.QDRANT_COLLECTION_NAME)

        self._vector_store = QdrantVectorStore(
            client=client,
            collection_name=config.QDRANT_COLLECTION_NAME,
        )

        storage_context = StorageContext.from_defaults(
            vector_store=self._vector_store
        )

        # 构建索引（直接传入 nodes，跳过分块，直接向量化 + 写入 Qdrant）
        print("正在构建向量索引（向量化 → 存储），请稍候...")
        self._index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            show_progress=True,
        )

        count = client.count(config.QDRANT_COLLECTION_NAME).count
        print(f"索引构建完成！Qdrant 中共 {count} 条记录")

    def load_index(self):
        """从已有的 Qdrant 数据库加载索引"""
        from pathlib import Path

        db_path = Path(config.QDRANT_PATH)
        if not db_path.exists():
            raise FileNotFoundError(
                f"未找到索引目录: {db_path}\n请先运行 --build 构建索引"
            )

        self._init_vector_store()
        self._index = VectorStoreIndex.from_vector_store(
            vector_store=self._vector_store,
        )
        print("已加载现有索引")

    def query(self, question: str) -> Dict[str, Any]:
        """
        执行 RAG 查询

        流程：问题向量化 → Qdrant Top-K 检索 → 自定义中文 Prompt → LLM 生成

        Args:
            question: 用户的自然语言问题

        Returns:
            {"answer": 生成的回答, "sources": 检索来源列表}
        """
        if self._index is None:
            raise RuntimeError("索引未加载，请先调用 build_index() 或 load_index()")

        query_engine = self._index.as_query_engine(
            similarity_top_k=config.TOP_K,
            text_qa_template=RECIPE_QA_PROMPT,
        )

        response = query_engine.query(question)

        # 提取检索来源（每个 source node 是一个完整食谱）
        sources = []
        for node in response.source_nodes:
            meta = node.metadata
            sources.append({
                "name": meta.get("name", "未知"),
                "dish": meta.get("dish", ""),
                "author": meta.get("author", ""),
                "keywords": meta.get("keywords", ""),
                "score": round(node.score, 4) if node.score else None,
                "text": node.text,  # 完整食谱文本，不截断
            })

        return {
            "answer": str(response),
            "sources": sources,
        }
