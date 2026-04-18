"""
测试 RAG Pipeline 模块（混合检索版本）

使用 mock 替代实际模型加载和外部依赖：
- HuggingFaceEmbedding（避免加载真实 Embedding 模型）
- DashScope（避免 API 调用）
- Settings（避免 LlamaIndex 全局状态副作用）
- RecipeIndexer（避免真实 Qdrant 操作）
- RecipeRetriever（避免真实检索）

验证命令: .venv\\Scripts\\python.exe -m pytest tests/test_pipeline.py -v
"""

import json

import pytest
from unittest.mock import patch, MagicMock, mock_open

from src import config


# =========================================================================
# 测试数据
# =========================================================================

MOCK_PARENT_DOCS_NORMAL = [
    {
        "recipe_id": "r001",
        "text": "【红烧肉】\n主料：五花肉500g\n调料：酱油、冰糖、料酒\n做法：切块焯水后小火炖煮...",
        "metadata": {
            "title": "红烧肉",
            "category": "家常菜",
            "difficulty": 2,
            "nutrition_tags": ["高蛋白"],
        },
        "relevance": 0.85,
        "matched_chunks": 3,
    },
    {
        "recipe_id": "r002",
        "text": "【糖醋排骨】\n主料：排骨400g\n调料：醋、糖、番茄酱\n做法：排骨焯水后油炸...",
        "metadata": {
            "title": "糖醋排骨",
            "category": "家常菜",
            "difficulty": 3,
        },
        "relevance": 0.72,
        "matched_chunks": 2,
    },
]

MOCK_PARENT_DOCS_WEAK = [
    {
        "recipe_id": "r003",
        "text": "【蛋炒饭】\n主料：米饭、鸡蛋\n做法：热油翻炒...",
        "metadata": {"title": "蛋炒饭", "category": "快手菜"},
        "relevance": 0.005,
        "matched_chunks": 1,
    },
]

MOCK_ENRICHED_RECIPES = [
    {"recipe_id": "r001", "title": "红烧肉", "ingredients": ["五花肉"]},
    {"recipe_id": "r002", "title": "糖醋排骨", "ingredients": ["排骨"]},
    {"recipe_id": "r003", "title": "蛋炒饭", "ingredients": ["米饭", "鸡蛋"]},
]


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_deps():
    """Mock 所有外部依赖（模型类 + Settings），避免加载真实模型和全局状态污染"""
    with (
        patch("src.pipeline.rag_pipeline.HuggingFaceEmbedding") as mock_embed_cls,
        patch("src.pipeline.rag_pipeline.DashScope") as mock_llm_cls,
        patch("src.pipeline.rag_pipeline.Settings") as mock_settings,
    ):
        # 模拟 Embedding 模型实例
        mock_embed = MagicMock()
        mock_embed._model = MagicMock()
        mock_embed._model.prompts = {}
        mock_embed_cls.return_value = mock_embed

        # 模拟 LLM 实例
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        yield {
            "embed_cls": mock_embed_cls,
            "embed_instance": mock_embed,
            "llm_cls": mock_llm_cls,
            "llm_instance": mock_llm,
            "settings": mock_settings,
        }


@pytest.fixture
def pipeline(mock_deps):
    """创建 mock 化的 RAGPipeline 实例"""
    with patch("src.pipeline.rag_pipeline.RecipeIndexer") as mock_indexer_cls:
        mock_indexer = MagicMock()
        mock_indexer_cls.return_value = mock_indexer

        from src.pipeline.rag_pipeline import RAGPipeline

        p = RAGPipeline()

        # 存储 mock 引用，供测试断言使用
        p._mock_indexer_cls = mock_indexer_cls
        p._mock_indexer = mock_indexer
        yield p


# =========================================================================
# TestConfigureSettings: 验证 Embedding/LLM 正确初始化
# =========================================================================


class TestConfigureSettings:
    """验证 _configure_settings 正确配置了 Embedding 和 LLM"""

    def test_embedding_model_initialized(self, mock_deps):
        """验证 HuggingFaceEmbedding 使用正确参数初始化"""
        with patch("src.pipeline.rag_pipeline.RecipeIndexer"):
            from src.pipeline.rag_pipeline import RAGPipeline

            RAGPipeline()

        mock_deps["embed_cls"].assert_called_once_with(
            model_name=config.EMBEDDING_MODEL,
            device="cpu",
            max_length=config.EMBEDDING_MAX_LENGTH,
        )

    def test_qwen3_prompts_cleared(self, mock_deps):
        """验证 Qwen3-Embedding 内置英文 prompt 被清除"""
        with patch("src.pipeline.rag_pipeline.RecipeIndexer"):
            from src.pipeline.rag_pipeline import RAGPipeline

            RAGPipeline()

        assert mock_deps["embed_instance"]._model.prompts == {
            "query": "",
            "text": "",
        }

    def test_llm_initialized(self, mock_deps):
        """验证 DashScope LLM 使用正确参数初始化"""
        with patch("src.pipeline.rag_pipeline.RecipeIndexer"):
            from src.pipeline.rag_pipeline import RAGPipeline

            RAGPipeline()

        mock_deps["llm_cls"].assert_called_once_with(
            model_name=config.DASHSCOPE_MODEL,
            api_key=config.DASHSCOPE_API_KEY,
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS,
            timeout=90,
        )

    def test_indexer_receives_embed_model(self, mock_deps):
        """验证 RecipeIndexer 接收了已配置的 embedding_model"""
        with patch("src.pipeline.rag_pipeline.RecipeIndexer") as mock_cls:
            from src.pipeline.rag_pipeline import RAGPipeline

            RAGPipeline()

        # Settings.embed_model 在 _configure_settings 中被设置为 mock_embed_instance
        # RecipeIndexer 应接收 embedding_model 参数
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert "embedding_model" in call_kwargs


