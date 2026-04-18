"""
混合检索器模块（retriever）

职责：
1. Dense 向量检索：通过 Qdrant 进行语义相似度检索
2. BM25 稀疏检索：通过 jieba 分词 + rank_bm25 进行关键词匹配
3. RRF 融合：Reciprocal Rank Fusion 合并两路检索结果
4. 元数据后过滤：根据用户约束条件过滤不符合要求的子块
5. 父文档聚合去重：按 recipe_id 分组、加权评分、去重输出 top-K 父文档

核心流程：
    用户查询
        → Dense 检索（Qdrant 向量搜索）→ top-N 子块
        → BM25 检索（jieba + rank_bm25）→ top-N 子块
        → RRF 融合 → 统一排序
        → 元数据后过滤（营养标签、食材、难度等）
        → 父文档聚合去重 → top-K 食谱
"""

import json
import logging
from pathlib import Path
from typing import Optional

import jieba
from rank_bm25 import BM25Okapi
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue, Range

from src import config

logger = logging.getLogger(__name__)


class RecipeRetriever:
    """混合检索器：Dense + BM25 + RRF + 父文档聚合去重"""

    def __init__(self, indexer):
        """
        初始化检索器。

        参数:
            indexer: 已加载索引的 RecipeIndexer 实例
        """
        self._indexer = indexer
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_corpus: list[list[str]] = []  # 分词后的语料库
        self._bm25_id_map: list[str] = []  # corpus[i] 对应的子块 id

    # ------------------------------------------------------------------
    # BM25 索引构建
    # ------------------------------------------------------------------

    def build_bm25_index(self, force_rebuild: bool = False):
        """
        构建 BM25 索引。

        从 indexer.parent_store 中提取所有子块文本，
        用 jieba 分词后构建 BM25 索引。

        支持序列化到 BM25_INDEX_PATH 磁盘缓存。

        参数:
            force_rebuild: 是否强制重建（忽略缓存）
        """
        cache_path = Path(config.BM25_INDEX_PATH)

        # 尝试加载缓存
        if not force_rebuild and cache_path.exists():
            if self._load_bm25_cache(cache_path):
                return

        # 从 parent_store 提取所有子块文本并分词
        logger.info("正在构建 BM25 索引...")
        corpus: list[list[str]] = []
        id_map: list[str] = []

        for recipe_id, entry in self._indexer.parent_store.items():
            text = entry.get("text", "")
            if not text:
                continue
            # 每个父文档作为一个整体文档进入 BM25
            # 但我们需要按子块粒度来做，以便后续与 dense 检索对齐
            # 根据 indexer 设计，每个食谱有 3 个子块：info / ingredient / step
            for chunk_type in ["info", "ingredient", "step"]:
                chunk_id = f"{recipe_id}_{chunk_type}"
                # 从父文档文本中提取对应片段（简化处理：使用完整父文档文本）
                # 实际上子块文本无法从父文档精确还原，使用父文档文本作为 BM25 语料
                tokens = jieba.lcut(text)
                if tokens:
                    corpus.append(tokens)
                    id_map.append(chunk_id)

        if not corpus:
            logger.warning("BM25 语料为空，跳过索引构建")
            return

        self._bm25_corpus = corpus
        self._bm25_id_map = id_map
        self._bm25 = BM25Okapi(corpus)

        logger.info(f"BM25 索引构建完成：{len(corpus)} 个文档")

        # 保存缓存
        self._save_bm25_cache(cache_path)

    def _save_bm25_cache(self, path: Path):
        """将 BM25 语料和 id 映射序列化为 JSON。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "corpus": self._bm25_corpus,
            "id_map": self._bm25_id_map,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
        logger.info(f"BM25 缓存已保存: {path}")

    def _load_bm25_cache(self, path: Path) -> bool:
        """
        从 JSON 缓存加载 BM25 索引。

        返回:
            是否加载成功
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            corpus = cache_data["corpus"]
            id_map = cache_data["id_map"]

            if not corpus:
                logger.warning("BM25 缓存为空")
                return False

            self._bm25_corpus = corpus
            self._bm25_id_map = id_map
            self._bm25 = BM25Okapi(corpus)

            logger.info(f"BM25 缓存已加载: {path}（{len(corpus)} 个文档）")
            return True
        except Exception as e:
            logger.warning(f"BM25 缓存加载失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 主检索接口
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = None,
        filters: dict | None = None,
    ) -> list[dict]:
        """
        执行混合检索 + 父文档聚合去重。

        参数:
            query: 用户查询文本
            top_k: 返回的食谱数量（默认 config.TOP_K）
            filters: 可选的元数据过滤条件，格式如：
                {
                    "nutrition_tags": ["低脂"],
                    "exclude_ingredients": ["花生"],
                    "include_ingredients": ["鸡胸肉"],
                    "difficulty_max": 3,
                    "costtime_max": 30,
                    "category": "家常菜",
                }

        返回:
            去重后的父文档列表（按相关性降序），每项：
            {
                "recipe_id": str,
                "text": str,          # 父文档完整文本
                "metadata": dict,     # 父文档完整元数据
                "relevance": float,   # 聚合相关性得分
                "matched_chunks": int, # 匹配的子块数量
            }
        """
        if top_k is None:
            top_k = config.TOP_K

        retrieval_top_k = config.RETRIEVAL_TOP_K

        # 1. Dense 向量检索
        dense_results = self._dense_retrieve(query, retrieval_top_k, filters)

        # 2. BM25 稀疏检索
        bm25_results = self._bm25_retrieve(query, retrieval_top_k)

        # 3. RRF 融合
        fused = rrf_fuse(dense_results, bm25_results)

        # 4. 元数据后过滤（BM25 结果不支持预过滤，需在融合后统一过滤）
        if filters:
            fused = apply_metadata_filters(fused, filters)

        # 5. 父文档聚合去重（含标题匹配 + 软约束加分）
        results = aggregate_parents(fused, self._indexer, top_k, filters, query)

        return results

    # ------------------------------------------------------------------
    # Dense 向量检索
    # ------------------------------------------------------------------

    def _dense_retrieve(
        self, query: str, top_k: int, filters: dict | None = None
    ) -> list[dict]:
        """
        通过 Qdrant 执行向量语义检索。

        参数:
            query: 用户查询文本
            top_k: 返回子块数量
            filters: 可选过滤条件（转为 Qdrant Filter）

        返回:
            子块列表，每项含 node_id / score / metadata
        """
        client = self._indexer.qdrant_client
        if client is None:
            logger.warning("Qdrant 客户端未初始化，跳过 Dense 检索")
            return []

        # 获取 embedding 模型，生成查询向量
        from llama_index.core import Settings

        embed_model = Settings.embed_model
        if embed_model is None:
            logger.warning("Embedding 模型未设置，跳过 Dense 检索")
            return []

        query_vector = embed_model.get_query_embedding(query)

        # 构建 Qdrant Filter（仅对支持预过滤的字段）
        qdrant_filter = _build_qdrant_filter(filters) if filters else None

        # 执行向量搜索
        search_results = client.query_points(
            collection_name=config.QDRANT_COLLECTION_NAME,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )

        # 转为统一格式（使用 chunk_id 作为 node_id，与 BM25 对齐以便 RRF 融合）
        results = []
        for point in search_results.points:
            payload = point.payload or {}
            results.append({
                "node_id": payload.get("chunk_id", str(point.id)),
                "score": point.score,
                "metadata": payload,
                "recipe_id": payload.get("recipe_id", ""),
            })

        logger.debug(f"Dense 检索返回 {len(results)} 个子块")
        return results

    # ------------------------------------------------------------------
    # BM25 稀疏检索
    # ------------------------------------------------------------------

    def _bm25_retrieve(self, query: str, top_k: int) -> list[dict]:
        """
        通过 BM25 执行关键词检索。

        参数:
            query: 用户查询文本
            top_k: 返回子块数量

        返回:
            子块列表，每项含 node_id / score / metadata / recipe_id
        """
        if self._bm25 is None:
            logger.warning("BM25 索引未构建，跳过 BM25 检索")
            return []

        # jieba 分词
        query_tokens = jieba.lcut(query)
        if not query_tokens:
            return []

        # 获取所有文档得分
        raw_scores = self._bm25.get_scores(query_tokens)

        # 归一化到 [0, 1]
        max_score = max(raw_scores) if len(raw_scores) > 0 else 0
        if max_score > 0:
            normalized_scores = [s / max_score for s in raw_scores]
        else:
            normalized_scores = list(raw_scores)

        # 取 top-K（按得分降序）
        scored_indices = sorted(
            range(len(normalized_scores)),
            key=lambda i: normalized_scores[i],
            reverse=True,
        )[:top_k]

        results = []
        for idx in scored_indices:
            score = normalized_scores[idx]
            if score <= 0:
                continue
            node_id = self._bm25_id_map[idx]
            # 从 node_id 解析 recipe_id（格式 "{recipe_id}_{chunk_type}"）
            recipe_id = _parse_recipe_id(node_id)
            # 从 parent_store 获取元数据
            parent_meta = self._indexer.get_parent_metadata(recipe_id) or {}
            results.append({
                "node_id": node_id,
                "score": score,
                "metadata": parent_meta,
                "recipe_id": recipe_id,
            })

        logger.debug(f"BM25 检索返回 {len(results)} 个子块")
        return results


