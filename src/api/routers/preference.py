"""
用户偏好路由

提供用户偏好的获取与更新接口。
"""

import json

from fastapi import APIRouter, Depends

from src.api.schemas import UserPreference
from src.api.database import get_db
from src.api.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["偏好"])


@router.get("/preference", response_model=UserPreference)
async def get_preference(
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户偏好

    若用户尚未设置偏好，返回默认值。
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM user_preference WHERE user_id = ?",
            (current_user["id"],),
        )
        row = await cursor.fetchone()

    if row is None:
        return UserPreference()

    return UserPreference(
        exclude_ingredients=json.loads(row["exclude_ingredients"]),
        preferred_categories=json.loads(row["preferred_categories"]),
        nutrition_goals=json.loads(row["nutrition_goals"]),
        difficulty_max=row["difficulty_max"],
        costtime_max=row["costtime_max"],
    )


@router.put("/preference", response_model=UserPreference)
async def update_preference(
    pref: UserPreference,
    current_user: dict = Depends(get_current_user),
):
    """更新用户偏好

    使用 UPSERT 策略：存在则更新，不存在则插入。
    同时将用户的 is_new_user 标记设为 false。
    """
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO user_preference
                (user_id, exclude_ingredients, preferred_categories,
                 nutrition_goals, difficulty_max, costtime_max, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                exclude_ingredients = excluded.exclude_ingredients,
                preferred_categories = excluded.preferred_categories,
                nutrition_goals = excluded.nutrition_goals,
                difficulty_max = excluded.difficulty_max,
                costtime_max = excluded.costtime_max,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                current_user["id"],
                json.dumps(pref.exclude_ingredients, ensure_ascii=False),
                json.dumps(pref.preferred_categories, ensure_ascii=False),
                json.dumps(pref.nutrition_goals, ensure_ascii=False),
                pref.difficulty_max,
                pref.costtime_max,
            ),
        )
        # 设置用户为非新用户
        await db.execute(
            "UPDATE users SET is_new_user = 0 WHERE id = ?",
            (current_user["id"],),
        )
        await db.commit()

    return pref
