"""
评估专用路由（不要求认证，仅供本地评估脚本调用）

与 /api/recommend 的区别：
- 不做鉴权，评估脚本无需登录
- /eval/retrieve 仅返回检索结果（含父文档 text），供 Hit Rate/MRR/Precision 计算
- /eval/query 返回生成答案 + contexts，供 Faithfulness/Relevancy 评估
- 响应体保留原始 text / metadata 字段（前端 schema 会丢 text）

这些接口不应暴露到公网；部署时可通过反向代理屏蔽 /api/eval/* 路径。
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.dependencies import get_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eval", tags=["评估"])


class EvalFilters(BaseModel):
    """评估请求的过滤条件（字段与 RecipeRetriever.retrieve 一致）"""
    nutrition_tags: list[str] | None = None
    exclude_ingredients: list[str] | None = None
    include_ingredients: list[str] | None = None
    difficulty_max: int | None = None
    costtime_max: int | None = None
    categories: list[str] | None = None
    keywords: list[str] | None = None


class EvalRetrieveRequest(BaseModel):
    """检索评估请求"""
    query: str = Field(..., description="查询文本")
    top_k: int | None = Field(None, description="返回的父文档数,默认 config.TOP_K")
    filters: EvalFilters | None = None


class EvalRetrieveItem(BaseModel):
    """检索评估单条结果（保留 retriever 原始字段）"""
    recipe_id: str
    text: str
    metadata: dict[str, Any]
    relevance: float
    matched_chunks: int


class EvalRetrieveResponse(BaseModel):
    results: list[EvalRetrieveItem]


class EvalQueryRequest(BaseModel):
    """生成评估请求"""
    query: str
    filters: EvalFilters | None = None


class EvalQueryResponse(BaseModel):
    answer: str
    contexts: list[str]
    sources: list[dict[str, Any]]


def _ensure_ready(pipeline) -> None:
    if pipeline is None or not pipeline.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="推荐引擎尚未就绪,请稍后重试",
        )


def _dump_filters(filters: EvalFilters | None) -> dict | None:
    if filters is None:
        return None
    d = filters.model_dump(exclude_none=True)
    return d or None


@router.post("/retrieve", response_model=EvalRetrieveResponse)
async def eval_retrieve(
    req: EvalRetrieveRequest,
    pipeline=Depends(get_pipeline),
):
    """仅检索：返回父文档列表（含 text / metadata / relevance）

    用于 LlamaIndex RetrieverEvaluator 计算 Hit Rate / MRR / Precision。
    """
    _ensure_ready(pipeline)

    filters_dict = _dump_filters(req.filters)
    retriever = pipeline._retriever

    try:
        docs = await asyncio.to_thread(
            retriever.retrieve, req.query, req.top_k, filters_dict
        )
    except Exception:
        logger.exception("eval/retrieve 执行失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="检索失败",
        )

    items = [
        EvalRetrieveItem(
            recipe_id=str(d.get("recipe_id", "")),
            text=d.get("text", "") or "",
            metadata=d.get("metadata") or {},
            relevance=float(d.get("relevance", 0.0)),
            matched_chunks=int(d.get("matched_chunks", 0)),
        )
        for d in docs
    ]
    return EvalRetrieveResponse(results=items)


@router.post("/query", response_model=EvalQueryResponse)
async def eval_query(
    req: EvalQueryRequest,
    pipeline=Depends(get_pipeline),
):
    """检索 + 生成:返回 answer、contexts 和 sources。

    - contexts: 父文档文本列表(pipeline.query 已随 sources 一并返回,不再二次检索)
    - sources:  与 /api/recommend 对齐的 sources(含 recipe_id/title/relevance 等)
    """
    _ensure_ready(pipeline)

    filters_dict = _dump_filters(req.filters)

    try:
        result = await asyncio.to_thread(
            pipeline.query, req.query, filters_dict
        )
    except Exception as e:
        logger.exception(
            "eval/query 执行失败: query=%r filters=%r error=%s",
            req.query, filters_dict, e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成失败: {type(e).__name__}: {e}",
        )

    contexts = [c for c in (result.get("contexts") or []) if c]

    return EvalQueryResponse(
        answer=result.get("answer", "") or "",
        contexts=contexts,
        sources=result.get("sources", []) or [],
    )
