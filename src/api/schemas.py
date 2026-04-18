"""
Pydantic 请求/响应模型

定义所有 API 接口的请求体和响应体结构，用于自动校验和文档生成。
"""

from pydantic import BaseModel, Field


# =============================================================================
# 认证相关模型
# =============================================================================

class RegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=20, description="用户名，3-20字符")
    password: str = Field(..., min_length=6, max_length=50, description="密码，6-50字符")


class LoginRequest(BaseModel):
    """用户登录请求"""
    username: str
    password: str


class AuthResponse(BaseModel):
    """认证响应（注册/登录共用）"""
    token: str
    username: str
    is_new_user: bool


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=50, description="新密码，6-50字符")


# =============================================================================
# 查询相关模型（T2/T4 使用）
# =============================================================================

class QueryFilters(BaseModel):
    """查询过滤条件"""
    nutrition_tags: list[str] = []
    exclude_ingredients: list[str] = []
    include_ingredients: list[str] = []
    difficulty_max: int | None = None
    costtime_max: int | None = None
    categories: list[str] = []
    keywords: list[str] = []


class QueryRequest(BaseModel):
    """推荐查询请求"""
    question: str
    filters: QueryFilters | None = None


class RecipeSource(BaseModel):
    """检索来源食谱摘要"""
    recipe_id: str
    title: str
    relevance: float
    matched_chunks: int
    category: str
    difficulty: int
    difficulty_text: str
    costtime: str
    nutrition_tags: list[str]
    thumb: str
    viewnum: int
    favnum: int


class QueryResponse(BaseModel):
    """推荐查询响应"""
    answer: str
    sources: list[RecipeSource]
    query: str
    filters: QueryFilters | None


class RecipeDetail(BaseModel):
    """食谱详情"""
    did: str
    title: str
    category: str
    tags: list[str]
    desc: str
    difficulty: int
    difficulty_text: str
    costtime: str
    tip: str
    ingredients_raw: list[str]
    quantities: list[str]
    steps: list[str]
    step_pics: list[str]
    thumb: str
    videourl: str
    viewnum: int
    favnum: int
    ingredient_nutrition: list[dict]
    nutrition_summary: dict | None
    nutrition_tags: list[str]
    nutrition_coverage: float


# =============================================================================
# 食谱卡片与筛选选项模型
# =============================================================================

# 难度等级映射
DIFFICULTY_MAP = {
    0: "简单",
    1: "一般",
    2: "较难",
    3: "困难",
}


class RecipeCard(BaseModel):
    """食谱卡片（用于列表/随机推荐展示）"""
    did: str
    title: str
    category: str
    difficulty: int
    difficulty_text: str
    costtime: str
    thumb: str
    viewnum: int
    favnum: int
    nutrition_tags: list[str]
    desc_preview: str  # 描述前50字


class FilterOptions(BaseModel):
    """筛选选项"""
    categories: list[dict]     # [{value, label, count}] — 来自 tags(cid)
    keywords: list[dict]       # [{value, label, count}] — 来自 zid
    difficulties: list[dict]   # [{value, label}]
    costtimes: list[dict]      # [{value, label}]
    nutrition_tags: list[str]


# =============================================================================
# 用户偏好模型
# =============================================================================

class UserPreference(BaseModel):
    """用户偏好设置"""
    exclude_ingredients: list[str] = []
    preferred_categories: list[str] = []
    nutrition_goals: list[str] = []
    difficulty_max: int | None = None
    costtime_max: int | None = None


# =============================================================================
# 历史记录模型
# =============================================================================

class HistoryItem(BaseModel):
    """历史记录列表项（预览）"""
    id: int
    question: str
    filters: dict | None
    answer_preview: str
    source_count: int
    created_at: str


class HistoryDetail(BaseModel):
    """历史记录详情"""
    id: int
    question: str
    filters: dict | None
    answer: str
    sources: list[dict]
    created_at: str
