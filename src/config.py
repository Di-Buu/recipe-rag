"""
全局配置模块

职责：集中管理项目配置参数
- 数据路径
- 模型配置（Embedding、LLM）
- 向量数据库配置
- 检索参数
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# =============================================================================
# 路径配置
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"

# 新数据集（豆果美食 CSV）
CSV_PATH = DATA_DIR / "caipu.csv"
CLEAN_DATA_PATH = PROCESSED_DIR / "recipes_clean.json"
ENRICHED_DATA_PATH = PROCESSED_DIR / "recipes_enriched.json"
NUTRITION_DB_PATH = PROCESSED_DIR / "food_nutrition.db"

INDEX_DIR = PROCESSED_DIR

# 父文档持久化存储路径
DOCSTORE_PATH = str(PROCESSED_DIR / "parent_docstore.json")
# BM25 索引持久化路径(pickle 格式,存整个 BM25Okapi 对象 + id_map)
BM25_INDEX_PATH = str(PROCESSED_DIR / "bm25_index.pkl")

# =============================================================================
# Qdrant 向量数据库配置
# =============================================================================

QDRANT_PATH = str(INDEX_DIR / "qdrant_db")
QDRANT_COLLECTION_NAME = "recipe_children"  # 存储子块向量

# Qdrant 连接模式: "local"(嵌入式文件,不适合大集合) 或 "server"(Docker/远程服务)
# 大于 2 万条 points 建议切 server 模式
QDRANT_MODE = os.getenv("QDRANT_MODE", "local")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# =============================================================================
# Embedding 模型配置
# =============================================================================

EMBEDDING_MODEL = r"D:\models\Qwen3-Embedding-0.6B"
EMBEDDING_DIMENSION = 1024

# =============================================================================
# LLM 配置（通义千问 DashScope）
# =============================================================================

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_MODEL = "qwen3-max"

# =============================================================================
# 评估 Judge LLM 配置
# 为规避 LLM-as-a-Judge 的 self-preference bias(Zheng et al., 2023),
# judge 选用与生成模型跨厂商、跨架构的 DeepSeek,通过 DashScope 托管调用
# =============================================================================

JUDGE_MODEL = "deepseek-v3.2-exp"
JUDGE_TEMPERATURE = 0.0    # judge 用 0 温度,保证评分一致可复现
# Faithfulness 对每道菜提取十多条 statement,附加 reason 后 JSON 可达 3000+ tokens
# 1024 会被截断导致 OUTPUT_PARSING_FAILURE,8192 给充足余量
JUDGE_MAX_TOKENS = 8192

# =============================================================================
# 检索参数
# =============================================================================

TOP_K = 5              # 最终返回的食谱数量
RETRIEVAL_TOP_K = 100  # 子块过量检索数（用于去重聚合前的候选池）

# 混合检索权重（Dense vs BM25）
DENSE_WEIGHT = 0.6     # 向量语义检索权重
BM25_WEIGHT = 0.4      # BM25 关键词检索权重

# 父文档聚合去重评分权重
DEDUP_WEIGHT_MATCH_RATIO = 0.3   # 匹配子块占比权重
DEDUP_WEIGHT_AVG_SCORE = 0.5     # 平均相似度权重
DEDUP_WEIGHT_MAX_SCORE = 0.2     # 最高相似度权重

# =============================================================================
# 文档参数
# =============================================================================

MAX_RECIPE_TEXT_LENGTH = 2000  # 单个食谱文本最大字符数（超过则截断）

# =============================================================================
# LLM 生成参数
# =============================================================================

LLM_TEMPERATURE = 0.3   # 较低温度，输出更稳定结构化
LLM_MAX_TOKENS = 2048   # 允许完整食谱输出

# =============================================================================
# Embedding 参数
# =============================================================================

EMBEDDING_MAX_LENGTH = 8192  # Qwen3-Embedding 支持 32768，从默认 512 提升
EMBEDDING_BATCH_SIZE = 64    # CPU 批量 embedding 大小

# =============================================================================
# 营养标签配置
# =============================================================================

NUTRITION_COVERAGE_THRESHOLD = 0.8   # 营养覆盖率 >= 此值才标注营养标签
NUTRITION_COVERAGE_PARTIAL = 0.5     # 覆盖率在 [partial, threshold) 之间标注"仅供参考"

NUTRITION_TAG_RULES = {
    "高蛋白": {"field": "protein", "op": ">=", "value": 15.0},
    "低脂": {"field": "fat", "op": "<=", "value": 5.0},
    "低卡": {"field": "energy", "op": "<=", "value": 100.0},
    "高碳水": {"field": "carbs", "op": ">=", "value": 50.0},
}

# =============================================================================
# JWT 认证配置
# =============================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

# =============================================================================
# Web 应用数据库配置
# =============================================================================

APP_DB_PATH = str(DATA_DIR / "recipe_app.db")
