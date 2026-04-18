"""
索引构建器模块（indexer）单元测试

测试内容：
1. 子块 → TextNode 转换正确性（id、text、metadata）
2. 元数据过滤逻辑（移除嵌套 dict/list of dict）
3. 父文档持久化与加载
4. get_parent_text / get_parent_metadata 查找
5. 小批量索引构建（mock embedding 模型）
6. 增量检查逻辑（跳过 / 强制重建）
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from llama_index.core.schema import TextNode

from src.pipeline.indexer import (
    RecipeIndexer,
    _filter_child_metadata,
    _child_to_text_node,
    _METADATA_EXCLUDE_KEYS,
)


# =========================================================================
# 测试辅助：构造 mock 食谱数据
# =========================================================================

def _make_recipe(**overrides) -> dict:
    """构造一条完整的测试食谱，可通过 overrides 覆盖任意字段。"""
    base = {
        "did": "12345",
        "title": "红烧肉",
        "zid": "家常菜",
        "tags": ["家常菜", "肉类"],
        "desc": "经典中华美食",
        "difficulty": 2,
        "costtime": "30-60分钟",
        "tip": "小火慢炖",
        "ingredients_raw": ["五花肉", "生姜", "大葱", "八角", "桂皮"],
        "ingredients_clean": ["五花肉", "生姜", "大葱", "八角", "桂皮"],
        "quantities": ["500g", "3片", "2段", "2个", "1小段"],
        "has_quantity": True,
        "ingredient_count": 5,
        "steps": ["1. 五花肉切块", "2. 焯水去腥", "3. 炒糖色"],
        "step_count": 3,
        "step_pics": ["http://pic1.jpg", "http://pic2.jpg"],
        "thumb": "http://thumb.jpg",
        "videourl": "http://video.mp4",
        "viewnum": 12000,
        "favnum": 800,
        "ingredient_nutrition": [
            {
                "name": "五花肉", "matched_name": "猪肉(肥瘦)",
                "energy": 395.0, "protein": 13.2, "fat": 37.0, "carbs": 2.4,
                "match_score": 90, "match_type": "contains",
            },
            {
                "name": "生姜", "matched_name": "姜",
                "energy": 41.0, "protein": 1.3, "fat": 0.6, "carbs": 9.0,
                "match_score": 100, "match_type": "alias",
            },
        ],
        "nutrition_coverage": 0.85,
        "nutrition_summary": {"energy": 218.0, "protein": 7.3, "fat": 18.8, "carbs": 5.7},
        "nutrition_tags": ["高蛋白"],
        "nutrition_confidence": "high",
    }
    base.update(overrides)
    return base


def _make_child_dict(chunk_type: str = "info", recipe_id: str = "12345") -> dict:
    """构造一个子块字典（模拟 document_builder 的输出）。"""
    return {
        "text": f"红烧肉的{chunk_type}子块文本",
        "chunk_type": chunk_type,
        "metadata": {
            "recipe_id": recipe_id,
            "title": "红烧肉",
            "category": "家常菜",
            "tags": ["家常菜", "肉类"],
            "difficulty": 2,
            "difficulty_text": "较难",
            "costtime": "30-60分钟",
            "costtime_minutes": 45,
            "ingredient_count": 5,
            "main_ingredients": ["五花肉", "生姜", "大葱"],
            "viewnum": 12000,
            "favnum": 800,
            "nutrition_coverage": 0.85,
            "nutrition_tags": ["高蛋白"],
            "nutrition_confidence": "high",
            "has_video": True,
            "thumb": "http://thumb.jpg",
            "chunk_type": chunk_type,
            # 以下字段应被过滤
            "ingredient_nutrition": [{"name": "五花肉", "energy": 395.0}],
            "nutrition_summary": {"energy": 218.0, "protein": 7.3},
            "step_pics": ["http://pic1.jpg", "http://pic2.jpg"],
        },
    }


# =========================================================================
# 一、元数据过滤测试
# =========================================================================

class TestFilterChildMetadata:
    """测试子块元数据过滤逻辑。"""

    def test_removes_ingredient_nutrition(self):
        """应移除 ingredient_nutrition（list[dict]）。"""
        meta = {"recipe_id": "1", "ingredient_nutrition": [{"name": "肉"}]}
        result = _filter_child_metadata(meta)
        assert "ingredient_nutrition" not in result

    def test_removes_nutrition_summary(self):
        """应移除 nutrition_summary（dict）。"""
        meta = {"recipe_id": "1", "nutrition_summary": {"energy": 100}}
        result = _filter_child_metadata(meta)
        assert "nutrition_summary" not in result

    def test_removes_step_pics(self):
        """应移除 step_pics。"""
        meta = {"recipe_id": "1", "step_pics": ["http://pic1.jpg"]}
        result = _filter_child_metadata(meta)
        assert "step_pics" not in result

    def test_keeps_tags(self):
        """应保留 tags（list[str]）。"""
        meta = {"tags": ["家常菜", "肉类"]}
        result = _filter_child_metadata(meta)
        assert result["tags"] == ["家常菜", "肉类"]

    def test_keeps_main_ingredients(self):
        """应保留 main_ingredients（list[str]）。"""
        meta = {"main_ingredients": ["五花肉", "生姜"]}
        result = _filter_child_metadata(meta)
        assert result["main_ingredients"] == ["五花肉", "生姜"]

    def test_keeps_nutrition_tags(self):
        """应保留 nutrition_tags（list[str]）。"""
        meta = {"nutrition_tags": ["高蛋白"]}
        result = _filter_child_metadata(meta)
        assert result["nutrition_tags"] == ["高蛋白"]

    def test_keeps_scalar_fields(self):
        """应保留标量字段。"""
        meta = {
            "recipe_id": "12345",
            "title": "红烧肉",
            "difficulty": 2,
            "viewnum": 12000,
            "has_video": True,
        }
        result = _filter_child_metadata(meta)
        assert result == meta

    def test_full_metadata_filtering(self):
        """完整元数据过滤：排除键集合应正好为 _METADATA_EXCLUDE_KEYS。"""
        child = _make_child_dict()
        original_keys = set(child["metadata"].keys())
        result = _filter_child_metadata(child["metadata"])
        removed = original_keys - set(result.keys())
        assert removed == _METADATA_EXCLUDE_KEYS


# =========================================================================
# 二、TextNode 转换测试
# =========================================================================

class TestChildToTextNode:
    """测试子块 → TextNode 转换。"""

    def test_node_id_format(self):
        """node.id_ 应为合法 UUID（从 recipe_id + chunk_type 确定性生成）。"""
        import uuid
        child = _make_child_dict(chunk_type="info", recipe_id="12345")
        node = _child_to_text_node(child, "12345")
        # 验证是合法 UUID
        parsed = uuid.UUID(node.id_)
        assert str(parsed) == node.id_
        # 验证 chunk_id 保留在 metadata 中
        assert node.metadata["chunk_id"] == "12345_info"

    def test_node_text(self):
        """node.text 应为子块文本。"""
        child = _make_child_dict(chunk_type="ingredient")
        node = _child_to_text_node(child, "12345")
        assert node.text == "红烧肉的ingredient子块文本"

    def test_node_metadata_filtered(self):
        """node.metadata 应已过滤嵌套字段。"""
        child = _make_child_dict()
        node = _child_to_text_node(child, "12345")
        assert "ingredient_nutrition" not in node.metadata
        assert "nutrition_summary" not in node.metadata
        assert "step_pics" not in node.metadata

    def test_node_metadata_has_required_fields(self):
        """node.metadata 应包含所有必需的非嵌套字段。"""
        child = _make_child_dict()
        node = _child_to_text_node(child, "12345")
        required = {"recipe_id", "title", "category", "tags", "difficulty",
                     "chunk_type", "viewnum", "favnum", "nutrition_tags", "chunk_id"}
        assert required.issubset(set(node.metadata.keys()))

    def test_excluded_embed_metadata_keys(self):
        """所有 metadata key 都应排除在 embedding 之外。"""
        child = _make_child_dict()
        node = _child_to_text_node(child, "12345")
        meta_keys = set(node.metadata.keys())
        excluded = set(node.excluded_embed_metadata_keys)
        assert meta_keys == excluded

    def test_excluded_llm_metadata_keys(self):
        """所有 metadata key 都应排除在 LLM 上下文之外。"""
        child = _make_child_dict()
        node = _child_to_text_node(child, "12345")
        meta_keys = set(node.metadata.keys())
        excluded = set(node.excluded_llm_metadata_keys)
        assert meta_keys == excluded

    def test_different_chunk_types(self):
        """三种子块类型的 node id 各不相同。"""
        ids = set()
        for ct in ("info", "ingredient", "step"):
            child = _make_child_dict(chunk_type=ct)
            node = _child_to_text_node(child, "12345")
            ids.add(node.id_)
        assert len(ids) == 3

    def test_is_text_node_instance(self):
        """返回值应为 TextNode 实例。"""
        child = _make_child_dict()
        node = _child_to_text_node(child, "12345")
        assert isinstance(node, TextNode)


# =========================================================================
# 三、父文档持久化测试
# =========================================================================

class TestParentStorePersistence:
    """测试父文档的保存与加载。"""

    def test_save_and_load(self, tmp_path):
        """保存后重新加载，数据应一致。"""
        docstore_path = str(tmp_path / "parent_docstore.json")

        indexer = RecipeIndexer()
        indexer._parent_store = {
            "12345": {
                "text": "红烧肉的完整文本",
                "metadata": {"recipe_id": "12345", "title": "红烧肉"},
            },
            "67890": {
                "text": "番茄炒蛋的完整文本",
                "metadata": {"recipe_id": "67890", "title": "番茄炒蛋"},
            },
        }

        # 保存
        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.DOCSTORE_PATH = docstore_path
            indexer._save_parent_store()

        # 验证文件存在
        assert (tmp_path / "parent_docstore.json").exists()

        # 加载到新实例
        indexer2 = RecipeIndexer()
        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.DOCSTORE_PATH = docstore_path
            indexer2._load_parent_store()

        assert len(indexer2._parent_store) == 2
        assert indexer2._parent_store["12345"]["text"] == "红烧肉的完整文本"
        assert indexer2._parent_store["67890"]["metadata"]["title"] == "番茄炒蛋"

    def test_save_utf8_encoding(self, tmp_path):
        """保存的 JSON 应使用 UTF-8 编码，中文不转义。"""
        docstore_path = str(tmp_path / "test_store.json")

        indexer = RecipeIndexer()
        indexer._parent_store = {
            "1": {"text": "中文测试", "metadata": {"title": "红烧肉"}},
        }

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.DOCSTORE_PATH = docstore_path
            indexer._save_parent_store()

        raw_content = (tmp_path / "test_store.json").read_text(encoding="utf-8")
        assert "中文测试" in raw_content
        assert "红烧肉" in raw_content
        # 确认不是 unicode escape
        assert "\\u" not in raw_content


# =========================================================================
# 四、get_parent_text / get_parent_metadata 测试
# =========================================================================

class TestGetParent:
    """测试父文档查找接口。"""

    def setup_method(self):
        """每个测试前创建带数据的 indexer。"""
        self.indexer = RecipeIndexer()
        self.indexer._parent_store = {
            "12345": {
                "text": "【红烧肉】\n分类：家常菜...",
                "metadata": {
                    "recipe_id": "12345",
                    "title": "红烧肉",
                    "tags": ["家常菜"],
                    "nutrition_summary": {"energy": 218.0},
                },
            },
        }

    def test_get_parent_text_existing(self):
        """存在的 recipe_id 应返回父文档文本。"""
        text = self.indexer.get_parent_text("12345")
        assert text is not None
        assert "红烧肉" in text

    def test_get_parent_text_missing(self):
        """不存在的 recipe_id 应返回 None。"""
        assert self.indexer.get_parent_text("99999") is None

    def test_get_parent_metadata_existing(self):
        """存在的 recipe_id 应返回父文档元数据。"""
        meta = self.indexer.get_parent_metadata("12345")
        assert meta is not None
        assert meta["title"] == "红烧肉"
        assert meta["recipe_id"] == "12345"

    def test_get_parent_metadata_missing(self):
        """不存在的 recipe_id 应返回 None。"""
        assert self.indexer.get_parent_metadata("99999") is None

    def test_parent_metadata_has_nested_fields(self):
        """父文档元数据应保留嵌套字段（不过滤）。"""
        meta = self.indexer.get_parent_metadata("12345")
        assert "nutrition_summary" in meta


# =========================================================================
# 五、小批量构建测试（mock Embedding）
# =========================================================================

class TestBuildIndex:
    """测试索引构建流程（使用 mock 避免加载真实模型）。"""

    @patch("src.pipeline.indexer.VectorStoreIndex")
    @patch("src.pipeline.indexer.QdrantClient")
    def test_build_creates_text_nodes(self, MockQdrantClient, MockVectorStoreIndex, tmp_path):
        """构建索引时应正确创建 TextNode。"""
        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = False
        mock_client.count.return_value = MagicMock(count=6)

        docstore_path = str(tmp_path / "parent_docstore.json")

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(tmp_path / "qdrant_db")
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer(embedding_model=MagicMock())
            # 跳过真实的 Settings 赋值
            indexer._setup_embedding = MagicMock()
            recipes = [_make_recipe(), _make_recipe(did="67890", title="番茄炒蛋")]
            result = indexer.build_index(recipes, force_rebuild=True)

        assert result["child_count"] == 6  # 2 食谱 × 3 子块
        assert result["parent_count"] == 2
        assert result["qdrant_count"] == 6

        # 验证 VectorStoreIndex 被调用时传入了正确数量的 nodes
        call_kwargs = MockVectorStoreIndex.call_args
        nodes_passed = call_kwargs.kwargs.get("nodes") or call_kwargs[1].get("nodes")
        assert len(nodes_passed) == 6

    @patch("src.pipeline.indexer.VectorStoreIndex")
    @patch("src.pipeline.indexer.QdrantClient")
    def test_build_saves_parent_store(self, MockQdrantClient, MockVectorStoreIndex, tmp_path):
        """构建索引后应持久化父文档。"""
        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = False
        mock_client.count.return_value = MagicMock(count=3)

        docstore_path = str(tmp_path / "parent_docstore.json")

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(tmp_path / "qdrant_db")
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer(embedding_model=MagicMock())
            indexer._setup_embedding = MagicMock()
            indexer.build_index([_make_recipe()], force_rebuild=True)

        assert (tmp_path / "parent_docstore.json").exists()
        with open(docstore_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "12345" in data
        assert data["12345"]["metadata"]["title"] == "红烧肉"

    @patch("src.pipeline.indexer.VectorStoreIndex")
    @patch("src.pipeline.indexer.QdrantClient")
    def test_build_node_ids_unique(self, MockQdrantClient, MockVectorStoreIndex, tmp_path):
        """不同食谱的子块 node id 应全局唯一。"""
        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = False
        mock_client.count.return_value = MagicMock(count=6)

        docstore_path = str(tmp_path / "parent_docstore.json")

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(tmp_path / "qdrant_db")
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer(embedding_model=MagicMock())
            indexer._setup_embedding = MagicMock()
            recipes = [_make_recipe(), _make_recipe(did="67890", title="番茄炒蛋")]
            indexer.build_index(recipes, force_rebuild=True)

        call_kwargs = MockVectorStoreIndex.call_args
        nodes_passed = call_kwargs.kwargs.get("nodes") or call_kwargs[1].get("nodes")
        ids = [n.id_ for n in nodes_passed]
        assert len(ids) == len(set(ids)), f"发现重复 ID: {ids}"

    @patch("src.pipeline.indexer.VectorStoreIndex")
    @patch("src.pipeline.indexer.QdrantClient")
    def test_build_text_node_metadata_clean(self, MockQdrantClient, MockVectorStoreIndex, tmp_path):
        """写入 Qdrant 的 TextNode 元数据应不含嵌套结构。"""
        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = False
        mock_client.count.return_value = MagicMock(count=3)

        docstore_path = str(tmp_path / "parent_docstore.json")

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(tmp_path / "qdrant_db")
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer(embedding_model=MagicMock())
            indexer._setup_embedding = MagicMock()
            indexer.build_index([_make_recipe()], force_rebuild=True)

        call_kwargs = MockVectorStoreIndex.call_args
        nodes_passed = call_kwargs.kwargs.get("nodes") or call_kwargs[1].get("nodes")
        for node in nodes_passed:
            assert "ingredient_nutrition" not in node.metadata
            assert "nutrition_summary" not in node.metadata
            assert "step_pics" not in node.metadata


# =========================================================================
# 六、增量检查测试
# =========================================================================

class TestIncrementalCheck:
    """测试增量检查逻辑（已有数据时跳过/强制重建）。"""

    @patch("src.pipeline.indexer.VectorStoreIndex")
    @patch("src.pipeline.indexer.QdrantClient")
    def test_skip_when_data_exists(self, MockQdrantClient, MockVectorStoreIndex, tmp_path):
        """不强制重建时，已有数据应跳过构建。"""
        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = True
        mock_client.count.return_value = MagicMock(count=100)

        docstore_path = str(tmp_path / "parent_docstore.json")
        # 创建一个已有的父文档文件
        with open(docstore_path, "w", encoding="utf-8") as f:
            json.dump({"11111": {"text": "旧数据", "metadata": {}}}, f)

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(tmp_path / "qdrant_db")
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer()
            result = indexer.build_index([_make_recipe()], force_rebuild=False)

        # 应跳过构建，child_count 为 0
        assert result["child_count"] == 0
        assert result["qdrant_count"] == 100
        # VectorStoreIndex 不应被调用
        MockVectorStoreIndex.assert_not_called()

    @patch("src.pipeline.indexer.VectorStoreIndex")
    @patch("src.pipeline.indexer.QdrantClient")
    def test_force_rebuild_deletes_old(self, MockQdrantClient, MockVectorStoreIndex, tmp_path):
        """强制重建时应删除旧 collection。"""
        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = True
        mock_client.count.return_value = MagicMock(count=3)

        docstore_path = str(tmp_path / "parent_docstore.json")

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(tmp_path / "qdrant_db")
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer(embedding_model=MagicMock())
            indexer._setup_embedding = MagicMock()
            indexer.build_index([_make_recipe()], force_rebuild=True)

        # 应调用 delete_collection
        mock_client.delete_collection.assert_called_once_with("test_collection")


# =========================================================================
# 七、load_index 测试
# =========================================================================

class TestLoadIndex:
    """测试索引加载逻辑。"""

    @patch("src.pipeline.indexer.QdrantClient")
    def test_load_fails_without_qdrant_dir(self, MockQdrantClient, tmp_path):
        """Qdrant 目录不存在时应返回 False。"""
        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(tmp_path / "nonexistent_dir")
            mock_config.DOCSTORE_PATH = str(tmp_path / "nonexistent.json")

            indexer = RecipeIndexer()
            assert indexer.load_index() is False

    @patch("src.pipeline.indexer.QdrantClient")
    def test_load_fails_without_docstore(self, MockQdrantClient, tmp_path):
        """父文档文件不存在时应返回 False。"""
        qdrant_dir = tmp_path / "qdrant_db"
        qdrant_dir.mkdir()

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(qdrant_dir)
            mock_config.DOCSTORE_PATH = str(tmp_path / "nonexistent.json")

            indexer = RecipeIndexer()
            assert indexer.load_index() is False

    @patch("src.pipeline.indexer.QdrantClient")
    def test_load_success(self, MockQdrantClient, tmp_path):
        """正常情况下应加载成功。"""
        qdrant_dir = tmp_path / "qdrant_db"
        qdrant_dir.mkdir()

        docstore_path = str(tmp_path / "parent_docstore.json")
        with open(docstore_path, "w", encoding="utf-8") as f:
            json.dump({"12345": {"text": "红烧肉", "metadata": {"title": "红烧肉"}}}, f)

        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = True
        mock_client.count.return_value = MagicMock(count=50)

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(qdrant_dir)
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer()
            assert indexer.load_index() is True

        # 加载后应能查找父文档
        assert indexer.get_parent_text("12345") == "红烧肉"

    @patch("src.pipeline.indexer.QdrantClient")
    def test_load_fails_empty_collection(self, MockQdrantClient, tmp_path):
        """Qdrant collection 为空时应返回 False。"""
        qdrant_dir = tmp_path / "qdrant_db"
        qdrant_dir.mkdir()

        docstore_path = str(tmp_path / "parent_docstore.json")
        with open(docstore_path, "w", encoding="utf-8") as f:
            json.dump({}, f)

        mock_client = MockQdrantClient.return_value
        mock_client.collection_exists.return_value = True
        mock_client.count.return_value = MagicMock(count=0)

        with patch("src.pipeline.indexer.config") as mock_config:
            mock_config.QDRANT_PATH = str(qdrant_dir)
            mock_config.DOCSTORE_PATH = docstore_path
            mock_config.QDRANT_COLLECTION_NAME = "test_collection"

            indexer = RecipeIndexer()
            assert indexer.load_index() is False


# =========================================================================
# 八、属性访问测试
# =========================================================================

class TestProperties:
    """测试 property 访问。"""

    def test_vector_store_initially_none(self):
        indexer = RecipeIndexer()
        assert indexer.vector_store is None

    def test_qdrant_client_initially_none(self):
        indexer = RecipeIndexer()
        assert indexer.qdrant_client is None

    def test_parent_store_initially_empty(self):
        indexer = RecipeIndexer()
        assert indexer.parent_store == {}
