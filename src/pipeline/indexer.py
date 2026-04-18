"""
索引构建器模块（indexer）

职责：
1. 加载富化食谱数据，调用 document_builder 生成父子文档
2. 将子块转为 LlamaIndex TextNode 并写入 Qdrant 向量数据库
3. 将父文档持久化为 JSON 文件（供检索阶段按 recipe_id 查找）
4. 支持增量检查：Qdrant 已有数据时可跳过或强制重建

核心流程：
    recipes_enriched.json
        → document_builder.build_all_nodes()
        → 子块 → TextNode → Qdrant（向量检索）
        → 父文档 → parent_docstore.json（完整上下文）
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from llama_index.core import Settings, VectorStoreIndex, StorageContext
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from src import config
from src.data.document_builder import build_all_nodes

logger = logging.getLogger(__name__)

# 子块元数据中需要移除的字段（Qdrant 不支持嵌套 dict / list of dict）
_METADATA_EXCLUDE_KEYS = {"ingredient_nutrition", "nutrition_summary", "step_pics"}


def _filter_child_metadata(metadata: dict) -> dict:
    """
    过滤子块元数据，移除 Qdrant 不支持的嵌套结构。

    保留规则：
    - tags / main_ingredients / nutrition_tags（list[str]）→ 保留
    - ingredient_nutrition（list[dict]）/ nutrition_summary（dict）/ step_pics → 移除
    """
    return {k: v for k, v in metadata.items() if k not in _METADATA_EXCLUDE_KEYS}


def _child_to_text_node(child: dict, recipe_id: str) -> TextNode:
    """
    将单个子块字典转为 LlamaIndex TextNode。

    参数:
        child: document_builder 生成的子块字典，含 text / metadata / chunk_type
        recipe_id: 所属食谱 ID

    返回:
        TextNode 实例，id_ 格式为 "{recipe_id}_{chunk_type}"
    """
    chunk_type = child["chunk_type"]
    chunk_id = f"{recipe_id}_{chunk_type}"
    # Qdrant 本地模式要求点 ID 为 UUID，用 uuid5 生成确定性 UUID
    node_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))
    filtered_meta = _filter_child_metadata(child["metadata"])
    # 保留逻辑 chunk_id 供检索器 RRF 融合使用
    filtered_meta["chunk_id"] = chunk_id
    meta_keys = list(filtered_meta.keys())

    return TextNode(
        text=child["text"],
        id_=node_uuid,
        metadata=filtered_meta,
        excluded_embed_metadata_keys=meta_keys,
        excluded_llm_metadata_keys=meta_keys,
    )


class RecipeIndexer:
    """
    食谱索引构建器

    负责将富化食谱数据构建为可检索的向量索引：
    - 子块（info / ingredient / step）→ Qdrant 向量数据库
    - 父文档（完整食谱文本 + 全量元数据）→ JSON 文件
    """

    def __init__(self, embedding_model=None):
        """
        初始化索引构建器。

        参数:
            embedding_model: 可选，传入已加载的 HuggingFaceEmbedding 实例
                             未传入时在 build_index 时自动加载
        """
        self._embedding_model = embedding_model
        self._qdrant_client: Optional[QdrantClient] = None
        self._vector_store: Optional[QdrantVectorStore] = None
        self._parent_store: dict[str, dict] = {}  # {recipe_id: {"text": ..., "metadata": ...}}

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def build_index(self, recipes: list[dict], force_rebuild: bool = False) -> dict:
        """
        构建完整索引（子块入 Qdrant + 父文档持久化）。

        参数:
            recipes: 富化后的食谱列表
            force_rebuild: 如果 Qdrant 已有数据，是否强制重建

        返回:
            {"child_count": int, "parent_count": int, "qdrant_count": int}
        """
        # 确保输出目录存在
        Path(config.QDRANT_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(config.DOCSTORE_PATH).parent.mkdir(parents=True, exist_ok=True)

        # 初始化 Qdrant 客户端
        self._qdrant_client = QdrantClient(path=config.QDRANT_PATH)

        # 增量检查：如果 collection 已存在且有数据，且不强制重建，则跳过
        if not force_rebuild and self._collection_has_data():
            count = self._qdrant_client.count(config.QDRANT_COLLECTION_NAME).count
            logger.info(f"Qdrant 已有 {count} 条数据，跳过索引构建（使用 force_rebuild=True 强制重建）")
            # 加载已有的父文档
            self._load_parent_store()
            return {
                "child_count": 0,
                "parent_count": len(self._parent_store),
                "qdrant_count": count,
            }

        # 强制重建时先删除旧 collection
        if force_rebuild and self._qdrant_client.collection_exists(config.QDRANT_COLLECTION_NAME):
            logger.info("删除旧 Qdrant collection...")
            self._qdrant_client.delete_collection(config.QDRANT_COLLECTION_NAME)

        # 配置 Embedding 模型
        self._setup_embedding()

        # 构建父子文档
        logger.info(f"正在构建父子文档（共 {len(recipes)} 条食谱）...")
        all_nodes = build_all_nodes(recipes)

        # 分离子块和父文档
        text_nodes: list[TextNode] = []
        parent_store: dict[str, dict] = {}

        for node_group in all_nodes:
            parent = node_group["parent"]
            recipe_id = parent["metadata"]["recipe_id"]

            # 父文档存入内存字典（后续持久化为 JSON）
            parent_store[recipe_id] = {
                "text": parent["text"],
                "metadata": parent["metadata"],
            }

            # 子块转为 TextNode
            for child in node_group["children"]:
                text_node = _child_to_text_node(child, recipe_id)
                text_nodes.append(text_node)

        logger.info(f"生成 {len(text_nodes)} 个子块 TextNode，{len(parent_store)} 个父文档")

        # 创建 Qdrant VectorStore 并写入
        self._vector_store = QdrantVectorStore(
            client=self._qdrant_client,
            collection_name=config.QDRANT_COLLECTION_NAME,
        )
        storage_context = StorageContext.from_defaults(vector_store=self._vector_store)

        logger.info("正在构建向量索引（Embedding + 写入 Qdrant）...")
        VectorStoreIndex(
            nodes=text_nodes,
            storage_context=storage_context,
            show_progress=True,
        )

        # 持久化父文档
        self._parent_store = parent_store
        self._save_parent_store()

        qdrant_count = self._qdrant_client.count(config.QDRANT_COLLECTION_NAME).count
        logger.info(f"索引构建完成！Qdrant {qdrant_count} 条，父文档 {len(parent_store)} 条")

        return {
            "child_count": len(text_nodes),
            "parent_count": len(parent_store),
            "qdrant_count": qdrant_count,
        }

    def load_index(self) -> bool:
        """
        加载已有索引，返回是否成功。

        验证：
        1. Qdrant collection 存在且有数据
        2. 父文档 JSON 文件存在且可加载
        """
        # 检查 Qdrant 数据库目录
        if not Path(config.QDRANT_PATH).exists():
            logger.warning(f"Qdrant 数据库目录不存在: {config.QDRANT_PATH}")
            return False

        # 检查父文档文件
        if not Path(config.DOCSTORE_PATH).exists():
            logger.warning(f"父文档文件不存在: {config.DOCSTORE_PATH}")
            return False

        try:
            self._qdrant_client = QdrantClient(path=config.QDRANT_PATH)

            if not self._collection_has_data():
                logger.warning("Qdrant collection 为空或不存在")
                return False

            self._vector_store = QdrantVectorStore(
                client=self._qdrant_client,
                collection_name=config.QDRANT_COLLECTION_NAME,
            )

            self._load_parent_store()

            count = self._qdrant_client.count(config.QDRANT_COLLECTION_NAME).count
            logger.info(f"索引加载成功：Qdrant {count} 条，父文档 {len(self._parent_store)} 条")
            return True

        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            return False

    def get_parent_text(self, recipe_id: str) -> Optional[str]:
        """通过 recipe_id 查找父文档文本。"""
        entry = self._parent_store.get(recipe_id)
        return entry["text"] if entry else None

    def get_parent_metadata(self, recipe_id: str) -> Optional[dict]:
        """通过 recipe_id 查找父文档元数据。"""
        entry = self._parent_store.get(recipe_id)
        return entry["metadata"] if entry else None

    @property
    def vector_store(self) -> Optional[QdrantVectorStore]:
        """供 retriever 使用的 Qdrant vector store。"""
        return self._vector_store

    @property
    def qdrant_client(self) -> Optional[QdrantClient]:
        """供 retriever 使用的 Qdrant client。"""
        return self._qdrant_client

    @property
    def parent_store(self) -> dict[str, dict]:
        """父文档存储字典（只读访问）。"""
        return self._parent_store

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _setup_embedding(self):
        """配置 Embedding 模型到 LlamaIndex Settings。"""
        if self._embedding_model is None:
            logger.info(f"正在加载 Embedding 模型: {config.EMBEDDING_MODEL}")
            self._embedding_model = HuggingFaceEmbedding(
                model_name=config.EMBEDDING_MODEL,
                max_length=config.EMBEDDING_MAX_LENGTH,
            )
            # 清除 Qwen3-Embedding 内置的英文 instruction，避免破坏中文匹配
            self._embedding_model._model.prompts = {"query": "", "text": ""}

        Settings.embed_model = self._embedding_model

    def _collection_has_data(self) -> bool:
        """检查 Qdrant collection 是否存在且有数据。"""
        if not self._qdrant_client.collection_exists(config.QDRANT_COLLECTION_NAME):
            return False
        return self._qdrant_client.count(config.QDRANT_COLLECTION_NAME).count > 0

    def _save_parent_store(self):
        """将父文档字典持久化为 JSON 文件。"""
        with open(config.DOCSTORE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._parent_store, f, ensure_ascii=False, indent=2)
        logger.info(f"父文档已保存: {config.DOCSTORE_PATH}（{len(self._parent_store)} 条）")

    def _load_parent_store(self):
        """从 JSON 文件加载父文档字典。"""
        with open(config.DOCSTORE_PATH, "r", encoding="utf-8") as f:
            self._parent_store = json.load(f)
        logger.info(f"父文档已加载: {config.DOCSTORE_PATH}（{len(self._parent_store)} 条）")
