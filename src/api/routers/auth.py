"""
认证路由

提供用户注册、登录、修改密码接口。
"""

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas import RegisterRequest, LoginRequest, AuthResponse, ChangePasswordRequest
from src.api.auth_utils import hash_password, verify_password, create_token
from src.api.database import get_db
from src.api.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    """用户注册

    创建新用户，返回 JWT Token。用户名不可重复。
    """
    async with get_db() as db:
        # 检查用户名是否已存在
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?", (req.username,)
        )
        if await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

        # 创建用户（捕获唯一约束冲突，防止并发注册的竞态条件）
        password_hash = hash_password(req.password)
        try:
            cursor = await db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (req.username, password_hash),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )
        user_id = cursor.lastrowid

    token = create_token(user_id, req.username)
    return AuthResponse(token=token, username=req.username, is_new_user=True)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """用户登录

    验证用户名和密码，返回 JWT Token 和新用户状态。
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, password_hash, is_new_user FROM users WHERE username = ?",
            (req.username,),
        )
        user = await cursor.fetchone()

    if user is None or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_token(user["id"], user["username"])
    return AuthResponse(
        token=token,
        username=user["username"],
        is_new_user=bool(user["is_new_user"]),
    )


@router.put("/password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """修改密码

    需要提供旧密码验证身份，然后更新为新密码。
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (current_user["id"],),
        )
        user = await cursor.fetchone()

        if not verify_password(req.old_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码错误",
            )

        new_hash = hash_password(req.new_password)
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, current_user["id"]),
        )
        await db.commit()

    return {"message": "密码修改成功"}
