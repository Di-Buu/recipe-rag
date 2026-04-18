"""
JWT 生成/验证与密码哈希工具

提供用户认证所需的核心安全功能：
- JWT Token 的生成与解析
- 密码的哈希与验证（bcrypt）
"""

from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from src.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_DAYS

# 密码哈希上下文（使用 bcrypt 方案）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """将明文密码哈希为 bcrypt 密文"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


def create_token(user_id: int, username: str) -> str:
    """生成 JWT Token

    Args:
        user_id: 用户 ID
        username: 用户名

    Returns:
        编码后的 JWT 字符串
    """
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """解析 JWT Token

    Args:
        token: JWT 字符串

    Returns:
        解析成功返回 payload 字典，失败返回 None
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None