# =========================================================================
# TestBuildIndex: 验证 build_index 调用链
# =========================================================================


class TestBuildIndex:
    """验证 build_index 正确调用 indexer 和 retriever"""

    def test_build_index_full_chain(self, pipeline, mock_deps):
        """验证完整构建流程：加载数据 → indexer.build_index → retriever.build_bm25_index"""
        import json

        with (
            patch("builtins.open", mock_open(read_data=json.dumps(MOCK_ENRICHED_RECIPES))),
            patch("src.pipeline.rag_pipeline.RecipeRetriever") as mock_ret_cls,
        ):
            mock_retriever = MagicMock()
            mock_ret_cls.return_value = mock_retriever

            pipeline.build_index()

            # 验证 indexer.build_index 被调用（传入全部食谱，force_rebuild=True）
            pipeline._mock_indexer.build_index.assert_called_once()
            call_args = pipeline._mock_indexer.build_index.call_args
            assert len(call_args[0][0]) == 3  # 3 条食谱
            assert call_args[1]["force_rebuild"] is True

            # 验证 retriever 创建并构建 BM25
            mock_ret_cls.assert_called_once_with(pipeline._mock_indexer)
            mock_retriever.build_bm25_index.assert_called_once_with(force_rebuild=True)

    def test_build_index_with_limit(self, pipeline, mock_deps):
        """验证 limit 参数正确截断食谱数量"""
        import json

        with (
            patch("builtins.open", mock_open(read_data=json.dumps(MOCK_ENRICHED_RECIPES))),
            patch("src.pipeline.rag_pipeline.RecipeRetriever"),
        ):
            pipeline.build_index(limit=2)

            call_args = pipeline._mock_indexer.build_index.call_args
            assert len(call_args[0][0]) == 2  # 限制为 2 条

    def test_build_index_sets_retriever(self, pipeline, mock_deps):
        """验证 build_index 后 is_loaded 为 True"""
        import json

        with (
            patch("builtins.open", mock_open(read_data=json.dumps(MOCK_ENRICHED_RECIPES))),
            patch("src.pipeline.rag_pipeline.RecipeRetriever"),
        ):
            assert not pipeline.is_loaded
            pipeline.build_index()
            assert pipeline.is_loaded


# =========================================================================
# TestLoadIndex: 验证 load_index 调用链
# =========================================================================


class TestLoadIndex:
    """验证 load_index 正确加载索引和创建检索器"""

    def test_load_index_success(self, pipeline, mock_deps):
        """验证加载成功时的调用链"""
        pipeline._mock_indexer.load_index.return_value = True

        with patch("src.pipeline.rag_pipeline.RecipeRetriever") as mock_ret_cls:
            mock_retriever = MagicMock()
            mock_ret_cls.return_value = mock_retriever

            pipeline.load_index()

            # 验证调用链
            pipeline._mock_indexer.load_index.assert_called_once()
            mock_ret_cls.assert_called_once_with(pipeline._mock_indexer)
            mock_retriever.build_bm25_index.assert_called_once()

    def test_load_index_failure_raises(self, pipeline, mock_deps):
        """验证加载失败时抛出 RuntimeError"""
        pipeline._mock_indexer.load_index.return_value = False

        with pytest.raises(RuntimeError, match="索引加载失败"):
            pipeline.load_index()

    def test_load_index_sets_retriever(self, pipeline, mock_deps):
        """验证 load_index 后 is_loaded 为 True"""
        pipeline._mock_indexer.load_index.return_value = True

        with patch("src.pipeline.rag_pipeline.RecipeRetriever"):
            assert not pipeline.is_loaded
            pipeline.load_index()
            assert pipeline.is_loaded


# =========================================================================
# TestQuery: 验证查询流程
# =========================================================================


