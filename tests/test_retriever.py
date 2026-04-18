"""
混合检索器模块（retriever）单元测试

测试内容：
1. BM25 索引构建：jieba 分词、BM25 索引创建、查询返回结果
2. RRF 融合：两路结果正确合并，得分计算正确
3. 元数据过滤：各种 filter 条件正确过滤
4. 父文档聚合去重：
   - 匹配多子块的食谱得分更高
   - 结果按相关性降序
   - 每个食谱只出现一次
   - top_k 截断正确
5. retrieve 完整流程（使用 mock）
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.pipeline.retriever import (
    RecipeRetriever,
    rrf_fuse,
    apply_metadata_filters,
    aggregate_parents,
    _parse_recipe_id,
    _passes_filters,
    _build_qdrant_filter,
    _has_elastic_constraints,
    _passes_elastic_constraints,
    _compute_elastic_bonus,
    _compute_soft_bonus,
    MIN_ELASTIC_RESULTS,
)


# =========================================================================
# 测试辅助：构造 mock 数据
# =========================================================================


def _make_parent_store():
    """构造一个小型 parent_store，包含 3 个食谱。"""
    return {
        "R001": {
            "text": "红烧肉是经典家常菜，主要用五花肉、生姜、大葱炖煮而成，口感软糯鲜美",
            "metadata": {
                "recipe_id": "R001",
                "title": "红烧肉",
                "category": "家常菜",
                "tags": ["家常菜", "肉类"],
                "difficulty": 2,
                "costtime_minutes": 45,
                "main_ingredients": ["五花肉", "生姜", "大葱"],
                "nutrition_tags": ["高蛋白"],
            },
        },
        "R002": {
            "text": "清蒸鲈鱼是一道粤菜，鲈鱼蒸好后淋上热油和蒸鱼豉油，鲜嫩可口",
            "metadata": {
                "recipe_id": "R002",
                "title": "清蒸鲈鱼",
                "category": "粤菜",
                "tags": ["粤菜", "鱼类"],
                "difficulty": 1,
                "costtime_minutes": 20,
                "main_ingredients": ["鲈鱼", "生姜", "葱丝"],
                "nutrition_tags": ["高蛋白", "低脂"],
            },
        },
        "R003": {
            "text": "宫保鸡丁用鸡胸肉切丁，配花生米和干辣椒炒制，麻辣鲜香",
            "metadata": {
                "recipe_id": "R003",
                "title": "宫保鸡丁",
                "category": "川菜",
                "tags": ["川菜", "鸡肉"],
                "difficulty": 3,
                "costtime_minutes": 30,
                "main_ingredients": ["鸡胸肉", "花生", "干辣椒"],
                "nutrition_tags": ["高蛋白"],
            },
        },
    }


def _make_mock_indexer(parent_store=None):
    """构造一个 mock RecipeIndexer。"""
    if parent_store is None:
        parent_store = _make_parent_store()

    indexer = MagicMock()
    type(indexer).parent_store = PropertyMock(return_value=parent_store)

    def get_parent_text(recipe_id):
        entry = parent_store.get(recipe_id)
        return entry["text"] if entry else None

    def get_parent_metadata(recipe_id):
        entry = parent_store.get(recipe_id)
        return entry["metadata"] if entry else None

    indexer.get_parent_text = MagicMock(side_effect=get_parent_text)
    indexer.get_parent_metadata = MagicMock(side_effect=get_parent_metadata)
    indexer.qdrant_client = None  # 默认无 Qdrant
    indexer.vector_store = None

    return indexer


def _make_chunks(recipe_id, score, metadata=None):
    """构造一个食谱对应的多个子块结果。"""
    chunk_types = ["info", "ingredient", "step"]
    chunks = []
    for i, ct in enumerate(chunk_types):
        chunks.append({
            "node_id": f"{recipe_id}_{ct}",
            "score": score - i * 0.01,  # 略微递减
            "metadata": metadata or {},
            "recipe_id": recipe_id,
        })
    return chunks


# =========================================================================
# 1. 测试 _parse_recipe_id
# =========================================================================


class TestParseRecipeId:
    """测试从 node_id 解析 recipe_id。"""

    def test_info_suffix(self):
        assert _parse_recipe_id("12345_info") == "12345"

    def test_ingredient_suffix(self):
        assert _parse_recipe_id("R001_ingredient") == "R001"

    def test_step_suffix(self):
        assert _parse_recipe_id("abc_def_step") == "abc_def"

    def test_no_known_suffix(self):
        assert _parse_recipe_id("xyz_unknown") == "xyz"

    def test_no_underscore(self):
        assert _parse_recipe_id("nounderscore") == "nounderscore"


# =========================================================================
# 2. 测试 BM25 索引构建与检索
# =========================================================================


class TestBM25Index:
    """测试 BM25 索引的构建、缓存和检索功能。"""

    def test_build_bm25_index(self):
        """构建 BM25 索引后，内部状态应正确设置。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)

        # 不使用缓存，强制构建
        retriever.build_bm25_index(force_rebuild=True)

        assert retriever._bm25 is not None
        # 3 个食谱 × 3 个子块 = 9 个文档
        assert len(retriever._bm25_corpus) == 9
        assert len(retriever._bm25_id_map) == 9

    def test_bm25_retrieve_returns_results(self):
        """BM25 检索应能返回相关结果。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        results = retriever._bm25_retrieve("红烧肉 五花肉", top_k=5)

        assert len(results) > 0
        # 结果中应有 R001 的子块
        recipe_ids = {r["recipe_id"] for r in results}
        assert "R001" in recipe_ids

    def test_bm25_retrieve_normalized_scores(self):
        """BM25 返回的得分应在 [0, 1] 范围内。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        results = retriever._bm25_retrieve("红烧肉", top_k=10)

        for r in results:
            assert 0 <= r["score"] <= 1.0

    def test_bm25_retrieve_no_index(self):
        """BM25 未构建时检索应返回空列表。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)

        results = retriever._bm25_retrieve("红烧肉", top_k=5)
        assert results == []

    def test_bm25_cache_save_and_load(self, tmp_path):
        """BM25 缓存的保存和加载应保持一致。"""
        parent_store = _make_parent_store()
        indexer = _make_mock_indexer(parent_store)
        retriever = RecipeRetriever(indexer)

        # 构建并保存缓存
        cache_path = tmp_path / "bm25_cache.json"
        retriever.build_bm25_index(force_rebuild=True)
        retriever._save_bm25_cache(cache_path)

        assert cache_path.exists()

        # 验证缓存内容
        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        assert "corpus" in cache_data
        assert "id_map" in cache_data
        assert len(cache_data["corpus"]) == len(cache_data["id_map"])

        # 重新加载
        retriever2 = RecipeRetriever(indexer)
        success = retriever2._load_bm25_cache(cache_path)
        assert success
        assert retriever2._bm25 is not None
        assert len(retriever2._bm25_id_map) == len(retriever._bm25_id_map)

    def test_bm25_empty_parent_store(self):
        """空 parent_store 时构建 BM25 索引不应报错。"""
        indexer = _make_mock_indexer({})
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        assert retriever._bm25 is None


# =========================================================================
# 3. 测试 RRF 融合
# =========================================================================


class TestRRFFusion:
    """测试 RRF 融合算法。"""

    def test_basic_fusion(self):
        """两路结果正确融合，得分正确计算。"""
        dense = [
            {"node_id": "A_info", "score": 0.9, "metadata": {}, "recipe_id": "A"},
            {"node_id": "B_info", "score": 0.8, "metadata": {}, "recipe_id": "B"},
            {"node_id": "C_info", "score": 0.7, "metadata": {}, "recipe_id": "C"},
        ]
        bm25 = [
            {"node_id": "B_info", "score": 1.0, "metadata": {}, "recipe_id": "B"},
            {"node_id": "D_info", "score": 0.8, "metadata": {}, "recipe_id": "D"},
            {"node_id": "A_info", "score": 0.6, "metadata": {}, "recipe_id": "A"},
        ]

        fused = rrf_fuse(dense, bm25, k=60)

        # 所有唯一 node_id 都应出现
        node_ids = [item["node_id"] for item in fused]
        assert set(node_ids) == {"A_info", "B_info", "C_info", "D_info"}

    def test_overlapping_items_rank_higher(self):
        """同时出现在两路结果中的项目应获得更高的 RRF 得分。"""
        dense = [
            {"node_id": "A_info", "score": 0.9, "metadata": {}, "recipe_id": "A"},
            {"node_id": "B_info", "score": 0.8, "metadata": {}, "recipe_id": "B"},
        ]
        bm25 = [
            {"node_id": "A_info", "score": 1.0, "metadata": {}, "recipe_id": "A"},
            {"node_id": "C_info", "score": 0.8, "metadata": {}, "recipe_id": "C"},
        ]

        fused = rrf_fuse(dense, bm25, k=60)

        # A 出现在两路中，应排第一
        assert fused[0]["node_id"] == "A_info"

        # A 的得分 = 1/(60+1) + 1/(60+1) = 2/61
        # B 的得分 = 1/(60+2)
        # C 的得分 = 1/(60+2)
        expected_a = 1.0 / 61 + 1.0 / 61
        assert abs(fused[0]["score"] - expected_a) < 1e-6

    def test_empty_inputs(self):
        """空输入应返回空列表。"""
        assert rrf_fuse([], []) == []

    def test_single_source(self):
        """只有一路结果时也能正常工作。"""
        dense = [
            {"node_id": "A_info", "score": 0.9, "metadata": {}, "recipe_id": "A"},
        ]

        fused = rrf_fuse(dense, [])
        assert len(fused) == 1
        assert fused[0]["node_id"] == "A_info"

    def test_rrf_score_descending(self):
        """融合后结果应按 RRF 得分降序排列。"""
        dense = [
            {"node_id": "A_info", "score": 0.9, "metadata": {}, "recipe_id": "A"},
            {"node_id": "B_info", "score": 0.8, "metadata": {}, "recipe_id": "B"},
            {"node_id": "C_info", "score": 0.7, "metadata": {}, "recipe_id": "C"},
        ]
        bm25 = [
            {"node_id": "C_info", "score": 1.0, "metadata": {}, "recipe_id": "C"},
            {"node_id": "A_info", "score": 0.5, "metadata": {}, "recipe_id": "A"},
        ]

        fused = rrf_fuse(dense, bm25, k=60)

        for i in range(len(fused) - 1):
            assert fused[i]["score"] >= fused[i + 1]["score"]


# =========================================================================
# 4. 测试元数据过滤
# =========================================================================


class TestMetadataFilters:
    """测试元数据过滤功能。"""

    def _make_chunk(self, recipe_id="R001", **meta_overrides):
        """构造单个子块用于过滤测试。"""
        meta = {
            "recipe_id": recipe_id,
            "category": "家常菜",
            "tags": ["家常菜", "快手菜"],
            "difficulty": 2,
            "costtime_minutes": 45,
            "main_ingredients": ["五花肉", "生姜", "大葱"],
            "nutrition_tags": ["高蛋白"],
        }
        meta.update(meta_overrides)
        return {
            "node_id": f"{recipe_id}_info",
            "score": 0.9,
            "metadata": meta,
            "recipe_id": recipe_id,
        }

    def test_nutrition_tags_pass(self):
        """匹配营养标签的子块应通过。"""
        chunk = self._make_chunk(nutrition_tags=["高蛋白", "低脂"])
        result = apply_metadata_filters([chunk], {"nutrition_tags": ["低脂"]})
        assert len(result) == 1

    def test_nutrition_tags_fail(self):
        """不匹配营养标签的子块应被过滤。"""
        chunk = self._make_chunk(nutrition_tags=["高蛋白"])
        result = apply_metadata_filters([chunk], {"nutrition_tags": ["低脂"]})
        assert len(result) == 0

    def test_exclude_ingredients_pass(self):
        """不含排除食材的子块应通过。"""
        chunk = self._make_chunk(main_ingredients=["鸡胸肉", "青椒"])
        result = apply_metadata_filters([chunk], {"exclude_ingredients": ["花生"]})
        assert len(result) == 1

    def test_exclude_ingredients_fail(self):
        """含排除食材的子块应被过滤。"""
        chunk = self._make_chunk(main_ingredients=["鸡胸肉", "花生"])
        result = apply_metadata_filters([chunk], {"exclude_ingredients": ["花生"]})
        assert len(result) == 0

    def test_include_ingredients_pass(self):
        """含要求食材的子块应通过。"""
        chunk = self._make_chunk(main_ingredients=["鸡胸肉", "青椒"])
        result = apply_metadata_filters([chunk], {"include_ingredients": ["鸡胸肉"]})
        assert len(result) == 1

    def test_include_ingredients_fail(self):
        """不含要求食材的子块应被过滤。"""
        chunk = self._make_chunk(main_ingredients=["五花肉", "青椒"])
        result = apply_metadata_filters([chunk], {"include_ingredients": ["鸡胸肉"]})
        assert len(result) == 0

    def test_difficulty_max_pass(self):
        """难度不超过上限的子块应通过。"""
        chunk = self._make_chunk(difficulty=2)
        result = apply_metadata_filters([chunk], {"difficulty_max": 3})
        assert len(result) == 1

    def test_difficulty_max_fail(self):
        """难度超过上限的子块现在是软约束，不再被过滤。"""
        chunk = self._make_chunk(difficulty=4)
        result = apply_metadata_filters([chunk], {"difficulty_max": 3})
        assert len(result) == 1  # 软约束不排除

    def test_costtime_max_pass(self):
        """耗时不超过上限的子块应通过。"""
        chunk = self._make_chunk(costtime_minutes=20)
        result = apply_metadata_filters([chunk], {"costtime_max": 30})
        assert len(result) == 1

    def test_costtime_max_fail(self):
        """耗时超过上限的子块现在是软约束，不再被过滤。"""
        chunk = self._make_chunk(costtime_minutes=60)
        result = apply_metadata_filters([chunk], {"costtime_max": 30})
        assert len(result) == 1  # 软约束不排除

    def test_costtime_none_passes(self):
        """costtime_minutes 为 None 时应保留（视为未知）。"""
        chunk = self._make_chunk(costtime_minutes=None)
        result = apply_metadata_filters([chunk], {"costtime_max": 30})
        assert len(result) == 1

    def test_category_pass(self):
        """匹配分类的子块应通过（categories 过滤检查 tags 列表）。"""
        chunk = self._make_chunk(tags=["家常菜", "快手菜"])
        result = apply_metadata_filters([chunk], {"categories": ["家常菜"]})
        assert len(result) == 1

    def test_category_fail(self):
        """不匹配分类的子块现在是软约束，不再被过滤。"""
        chunk = self._make_chunk(tags=["粤菜"])
        result = apply_metadata_filters([chunk], {"categories": ["家常菜"]})
        assert len(result) == 1  # 软约束不排除

    def test_categories_multi_any_match(self):
        """多选分类取并集：匹配任一即通过。"""
        chunk = self._make_chunk(tags=["粤菜"])
        result = apply_metadata_filters([chunk], {"categories": ["家常菜", "粤菜"]})
        assert len(result) == 1

    def test_combined_filters(self):
        """多条件同时过滤：硬约束（nutrition_tags, include_ingredients）排除，
        软约束（difficulty_max）不排除。"""
        chunks = [
            self._make_chunk(
                "R001",
                difficulty=2,
                main_ingredients=["鸡胸肉"],
                nutrition_tags=["高蛋白", "低脂"],
            ),
            self._make_chunk(
                "R002",
                difficulty=4,  # 超难度（软约束，不排除）
                main_ingredients=["鸡胸肉"],
                nutrition_tags=["高蛋白", "低脂"],
            ),
            self._make_chunk(
                "R003",
                difficulty=1,
                main_ingredients=["五花肉"],  # 不含鸡胸肉（硬约束，排除）
                nutrition_tags=["高蛋白"],
            ),
        ]

        filters = {
            "difficulty_max": 3,
            "include_ingredients": ["鸡胸肉"],
            "nutrition_tags": ["低脂"],
        }
        result = apply_metadata_filters(chunks, filters)
        # R001 通过（硬约束满足），R002 通过（difficulty 是软约束不排除），R003 被排除（缺鸡胸肉）
        assert len(result) == 2
        recipe_ids = {r["recipe_id"] for r in result}
        assert "R001" in recipe_ids
        assert "R002" in recipe_ids

    def test_empty_filters_pass_all(self):
        """空过滤条件应保留所有子块。"""
        chunks = [self._make_chunk("R001"), self._make_chunk("R002")]
        result = apply_metadata_filters(chunks, {})
        assert len(result) == 2


# =========================================================================
# 5. 测试父文档聚合去重
# =========================================================================


class TestAggregateParents:
    """测试父文档聚合去重逻辑。"""

    def test_multi_chunk_higher_score(self):
        """匹配多子块的食谱应获得更高的相关性得分。"""
        indexer = _make_mock_indexer()

        # R001 有 3 个子块匹配，R002 只有 1 个
        chunks = (
            _make_chunks("R001", score=0.8)  # 3 个子块
            + [{"node_id": "R002_info", "score": 0.9, "metadata": {}, "recipe_id": "R002"}]
        )

        results = aggregate_parents(chunks, indexer, top_k=5)

        assert len(results) == 2
        # R001（3 子块）应排在 R002（1 子块）前面
        assert results[0]["recipe_id"] == "R001"
        assert results[1]["recipe_id"] == "R002"

    def test_dedup_uniqueness(self):
        """结果中每个食谱只应出现一次。"""
        indexer = _make_mock_indexer()

        chunks = _make_chunks("R001", score=0.8) + _make_chunks("R001", score=0.7)

        results = aggregate_parents(chunks, indexer, top_k=5)

        recipe_ids = [r["recipe_id"] for r in results]
        assert len(recipe_ids) == len(set(recipe_ids))

    def test_top_k_truncation(self):
        """top_k 应正确截断结果数量。"""
        indexer = _make_mock_indexer()

        chunks = (
            _make_chunks("R001", score=0.9)
            + _make_chunks("R002", score=0.8)
            + _make_chunks("R003", score=0.7)
        )

        results = aggregate_parents(chunks, indexer, top_k=2)
        assert len(results) == 2

    def test_descending_relevance(self):
        """结果应按相关性降序排列。"""
        indexer = _make_mock_indexer()

        chunks = (
            _make_chunks("R001", score=0.9)
            + _make_chunks("R002", score=0.7)
            + _make_chunks("R003", score=0.8)
        )

        results = aggregate_parents(chunks, indexer, top_k=5)

        for i in range(len(results) - 1):
            assert results[i]["relevance"] >= results[i + 1]["relevance"]

    def test_output_format(self):
        """输出格式应包含所有必需字段。"""
        indexer = _make_mock_indexer()

        chunks = _make_chunks("R001", score=0.85)
        results = aggregate_parents(chunks, indexer, top_k=5)

        assert len(results) == 1
        result = results[0]
        assert "recipe_id" in result
        assert "text" in result
        assert "metadata" in result
        assert "relevance" in result
        assert "matched_chunks" in result
        assert result["recipe_id"] == "R001"
        assert isinstance(result["text"], str)
        assert isinstance(result["metadata"], dict)
        assert isinstance(result["relevance"], float)
        assert isinstance(result["matched_chunks"], int)

    def test_empty_chunks(self):
        """空子块列表应返回空结果。"""
        indexer = _make_mock_indexer()
        results = aggregate_parents([], indexer, top_k=5)
        assert results == []

    def test_missing_parent_skipped(self):
        """parent_store 中不存在的食谱应被跳过。"""
        indexer = _make_mock_indexer()
        # R999 不在 parent_store 中
        chunks = [{"node_id": "R999_info", "score": 0.9, "metadata": {}, "recipe_id": "R999"}]

        results = aggregate_parents(chunks, indexer, top_k=5)
        assert len(results) == 0


# =========================================================================
# 6. 测试 _build_qdrant_filter
# =========================================================================


class TestBuildQdrantFilter:
    """测试 Qdrant Filter 构建。"""

    def test_empty_filters(self):
        """空过滤条件应返回 None。"""
        assert _build_qdrant_filter({}) is None

    def test_difficulty_filter(self):
        """软约束不再生成 Qdrant 预过滤条件，返回 None。"""
        result = _build_qdrant_filter({"difficulty_max": 3})
        assert result is None

    def test_multiple_filters(self):
        """软约束全部移除后，返回 None（硬约束通过后过滤处理）。"""
        result = _build_qdrant_filter({
            "difficulty_max": 3,
            "costtime_max": 30,
            "categories": ["家常菜"],
        })
        assert result is None

    def test_unsupported_filter_ignored(self):
        """不支持预过滤的字段应被忽略。"""
        result = _build_qdrant_filter({"nutrition_tags": ["低脂"]})
        assert result is None


# =========================================================================
# 7. 测试 retrieve 完整流程（使用 mock）
# =========================================================================


class TestRetrieveFullFlow:
    """测试 retrieve 完整流程。"""

    def test_retrieve_with_bm25_only(self):
        """当无 Qdrant 时，仅使用 BM25 进行检索。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        results = retriever.retrieve("红烧肉怎么做", top_k=3)

        assert len(results) > 0
        # 结果应包含 recipe_id、text 等字段
        for r in results:
            assert "recipe_id" in r
            assert "text" in r
            assert "relevance" in r

    def test_retrieve_with_filters(self):
        """带过滤条件的检索应正确过滤。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        # 排除花生 → R003（宫保鸡丁，含花生）应被过滤
        results = retriever.retrieve(
            "鸡肉怎么做",
            top_k=5,
            filters={"exclude_ingredients": ["花生"]},
        )

        recipe_ids = {r["recipe_id"] for r in results}
        assert "R003" not in recipe_ids

    @patch("src.pipeline.retriever.RecipeRetriever._dense_retrieve")
    def test_retrieve_full_hybrid(self, mock_dense):
        """完整混合检索流程（Dense + BM25）。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        # mock Dense 返回 R001 和 R002 的子块
        mock_dense.return_value = [
            {
                "node_id": "R001_info",
                "score": 0.95,
                "metadata": _make_parent_store()["R001"]["metadata"],
                "recipe_id": "R001",
            },
            {
                "node_id": "R001_ingredient",
                "score": 0.90,
                "metadata": _make_parent_store()["R001"]["metadata"],
                "recipe_id": "R001",
            },
            {
                "node_id": "R002_info",
                "score": 0.85,
                "metadata": _make_parent_store()["R002"]["metadata"],
                "recipe_id": "R002",
            },
        ]

        results = retriever.retrieve("红烧肉", top_k=3)

        assert len(results) > 0
        # 结果应去重
        recipe_ids = [r["recipe_id"] for r in results]
        assert len(recipe_ids) == len(set(recipe_ids))

    @patch("src.pipeline.retriever.RecipeRetriever._dense_retrieve")
    def test_retrieve_respects_top_k(self, mock_dense):
        """retrieve 应遵守 top_k 限制。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        mock_dense.return_value = (
            _make_chunks("R001", score=0.9)
            + _make_chunks("R002", score=0.8)
            + _make_chunks("R003", score=0.7)
        )
        # 给 dense 结果添加 metadata
        for chunk in mock_dense.return_value:
            rid = chunk["recipe_id"]
            chunk["metadata"] = _make_parent_store()[rid]["metadata"]

        results = retriever.retrieve("做菜", top_k=1)
        assert len(results) <= 1

    def test_retrieve_empty_query(self):
        """空查询不应报错。"""
        indexer = _make_mock_indexer()
        retriever = RecipeRetriever(indexer)
        retriever.build_bm25_index(force_rebuild=True)

        results = retriever.retrieve("", top_k=3)
        # 空查询可能返回空结果或部分结果，不应抛异常
        assert isinstance(results, list)


# =========================================================================
# 8. 测试弹性约束（Elastic Constraints）
# =========================================================================


class TestElasticConstraints:
    """测试弹性约束辅助函数和 aggregate_parents 中的弹性约束逻辑。"""

    # --- _has_elastic_constraints ---

    def test_has_elastic_no_filters(self):
        """无过滤条件时不存在弹性约束。"""
        assert _has_elastic_constraints({}) is False
        assert _has_elastic_constraints(None) is False

    def test_has_elastic_only_hard(self):
        """仅含硬约束时不存在弹性约束。"""
        assert _has_elastic_constraints({"nutrition_tags": ["低脂"]}) is False
        assert _has_elastic_constraints({"exclude_ingredients": ["辣椒"]}) is False

    def test_has_elastic_with_categories(self):
        """含 categories 时存在弹性约束。"""
        assert _has_elastic_constraints({"categories": ["家常菜"]}) is True

    def test_has_elastic_with_difficulty(self):
        """含 difficulty_max 时存在弹性约束。"""
        assert _has_elastic_constraints({"difficulty_max": 2}) is True

    def test_has_elastic_with_costtime(self):
        """含 costtime_max 时存在弹性约束。"""
        assert _has_elastic_constraints({"costtime_max": 30}) is True

    # --- _passes_elastic_constraints ---

    def test_passes_elastic_all_match(self):
        """全部弹性约束匹配时应通过。"""
        meta = {"tags": ["家常菜"], "difficulty": 1, "costtime_minutes": 20}
        filters = {"categories": ["家常菜"], "difficulty_max": 2, "costtime_max": 30}
        assert _passes_elastic_constraints(meta, filters) is True

    def test_passes_elastic_category_mismatch(self):
        """分类不匹配时不通过。"""
        meta = {"tags": ["粤菜"], "difficulty": 1}
        filters = {"categories": ["家常菜"]}
        assert _passes_elastic_constraints(meta, filters) is False

    def test_passes_elastic_difficulty_too_high(self):
        """难度超限时不通过。"""
        meta = {"tags": ["家常菜"], "difficulty": 3}
        filters = {"difficulty_max": 1}
        assert _passes_elastic_constraints(meta, filters) is False

    def test_passes_elastic_costtime_too_high(self):
        """耗时超限时不通过。"""
        meta = {"costtime_minutes": 60}
        filters = {"costtime_max": 30}
        assert _passes_elastic_constraints(meta, filters) is False

    def test_passes_elastic_none_difficulty(self):
        """难度未知时视为通过。"""
        meta = {"difficulty": None}
        filters = {"difficulty_max": 1}
        assert _passes_elastic_constraints(meta, filters) is True

    def test_passes_elastic_no_constraint(self):
        """无弹性约束时所有食谱通过。"""
        meta = {"tags": ["川菜"], "difficulty": 3, "costtime_minutes": 120}
        assert _passes_elastic_constraints(meta, {}) is True

    # --- _compute_elastic_bonus ---

    def test_elastic_bonus_all_match(self):
        """全部匹配时获得最大加分。"""
        meta = {"tags": ["家常菜"], "difficulty": 1, "costtime_minutes": 15}
        filters = {"categories": ["家常菜"], "difficulty_max": 2, "costtime_max": 30}
        bonus = _compute_elastic_bonus(meta, filters)
        assert bonus == pytest.approx(0.24)  # 0.12 + 0.06 + 0.06

    def test_elastic_bonus_none_match(self):
        """全部不匹配时加分为 0。"""
        meta = {"tags": ["粤菜"], "difficulty": 3, "costtime_minutes": 60}
        filters = {"categories": ["家常菜"], "difficulty_max": 1, "costtime_max": 30}
        bonus = _compute_elastic_bonus(meta, filters)
        assert bonus == 0.0

    def test_elastic_bonus_partial_match(self):
        """部分匹配时获得对应加分。"""
        meta = {"tags": ["家常菜"], "difficulty": 3}
        filters = {"categories": ["家常菜"], "difficulty_max": 1}
        bonus = _compute_elastic_bonus(meta, filters)
        assert bonus == pytest.approx(0.12)  # 仅分类匹配

    # --- _compute_soft_bonus（仅关键词） ---

    def test_soft_bonus_keyword_only(self):
        """软约束现在仅包含关键词加分。"""
        meta = {"category": "家常菜", "tags": ["家常菜"], "difficulty": 1}
        filters = {
            "keywords": ["家常菜"],
            "categories": ["家常菜"],
            "difficulty_max": 2,
        }
        bonus = _compute_soft_bonus(meta, filters)
        assert bonus == pytest.approx(0.03)  # 仅关键词

    # --- aggregate_parents 弹性约束集成 ---

    def test_aggregate_strict_mode(self):
        """足够结果满足弹性约束时使用严格模式。"""
        indexer = _make_mock_indexer()
        # R001(家常菜,d=2), R002(粤菜,d=1), R003(川菜,d=3)
        chunks = (
            _make_chunks("R001", score=0.9)
            + _make_chunks("R002", score=0.8)
            + _make_chunks("R003", score=0.7)
        )

        # difficulty_max=2: R001(d=2 ✅), R002(d=1 ✅), R003(d=3 ✗)
        results = aggregate_parents(
            chunks, indexer, top_k=5,
            filters={"difficulty_max": 2},
        )

        recipe_ids = {r["recipe_id"] for r in results}
        # R001 和 R002 满足 d<=2，且 >= MIN_ELASTIC_RESULTS(=3 但只有2配方)
        # 如果只有2条满足(<3)，回退模式
        # 实际：R001(d=2)和R002(d=1)满足，只有2条 < 3 → 回退
        assert "R001" in recipe_ids
        assert "R002" in recipe_ids

    def test_aggregate_fallback_keeps_all(self):
        """回退模式保留所有结果但匹配的排更前。"""
        indexer = _make_mock_indexer()
        chunks = (
            _make_chunks("R001", score=0.9)
            + _make_chunks("R002", score=0.8)
            + _make_chunks("R003", score=0.7)
        )

        # categories=["粤菜"]: 仅 R002 匹配（< 3 → 回退）
        results = aggregate_parents(
            chunks, indexer, top_k=5,
            filters={"categories": ["粤菜"]},
        )

        # 回退模式：全部 3 个食谱都应在结果中
        assert len(results) == 3
        # R002 因为弹性加分应排名靠前
        r002_pos = next(i for i, r in enumerate(results) if r["recipe_id"] == "R002")
        assert r002_pos <= 1  # R002 应在前 2 名

    def test_aggregate_constraint_relaxed_flag(self):
        """回退模式下不匹配的结果标记 constraint_relaxed=True。"""
        indexer = _make_mock_indexer()
        chunks = (
            _make_chunks("R001", score=0.9)
            + _make_chunks("R002", score=0.8)
            + _make_chunks("R003", score=0.7)
        )

        results = aggregate_parents(
            chunks, indexer, top_k=5,
            filters={"categories": ["粤菜"]},
        )

        for r in results:
            if r["recipe_id"] == "R002":
                # R002 匹配粤菜，不应被标记
                assert r.get("constraint_relaxed") is False
            else:
                # R001、R003 不匹配，应被标记
                assert r.get("constraint_relaxed") is True

    def test_aggregate_no_elastic_no_flag(self):
        """无弹性约束时不标记 constraint_relaxed。"""
        indexer = _make_mock_indexer()
        chunks = _make_chunks("R001", score=0.9)

        results = aggregate_parents(chunks, indexer, top_k=5)

        for r in results:
            assert r.get("constraint_relaxed") is False


# =========================================================================
# 9. 测试排除食材增强（main + sub ingredients）
# =========================================================================


class TestExcludeIngredientsEnhanced:
    """测试排除食材同时检查主料和辅料。"""

    def _make_chunk(self, main=None, sub=None, **kwargs):
        return {
            "node_id": "T001_info",
            "score": 0.9,
            "recipe_id": "T001",
            "metadata": {
                "main_ingredients": main or [],
                "sub_ingredients": sub or [],
                **kwargs,
            },
        }

    def test_exclude_in_main(self):
        """排除食材在主料中应被过滤。"""
        chunk = self._make_chunk(main=["鸡胸肉", "花生"])
        result = apply_metadata_filters([chunk], {"exclude_ingredients": ["花生"]})
        assert len(result) == 0

    def test_exclude_in_sub(self):
        """排除食材在辅料中也应被过滤。"""
        chunk = self._make_chunk(main=["鸡胸肉"], sub=["花生", "干辣椒"])
        result = apply_metadata_filters([chunk], {"exclude_ingredients": ["花生"]})
        assert len(result) == 0

    def test_exclude_not_in_either(self):
        """排除食材不在主料和辅料中应保留。"""
        chunk = self._make_chunk(main=["鸡胸肉"], sub=["干辣椒"])
        result = apply_metadata_filters([chunk], {"exclude_ingredients": ["花生"]})
        assert len(result) == 1

    def test_exclude_sub_is_string_na(self):
        """辅料为字符串 'N/A' 时不报错。"""
        chunk = self._make_chunk(main=["鸡胸肉"])
        chunk["metadata"]["sub_ingredients"] = "N/A"
        result = apply_metadata_filters([chunk], {"exclude_ingredients": ["花生"]})
        assert len(result) == 1