# =========================================================================
# 辅助函数（模块级，便于单元测试）
# =========================================================================


def _parse_recipe_id(node_id: str) -> str:
    """
    从子块 node_id 中解析 recipe_id。

    node_id 格式为 "{recipe_id}_{chunk_type}"，
    chunk_type 为 info / ingredient / step。

    示例:
        "12345_info" → "12345"
        "abc_def_step" → "abc_def"
    """
    for suffix in ("_info", "_ingredient", "_step"):
        if node_id.endswith(suffix):
            return node_id[: -len(suffix)]
    # 回退：取最后一个下划线前的部分
    parts = node_id.rsplit("_", 1)
    return parts[0] if len(parts) > 1 else node_id


def rrf_fuse(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    RRF（Reciprocal Rank Fusion）融合两路检索结果。

    公式：score(d) = sum(1 / (k + rank_i(d))) 对每路检索

    参数:
        dense_results: 向量检索结果（已按 score 降序）
        bm25_results: BM25 检索结果（已按 score 降序）
        k: RRF 参数，通常取 60

    返回:
        融合后的子块列表（按 RRF 得分降序），格式同输入
    """
    rrf_scores: dict[str, float] = {}
    node_info: dict[str, dict] = {}

    # Dense 路
    for rank, item in enumerate(dense_results):
        node_id = item["node_id"]
        rrf_scores[node_id] = rrf_scores.get(node_id, 0) + 1.0 / (k + rank + 1)
        if node_id not in node_info:
            node_info[node_id] = item

    # BM25 路
    for rank, item in enumerate(bm25_results):
        node_id = item["node_id"]
        rrf_scores[node_id] = rrf_scores.get(node_id, 0) + 1.0 / (k + rank + 1)
        if node_id not in node_info:
            node_info[node_id] = item

    # 按 RRF 得分降序排列
    sorted_ids = sorted(rrf_scores.keys(), key=lambda nid: rrf_scores[nid], reverse=True)

    results = []
    for node_id in sorted_ids:
        item = node_info[node_id].copy()
        item["score"] = rrf_scores[node_id]
        results.append(item)

    return results


def apply_metadata_filters(chunks: list[dict], filters: dict) -> list[dict]:
    """
    对子块列表进行元数据后过滤。

    支持的过滤条件：
    - nutrition_tags: 子块 metadata["nutrition_tags"] 包含指定标签
    - exclude_ingredients: 子块 metadata["main_ingredients"] 不包含指定食材
    - include_ingredients: 子块 metadata["main_ingredients"] 包含指定食材
    - difficulty_max: 子块 metadata["difficulty"] <= 指定值
    - costtime_max: 子块 metadata["costtime_minutes"] <= 指定值
    - categories: 子块 metadata["tags"] 包含指定值列表中的任一值
    - keywords: 子块 metadata["category"](zid) 匹配指定值列表中的任一值

    参数:
        chunks: 子块列表
        filters: 过滤条件字典

    返回:
        过滤后的子块列表
    """
    result = []

    for chunk in chunks:
        meta = chunk.get("metadata", {})

        if not _passes_filters(meta, filters):
            continue

        result.append(chunk)

    return result


def _passes_filters(meta: dict, filters: dict) -> bool:
    """
    检查单个子块的元数据是否满足硬约束条件。

    硬约束（不满足则排除）：
    - nutrition_tags: 必须包含指定营养标签
    - exclude_ingredients: 不得包含指定食材
    - include_ingredients: 必须包含指定食材

    软约束（categories, keywords, difficulty_max, costtime_max）
    不在此处过滤，而是在 aggregate_parents 中作为加分项处理。

    返回:
        True 表示通过硬约束，False 表示被排除
    """
    # 营养标签过滤（硬约束）
    required_tags = filters.get("nutrition_tags")
    if required_tags:
        chunk_tags = meta.get("nutrition_tags", [])
        if not any(tag in chunk_tags for tag in required_tags):
            return False

    # 排除食材过滤（硬约束）—— 同时检查主料和辅料
    exclude_ings = filters.get("exclude_ingredients")
    if exclude_ings:
        main_ings = meta.get("main_ingredients", [])
        sub_ings = meta.get("sub_ingredients", [])
        if isinstance(sub_ings, str):
            sub_ings = []
        all_ings = list(main_ings) + list(sub_ings)
        if any(ing in all_ings for ing in exclude_ings):
            return False

    # 包含食材过滤（硬约束）
    include_ings = filters.get("include_ingredients")
    if include_ings:
        main_ings = meta.get("main_ingredients", [])
        if not any(ing in main_ings for ing in include_ings):
            return False

    return True


def _compute_title_bonus(title: str, query: str) -> float:
    """
    计算标题匹配加分。

    让标题与用户查询高度吻合的食谱获得排名提升：
    - 精确匹配（标题 == 查询）→ +0.20
    - 查询是标题子串或标题是查询子串 → +0.15

    参数:
        title: 食谱标题
        query: 用户查询文本

    返回:
        加分值（0 ~ 0.20）
    """
    if not title or not query:
        return 0.0
    title_clean = title.strip()
    query_clean = query.strip()
    if query_clean == title_clean:
        return 0.20
    if query_clean in title_clean or title_clean in query_clean:
        return 0.15
    return 0.0


def _compute_soft_bonus(meta: dict, filters: dict) -> float:
    """
    计算软约束加分（仅关键词匹配）。

    categories、difficulty_max、costtime_max 已移至弹性约束处理，
    此函数仅保留 keywords 加分。

    参数:
        meta: 父文档元数据
        filters: 用户过滤条件

    返回:
        加分值（0 ~ 0.03）
    """
    if not filters:
        return 0.0

    bonus = 0.0

    # 关键词匹配加分
    keywords = filters.get("keywords") or []
    if keywords:
        recipe_zid = meta.get("category", "")
        if recipe_zid in keywords:
            bonus += 0.03

    return bonus


# =========================================================================
# 弹性约束（Elastic Constraints）
#
# categories、difficulty_max、costtime_max 使用"先严后宽"策略：
# 1. 先作为硬约束过滤，若结果 ≥ MIN_ELASTIC_RESULTS 则采用严格结果
# 2. 否则自动放宽为增强版软约束（给匹配的结果加更高的奖励分）
# =========================================================================

MIN_ELASTIC_RESULTS = 3

# 回退模式下的增强加分值
_ELASTIC_CATEGORY_BONUS = 0.12
_ELASTIC_DIFFICULTY_BONUS = 0.06
_ELASTIC_COSTTIME_BONUS = 0.06


def _has_elastic_constraints(filters: dict) -> bool:
    """检查过滤条件中是否包含弹性约束。"""
    if not filters:
        return False
    return any([
        filters.get("categories"),
        filters.get("difficulty_max") is not None,
        filters.get("costtime_max") is not None,
    ])


def _passes_elastic_constraints(meta: dict, filters: dict) -> bool:
    """
    检查食谱元数据是否满足所有弹性约束。

    - categories: 食谱 tags 包含用户选择的任一分类
    - difficulty_max: 食谱难度 ≤ 上限
    - costtime_max: 食谱耗时 ≤ 上限
    """
    categories = filters.get("categories") or []
    if categories:
        recipe_tags = meta.get("tags", [])
        if not any(cat in recipe_tags for cat in categories):
            return False

    difficulty_max = filters.get("difficulty_max")
    if difficulty_max is not None:
        recipe_diff = meta.get("difficulty")
        if recipe_diff is not None and recipe_diff > difficulty_max:
            return False

    costtime_max = filters.get("costtime_max")
    if costtime_max is not None:
        recipe_time = meta.get("costtime_minutes")
        if recipe_time is not None and recipe_time > costtime_max:
            return False

    return True


def _compute_elastic_bonus(meta: dict, filters: dict) -> float:
    """
    计算弹性约束的增强加分（回退模式使用）。

    当严格过滤结果不足时，匹配弹性约束的食谱获得额外加分，
    使其在混合结果中排名靠前。

    返回:
        加分值（0 ~ 0.24）
    """
    bonus = 0.0

    categories = filters.get("categories") or []
    if categories:
        recipe_tags = meta.get("tags", [])
        if any(cat in recipe_tags for cat in categories):
            bonus += _ELASTIC_CATEGORY_BONUS

    difficulty_max = filters.get("difficulty_max")
    if difficulty_max is not None:
        recipe_diff = meta.get("difficulty")
        if recipe_diff is not None and recipe_diff <= difficulty_max:
            bonus += _ELASTIC_DIFFICULTY_BONUS

    costtime_max = filters.get("costtime_max")
    if costtime_max is not None:
        recipe_time = meta.get("costtime_minutes")
        if recipe_time is not None and recipe_time <= costtime_max:
            bonus += _ELASTIC_COSTTIME_BONUS

    return bonus


def aggregate_parents(
    filtered_chunks: list[dict],
    indexer,
    top_k: int,
    filters: dict | None = None,
    query: str = "",
) -> list[dict]:
    """
    按 recipe_id 分组、加权评分、去重输出 top-K 父文档。

    评分流程：
    1. 对 RRF 分数做批内归一化（最高分 → 1.0），让分数有意义
    2. 基础公式：
        base = (match_count / 3) * WEIGHT_MATCH
             + avg(norm_scores) * WEIGHT_AVG
             + max(norm_scores) * WEIGHT_MAX
       → 理论最高 1.0，自然分布在 0~1
    3. 叠加标题匹配加分（0~0.20）和关键词软约束加分（0~0.03）
    4. 弹性约束处理：categories/difficulty_max/costtime_max
       - 严格模式：满足约束的结果 ≥ MIN_ELASTIC_RESULTS → 仅返回满足的
       - 回退模式：不足 → 保留全部，匹配的加增强奖励（0~0.24）
    5. 最终 clamp 到 [0, 1]

    参数:
        filtered_chunks: 过滤后的子块列表
        indexer: RecipeIndexer 实例
        top_k: 返回的食谱数量
        filters: 用户过滤条件（用于软约束/弹性约束）
        query: 用户原始查询文本（用于标题匹配加分）

    返回:
        去重后的父文档列表（按相关性降序），含 constraint_relaxed 标记
    """
    if not filtered_chunks:
        return []

    # 0. RRF 分数批内归一化：最高分 → 1.0
    max_score = max(c["score"] for c in filtered_chunks)
    if max_score > 0:
        for chunk in filtered_chunks:
            chunk["score_norm"] = chunk["score"] / max_score
    else:
        for chunk in filtered_chunks:
            chunk["score_norm"] = 0.0

    # 1. 按 recipe_id 分组
    groups: dict[str, list[dict]] = {}
    for chunk in filtered_chunks:
        rid = chunk.get("recipe_id") or _parse_recipe_id(chunk.get("node_id", ""))
        groups.setdefault(rid, []).append(chunk)

    # 2. 计算归一化后的基础相关性
    scored = []
    for rid, chunks in groups.items():
        match_count = len(chunks)
        norm_scores = [c["score_norm"] for c in chunks]
        base_relevance = (
            (match_count / 3) * config.DEDUP_WEIGHT_MATCH_RATIO
            + (sum(norm_scores) / len(norm_scores)) * config.DEDUP_WEIGHT_AVG_SCORE
            + max(norm_scores) * config.DEDUP_WEIGHT_MAX_SCORE
        )
        scored.append((rid, base_relevance, match_count))

    # 3. 先按 base_relevance 排序，取扩大的候选集
    scored.sort(key=lambda x: -x[1])

    # 4. 叠加标题匹配 + 关键词软约束加分，组装输出
    results = []
    for rid, base_relevance, match_count in scored[:top_k * 3]:
        parent_text = indexer.get_parent_text(rid)
        parent_meta = indexer.get_parent_metadata(rid)
        if parent_text:
            title = (parent_meta or {}).get("title", "")
            title_bonus = _compute_title_bonus(title, query)
            soft_bonus = _compute_soft_bonus(parent_meta or {}, filters or {})
            final = min(1.0, base_relevance + title_bonus + soft_bonus)
            results.append({
                "recipe_id": rid,
                "text": parent_text,
                "metadata": parent_meta or {},
                "relevance": round(final, 4),
                "matched_chunks": match_count,
                "constraint_relaxed": False,
            })

    # 5. 弹性约束处理
    if filters and _has_elastic_constraints(filters):
        strict = [r for r in results
                  if _passes_elastic_constraints(r["metadata"], filters)]
        if len(strict) >= MIN_ELASTIC_RESULTS:
            # 严格模式：结果充足，仅返回满足约束的食谱
            strict.sort(key=lambda x: -x["relevance"])
            logger.debug(
                f"弹性约束严格模式: {len(strict)} 条满足，返回 top {top_k}"
            )
            return strict[:top_k]
        else:
            # 回退模式：为匹配的结果叠加增强奖励，不匹配的保留但排后面
            logger.info(
                f"弹性约束回退: 严格结果仅 {len(strict)} 条 < {MIN_ELASTIC_RESULTS}，"
                "切换为增强软约束"
            )
            for r in results:
                if _passes_elastic_constraints(r["metadata"], filters):
                    eb = _compute_elastic_bonus(r["metadata"], filters)
                    r["relevance"] = round(min(1.0, r["relevance"] + eb), 4)
                else:
                    r["constraint_relaxed"] = True

    # 加分后重排，取 top_k
    results.sort(key=lambda x: -x["relevance"])
    return results[:top_k]


def _build_qdrant_filter(filters: dict) -> Optional[Filter]:
    """
    将用户过滤条件转为 Qdrant Filter 对象。

    仅构建硬约束（必须满足的条件）。
    弹性约束（分类、难度、耗时）和软约束（关键词）不在此处过滤，
    而是在 aggregate_parents 阶段处理。

    当前硬约束均通过后过滤实现（nutrition_tags、exclude_ingredients），
    因此此函数通常返回 None，使 Qdrant 返回最大候选集。

    参数:
        filters: 用户过滤条件字典

    返回:
        Qdrant Filter 对象，无条件时返回 None
    """
    # 硬约束通过后过滤处理，Qdrant 预过滤暂不设条件
    # 这样可以最大化候选集，避免因筛选条件过严导致 0 结果
    return None
