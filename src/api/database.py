"""
数据库连接与表定义

使用 aiosqlite 异步操作 SQLite，管理用户、偏好、历史记录等业务数据。
数据库文件路径：data/recipe_app.db
"""

import aiosqlite
from contextlib import asynccontextmanager

import src.config as config


# 建表 SQL
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_new_user BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
);

CREATE TABLE IF NOT EXISTS user_preference (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    exclude_ingredients TEXT DEFAULT '[]',
    preferred_categories TEXT DEFAULT '[]',
    nutrition_goals TEXT DEFAULT '[]',
    difficulty_max INTEGER DEFAULT 5,
    costtime_max INTEGER,
    updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
);

CREATE TABLE IF NOT EXISTS recommend_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    question TEXT NOT NULL,
    filters TEXT,
    answer TEXT NOT NULL,
    sources TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
);
"""


@asynccontextmanager
async def get_db():
    """获取数据库连接的异步上下文管理器

    使用示例：
        async with get_db() as db:
            await db.execute("SELECT * FROM users")
    """
    db = await aiosqlite.connect(config.APP_DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """初始化数据库，创建所有业务表

    在应用启动时调用，确保表结构存在。
    """
    async with get_db() as db:
        await db.executescript(_CREATE_TABLES_SQL)
        await db.commit()
