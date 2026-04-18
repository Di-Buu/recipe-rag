"""
食谱数据服务接口测试

覆盖场景：
- 食谱详情查询（正常/不存在）
- 随机推荐（默认数量/指定数量/边界值）
- 筛选选项（分类/难度/耗时/营养标签）
- 未登录访问拒绝

验证命令: .venv\\Scripts\\python.exe -m pytest tests/test_api/test_recipe.py -v
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from src.api.main import app

# =============================================================================
# 测试用食谱样本数据
# =============================================================================

SAMPLE_RECIPES = [
    {
        "did": "100001",
        "title": "番茄炒蛋",
        "zid": "家常菜",
        "tags": ["家常菜", "快手菜"],
        "desc": "经典的番茄炒蛋，酸甜可口，营养丰富，是一道老少皆宜的家常菜。这道菜做法简单，十分钟即可上桌。",
        "difficulty": 1,
        "costtime": "10分钟内",
        "tip": "番茄要选熟透的，炒蛋时火不要太大",
        "ingredients_raw": ["番茄", "鸡蛋", "盐", "糖"],
        "quantities": ["2个", "3个", "适量", "少许"],
        "steps": ["打散鸡蛋", "切番茄", "炒蛋", "加入番茄翻炒"],
        "step_pics": ["http://example.com/1.jpg", "http://example.com/2.jpg"],
        "thumb": "http://example.com/thumb1.jpg",
        "videourl": "",
        "viewnum": 50000,
        "favnum": 12000,
        "ingredient_nutrition": [{"name": "番茄", "energy": 18.0}],
        "nutrition_summary": {"energy": 150.0, "protein": 12.0},
        "nutrition_tags": ["低卡", "高蛋白"],
        "nutrition_coverage": 0.85,
        "nutrition_confidence": "可信",
    },
    {
        "did": "100002",
        "title": "红烧肉",
        "zid": "家常菜",
        "tags": ["家常菜", "硬菜"],
        "desc": "肥而不腻的红烧肉",
        "difficulty": 3,
        "costtime": "1-2小时",
        "tip": "小火慢炖才入味",
        "ingredients_raw": ["五花肉", "冰糖", "酱油", "料酒"],
        "quantities": ["500g", "30g", "2勺", "1勺"],
        "steps": ["切块焯水", "炒糖色", "放入肉块", "加调料炖煮"],
        "step_pics": [],
        "thumb": "http://example.com/thumb2.jpg",
        "videourl": "",
        "viewnum": 80000,
        "favnum": 20000,
        "ingredient_nutrition": [],
        "nutrition_summary": None,
        "nutrition_tags": [],
        "nutrition_coverage": 0.0,
        "nutrition_confidence": "不可信",
    },
    {
        "did": "100003",
        "title": "清蒸鲈鱼",
        "zid": "海鲜",
        "tags": ["海鲜", "蒸菜"],
        "desc": "鲜嫩可口的清蒸鲈鱼，保留了鱼肉的原汁原味",
        "difficulty": 2,
        "costtime": "30-60分钟",
        "tip": "蒸鱼时间不要过长",
        "ingredients_raw": ["鲈鱼", "葱", "姜", "蒸鱼豉油"],
        "quantities": ["1条", "2根", "1块", "适量"],
        "steps": ["处理鲈鱼", "摆盘蒸制", "浇热油"],
        "step_pics": [],
        "thumb": "http://example.com/thumb3.jpg",
        "videourl": "http://example.com/video.mp4",
        "viewnum": 30000,
        "favnum": 8000,
        "ingredient_nutrition": [{"name": "鲈鱼", "protein": 18.0}],
        "nutrition_summary": {"energy": 120.0, "protein": 18.0},
        "nutrition_tags": ["高蛋白", "低脂"],
        "nutrition_coverage": 0.9,
        "nutrition_confidence": "可信",
    },
]


@pytest_asyncio.fixture(autouse=True)
async def inject_sample_recipes():
    """在每个测试前注入样本食谱数据到 app.state"""
    app.state.recipes = {str(r["did"]): r for r in SAMPLE_RECIPES}
    yield
    # 清理
    app.state.recipes = None


# =============================================================================
# 食谱详情接口测试
# =============================================================================


class TestGetRecipe:
    """GET /api/recipe/{recipe_id} 测试"""

    @pytest.mark.asyncio
    async def test_get_recipe_success(self, client: AsyncClient, auth_headers: dict):
        """正常获取食谱详情"""
        resp = await client.get("/api/recipe/100001", headers=auth_headers)
        assert resp.status_code == 200

        data = resp.json()
        assert data["did"] == "100001"
        assert data["title"] == "番茄炒蛋"
        assert data["category"] == "家常菜"
        assert data["difficulty"] == 1
        assert data["difficulty_text"] == "一般"
        assert data["costtime"] == "10分钟内"
        assert len(data["ingredients_raw"]) == 4
        assert len(data["steps"]) == 4
        assert data["thumb"] == "http://example.com/thumb1.jpg"
        assert data["viewnum"] == 50000
        assert "低卡" in data["nutrition_tags"]
        assert data["nutrition_coverage"] == 0.85

    @pytest.mark.asyncio
    async def test_get_recipe_not_found(self, client: AsyncClient, auth_headers: dict):
        """查询不存在的食谱返回 404"""
        resp = await client.get("/api/recipe/999999", headers=auth_headers)
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_recipe_unauthorized(self, client: AsyncClient):
        """未登录访问返回 401"""
        resp = await client.get("/api/recipe/100001")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_get_recipe_difficulty_mapping(self, client: AsyncClient, auth_headers: dict):
        """难度映射正确：difficulty=3 → '困难'"""
        resp = await client.get("/api/recipe/100002", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["difficulty_text"] == "困难"

    @pytest.mark.asyncio
    async def test_get_recipe_with_video(self, client: AsyncClient, auth_headers: dict):
        """含视频链接的食谱"""
        resp = await client.get("/api/recipe/100003", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["videourl"] == "http://example.com/video.mp4"


# =============================================================================
# 随机推荐接口测试
# =============================================================================


class TestRandomRecipes:
    """GET /api/recipes/random 测试"""

    @pytest.mark.asyncio
    async def test_random_default_count(self, client: AsyncClient, auth_headers: dict):
        """默认返回数量（样本只有3条，返回3条）"""
        resp = await client.get("/api/recipes/random", headers=auth_headers)
        assert resp.status_code == 200

        data = resp.json()
        # 样本只有3条，请求默认6条，实际返回 min(6, 3) = 3
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_random_with_count(self, client: AsyncClient, auth_headers: dict):
        """指定数量 count=2"""
        resp = await client.get("/api/recipes/random?count=2", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_random_count_one(self, client: AsyncClient, auth_headers: dict):
        """最少返回1条"""
        resp = await client.get("/api/recipes/random?count=1", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_random_card_fields(self, client: AsyncClient, auth_headers: dict):
        """卡片字段完整性检查"""
        resp = await client.get("/api/recipes/random?count=1", headers=auth_headers)
        assert resp.status_code == 200

        card = resp.json()[0]
        expected_fields = {
            "did", "title", "category", "difficulty", "difficulty_text",
            "costtime", "thumb", "viewnum", "favnum", "nutrition_tags",
            "desc_preview",
        }
        assert expected_fields.issubset(set(card.keys()))

    @pytest.mark.asyncio
    async def test_random_desc_preview_truncated(self, client: AsyncClient, auth_headers: dict):
        """desc_preview 不超过50字"""
        resp = await client.get("/api/recipes/random?count=3", headers=auth_headers)
        for card in resp.json():
            assert len(card["desc_preview"]) <= 50

    @pytest.mark.asyncio
    async def test_random_count_exceed_max(self, client: AsyncClient, auth_headers: dict):
        """count 超过上限20时返回422"""
        resp = await client.get("/api/recipes/random?count=21", headers=auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_random_count_zero(self, client: AsyncClient, auth_headers: dict):
        """count=0 返回422"""
        resp = await client.get("/api/recipes/random?count=0", headers=auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_random_unauthorized(self, client: AsyncClient):
        """未登录访问返回 401"""
        resp = await client.get("/api/recipes/random")
        assert resp.status_code in (401, 403)


# =============================================================================
# 筛选选项接口测试
# =============================================================================


class TestFilterOptions:
    """GET /api/filters/options 测试"""

    @pytest.mark.asyncio
    async def test_filter_options_success(self, client: AsyncClient, auth_headers: dict):
        """正常获取筛选选项"""
        resp = await client.get("/api/filters/options", headers=auth_headers)
        assert resp.status_code == 200

        data = resp.json()
        assert "categories" in data
        assert "difficulties" in data
        assert "costtimes" in data
        assert "nutrition_tags" in data

    @pytest.mark.asyncio
    async def test_filter_categories_sorted_by_count(self, client: AsyncClient, auth_headers: dict):
        """分类按数量降序排列（来源于 tags 字段）"""
        resp = await client.get("/api/filters/options", headers=auth_headers)
        categories = resp.json()["categories"]

        # 样本 tags: ["家常菜","快手菜"], ["家常菜","硬菜"], ["海鲜","蒸菜"]
        # 家常菜=2, 快手菜=1, 硬菜=1, 海鲜=1, 蒸菜=1
        assert len(categories) == 5
        assert categories[0]["value"] == "家常菜"
        assert categories[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_filter_difficulties(self, client: AsyncClient, auth_headers: dict):
        """难度选项包含4个等级"""
        resp = await client.get("/api/filters/options", headers=auth_headers)
        difficulties = resp.json()["difficulties"]

        assert len(difficulties) == 4
        assert difficulties[0] == {"value": 0, "label": "简单"}
        assert difficulties[3] == {"value": 3, "label": "困难"}

    @pytest.mark.asyncio
    async def test_filter_costtimes(self, client: AsyncClient, auth_headers: dict):
        """耗时选项为预定义4项"""
        resp = await client.get("/api/filters/options", headers=auth_headers)
        costtimes = resp.json()["costtimes"]

        assert len(costtimes) == 4
        assert costtimes[0] == {"value": 10, "label": "≤10分钟"}
        assert costtimes[3] == {"value": 120, "label": "≤2小时"}

    @pytest.mark.asyncio
    async def test_filter_nutrition_tags(self, client: AsyncClient, auth_headers: dict):
        """营养标签去重且排序"""
        resp = await client.get("/api/filters/options", headers=auth_headers)
        tags = resp.json()["nutrition_tags"]

        # 样本中出现的标签：低卡、高蛋白、低脂（去重后3个）
        assert "低卡" in tags
        assert "高蛋白" in tags
        assert "低脂" in tags
        assert len(tags) == 3
        # 排序检查
        assert tags == sorted(tags)

    @pytest.mark.asyncio
    async def test_filter_options_unauthorized(self, client: AsyncClient):
        """未登录访问返回 401"""
        resp = await client.get("/api/filters/options")
        assert resp.status_code in (401, 403)


# =============================================================================
# 食谱数据未加载时的降级测试
# =============================================================================


class TestRecipesNotLoaded:
    """食谱数据未加载时返回 503"""

    @pytest_asyncio.fixture(autouse=True)
    async def clear_recipes(self):
        """清除食谱数据，模拟数据未加载场景"""
        app.state.recipes = None
        yield
        # inject_sample_recipes 会在其他测试中恢复

    @pytest.mark.asyncio
    async def test_recipe_detail_503(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/recipe/100001", headers=auth_headers)
        assert resp.status_code == 503
        assert "未加载" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_random_503(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/recipes/random", headers=auth_headers)
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_filter_options_503(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/filters/options", headers=auth_headers)
        assert resp.status_code == 503