class TestQuery:
    """验证 RAG 查询的各种场景"""

    def test_normal_query(self, pipeline, mock_deps):
        """正常检索 → QA prompt → LLM 返回结构化结果"""
        # 设置已加载的检索器
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = MOCK_PARENT_DOCS_NORMAL
        pipeline._retriever = mock_retriever

        # Settings.llm 在 init 中已被 _configure_settings 设为 mock_llm_instance
        mock_response = MagicMock()
        mock_response.message.content = "推荐您试试红烧肉和糖醋排骨..."
        mock_deps["settings"].llm.chat.return_value = mock_response

        result = pipeline.query("家常红烧肉怎么做？")

        # 验证返回结构
        assert result["answer"] == "推荐您试试红烧肉和糖醋排骨..."
        assert result["query"] == "家常红烧肉怎么做？"
        assert result["filters"] is None
        assert len(result["sources"]) == 2

        # 验证来源信息
        assert result["sources"][0]["recipe_id"] == "r001"
        assert result["sources"][0]["title"] == "红烧肉"
        assert result["sources"][0]["relevance"] == 0.85
        assert result["sources"][0]["matched_chunks"] == 3
        assert "title" in result["sources"][0]["metadata"]

    def test_weak_result_uses_weak_prompt(self, pipeline, mock_deps):
        """弱结果检索（relevance < 0.01）→ 使用 build_weak_result_prompt"""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = MOCK_PARENT_DOCS_WEAK
        pipeline._retriever = mock_retriever

        mock_response = MagicMock()
        mock_response.message.content = "检索结果相关性不高，建议您..."
        mock_deps["settings"].llm.chat.return_value = mock_response

        with (
            patch("src.pipeline.rag_pipeline.build_weak_result_prompt") as mock_weak_fn,
            patch("src.pipeline.rag_pipeline.build_qa_prompt") as mock_qa_fn,
        ):
            mock_weak_fn.return_value = "弱结果 Prompt 内容"

            result = pipeline.query("高端分子料理怎么做？")

            # 验证使用了弱结果 Prompt
            mock_weak_fn.assert_called_once()
            mock_qa_fn.assert_not_called()

        assert result["answer"] == "检索结果相关性不高，建议您..."

    def test_empty_result_no_llm_call(self, pipeline, mock_deps):
        """空检索结果 → 直接返回默认回答，不调用 LLM"""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        pipeline._retriever = mock_retriever

        # 重置 LLM mock 调用记录（init 中可能有间接调用）
        mock_deps["settings"].llm.chat.reset_mock()

        result = pipeline.query("完全不相关的查询")

        # 验证不调用 LLM
        mock_deps["settings"].llm.chat.assert_not_called()

        # 验证返回结构
        assert "未找到" in result["answer"]
        assert result["sources"] == []
        assert result["query"] == "完全不相关的查询"
        assert result["filters"] is None

    def test_query_with_filters(self, pipeline, mock_deps):
        """带 filters 的查询正确传递过滤条件"""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = MOCK_PARENT_DOCS_NORMAL
        pipeline._retriever = mock_retriever

        mock_response = MagicMock()
        mock_response.message.content = "低脂家常菜推荐..."
        mock_deps["settings"].llm.chat.return_value = mock_response

        filters = {"nutrition_tags": ["低脂"], "exclude_ingredients": ["花生"]}

        result = pipeline.query("推荐低脂菜谱", filters=filters)

        # 验证 filters 正确传递给 retriever
        mock_retriever.retrieve.assert_called_once_with(
            query="推荐低脂菜谱",
            top_k=config.TOP_K,
            filters=filters,
        )

        # 验证返回结构包含 filters
        assert result["filters"] == filters
        assert result["answer"] == "低脂家常菜推荐..."

    def test_query_not_loaded_raises(self, pipeline, mock_deps):
        """未加载索引时调用 query 应抛出 RuntimeError"""
        assert pipeline._retriever is None

        with pytest.raises(RuntimeError, match="索引未加载"):
            pipeline.query("任何问题")

    def test_normal_result_uses_qa_prompt(self, pipeline, mock_deps):
        """正常结果（relevance >= 0.01）→ 使用 build_qa_prompt"""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = MOCK_PARENT_DOCS_NORMAL
        pipeline._retriever = mock_retriever

        mock_response = MagicMock()
        mock_response.message.content = "QA 推荐..."
        mock_deps["settings"].llm.chat.return_value = mock_response

        with (
            patch("src.pipeline.rag_pipeline.build_qa_prompt") as mock_qa_fn,
            patch("src.pipeline.rag_pipeline.build_weak_result_prompt") as mock_weak_fn,
        ):
            mock_qa_fn.return_value = "QA Prompt 内容"

            pipeline.query("做红烧肉")

            # 验证使用了 QA Prompt
            mock_qa_fn.assert_called_once()
            mock_weak_fn.assert_not_called()


# =========================================================================
# TestIsLoaded: 属性测试
# =========================================================================


class TestIsLoaded:
    """验证 is_loaded 属性在不同状态下的行为"""

    def test_not_loaded_initially(self, pipeline):
        """初始化后 is_loaded 应为 False"""
        assert pipeline.is_loaded is False

    def test_loaded_when_retriever_exists(self, pipeline):
        """设置 retriever 后 is_loaded 应为 True"""
        pipeline._retriever = MagicMock()
        assert pipeline.is_loaded is True

    def test_not_loaded_when_retriever_none(self, pipeline):
        """retriever 为 None 时 is_loaded 应为 False"""
        pipeline._retriever = None
        assert pipeline.is_loaded is False
