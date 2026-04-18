"""
依赖注入模块

提供 FastAPI 路由中常用的依赖项：
- get_current_user: 从 JWT Token 中提取当前登录用户
- get_pipeline: 获取 RAG Pipeline 实例
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.auth_utils import decode_token
from src.api.database import get_db

# Bearer Token 提取器
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """从请求头的 Bearer Token 中解析当前用户

    Returns:
        包含 id、username、is_new_user 的用户字典

    Raises:
        HTTPException 401: Token 无效或用户不存在
    """
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
        )

    # 安全转换 user_id 为整数，防止篡改 JWT 导致 500
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
        )

    # 查数据库确认用户存在
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, is_new_user FROM users WHERE id = ?",
            (user_id_int,),
        )
        user = await cursor.fetchone()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    return {
        "id": user["id"],
        "username": user["username"],
        "is_new_user": bool(user["is_new_user"]),
    }


def get_pipeline(request: Request):
    """从 app.state 获取 RAG Pipeline 实例

    Returns:
        Pipeline 实例，若未初始化则返回 None
    """
    return getattr(request.app.state, "pipeline", None)


def get_recipes(request: Request) -> dict:
    """获取食谱数据字典（从 app.state 中读取）

    Returns:
        以 did 为键的食谱字典

    Raises:
        HTTPException 503: 食谱数据未加载
    """
    recipes = getattr(request.app.state, "recipes", None)
    if recipes is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="食谱数据未加载",
        )
    return recipes
