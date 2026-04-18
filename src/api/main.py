"""
FastAPI 应用入口

职责：
- 应用生命周期管理（启动时初始化数据库、加载食谱数据、初始化 RAG Pipeline）
- CORS 中间件配置
- 路由注册
- 生产模式下托管前端静态文件
- 健康检查端点
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.api.database import init_db
from src.api.routers import auth, recommend, recipe, preference, history
from src.config import ENRICHED_DATA_PATH

logger = logging.getLogger(__name__)

# 前端构建产物目录
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    启动时：
    1. 初始化数据库表
    2. 加载食谱数据到内存（app.state.recipes）
    3. 初始化 RAG Pipeline（加载索引）
    """
    await init_db()

    # 加载食谱数据到内存，以 did 为键构建字典
    try:
        with open(ENRICHED_DATA_PATH, "r", encoding="utf-8") as f:
            recipes_list = json.load(f)
        app.state.recipes = {str(r["did"]): r for r in recipes_list}
        logger.info("食谱数据加载完成，共 %d 条", len(app.state.recipes))
    except FileNotFoundError:
        logger.warning("食谱数据文件不存在: %s，食谱接口将不可用", ENRICHED_DATA_PATH)
        app.state.recipes = None
    except Exception:
        logger.exception("加载食谱数据失败")
        app.state.recipes = None

    # 初始化 RAG Pipeline
    app.state.pipeline = None
    try:
        from src.pipeline.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline()
        pipeline.load_index()
        app.state.pipeline = pipeline
        logger.info("RAG Pipeline 初始化成功")
    except Exception:
        logger.exception("RAG Pipeline 初始化失败，推荐功能不可用")

    yield


app = FastAPI(
    title="食谱 RAG 推荐系统",
    description="基于检索增强生成的个性化食谱推荐后端服务",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 中间件：允许 Vue 开发服务器跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(auth.router)
app.include_router(recommend.router)
app.include_router(recipe.router)
app.include_router(preference.router)
app.include_router(history.router)


@app.get("/api/health", tags=["系统"])
async def health_check():
    """健康检查端点"""
    pipeline = getattr(app.state, "pipeline", None)
    return {
        "status": "ok",
        "pipeline_ready": pipeline is not None and pipeline.is_loaded,
        "recipes_loaded": getattr(app.state, "recipes", None) is not None,
    }


# ---------- 生产模式：托管前端静态文件 ----------
if FRONTEND_DIST.is_dir():
    # 挂载静态资源（JS/CSS/图片等）
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """SPA 回退：所有非 /api 路径返回 index.html，交给 Vue Router 处理"""
        file = FRONTEND_DIST / full_path
        if file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(FRONTEND_DIST / "index.html"))

