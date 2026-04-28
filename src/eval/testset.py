"""
评估测试集（30 题，覆盖三类典型用户画像）

每题包含：
- id: 测试用例编号
- persona: 所属用户画像
- scenario: 使用场景
- query: 自然语言查询
- relevance_hints: 相关性判定线索（自动标注用）
    - title_contains: 标题应包含的关键词（任一匹配即算相关）
    - main_ingredients_any: 主要食材应包含的任一项
    - tags_any: 分类标签应包含的任一项
    - nutrition_tags_any: 营养标签应包含的任一项
- constraints: 查询附带的硬/弹性约束（可选）

自动相关性判定逻辑（metrics.py 使用）：
对 top-K 每个结果，若 metadata 满足 relevance_hints 中任一条件族即算相关。
"""

TESTSET = [
    # ================= 张女士（日常决策）10 题 =================
    {
        "id": "T01", "persona": "张女士", "scenario": "日常决策",
        "query": "简单的家常红烧肉怎么做",
        "relevance_hints": {
            "title_contains": ["红烧肉"],
            "main_ingredients_any": ["五花肉", "猪肉"],
        },
        "constraints": {},
    },
    {
        "id": "T02", "persona": "张女士", "scenario": "日常决策",
        "query": "适合孩子吃的营养早餐",
        "relevance_hints": {
            "tags_any": ["早餐", "儿童", "营养"],
        },
        "constraints": {},
    },
    {
        "id": "T03", "persona": "张女士", "scenario": "日常决策",
        "query": "30分钟内能做好的快手菜",
        "relevance_hints": {
            "tags_any": ["快手菜", "家常菜"],
        },
        "constraints": {"costtime_max": 30},
    },
    {
        "id": "T04", "persona": "张女士", "scenario": "日常决策",
        "query": "冰箱里有鸡胸肉能做什么",
        "relevance_hints": {
            "main_ingredients_any": ["鸡胸肉", "鸡肉"],
        },
        "constraints": {"include_ingredients": ["鸡胸肉"]},
    },
    {
        "id": "T05", "persona": "张女士", "scenario": "日常决策",
        "query": "天气冷了想喝汤",
        "relevance_hints": {
            "tags_any": ["汤", "羹", "炖"],
            "title_contains": ["汤", "羹"],
        },
        "constraints": {},
    },
    {
        "id": "T06", "persona": "张女士", "scenario": "日常决策",
        "query": "下饭的家常菜",
        "relevance_hints": {
            "tags_any": ["家常菜", "下饭菜"],
        },
        "constraints": {},
    },
    {
        "id": "T07", "persona": "张女士", "scenario": "日常决策",
        "query": "两人份的晚餐",
        "relevance_hints": {
            "tags_any": ["家常菜", "晚餐"],
        },
        "constraints": {},
    },
    {
        "id": "T08", "persona": "张女士", "scenario": "日常决策",
        "query": "适合周末做的硬菜",
        "relevance_hints": {
            "tags_any": ["宴客", "硬菜", "大餐"],
            "title_contains": ["红烧", "炖", "蒸"],
        },
        "constraints": {},
    },
    {
        "id": "T09", "persona": "张女士", "scenario": "日常决策",
        "query": "有土豆能做什么菜",
        "relevance_hints": {
            "main_ingredients_any": ["土豆", "马铃薯"],
        },
        "constraints": {"include_ingredients": ["土豆"]},
    },
    {
        "id": "T10", "persona": "张女士", "scenario": "日常决策",
        "query": "简单西红柿炒鸡蛋",
        "relevance_hints": {
            "title_contains": ["西红柿", "番茄", "鸡蛋"],
            "main_ingredients_any": ["西红柿", "番茄", "鸡蛋"],
        },
        "constraints": {},
    },
    # ================= 李先生（健康管理）10 题 =================
    {
        "id": "T11", "persona": "李先生", "scenario": "健康管理",
        "query": "低卡高蛋白的减脂晚餐",
        "relevance_hints": {
            "nutrition_tags_any": ["低卡", "高蛋白"],
        },
        "constraints": {"nutrition_tags": ["低卡", "高蛋白"]},
    },
    {
        "id": "T12", "persona": "李先生", "scenario": "健康管理",
        "query": "适合健身的高蛋白鸡肉餐",
        "relevance_hints": {
            "nutrition_tags_any": ["高蛋白"],
            "main_ingredients_any": ["鸡胸肉", "鸡肉"],
        },
        "constraints": {"nutrition_tags": ["高蛋白"]},
    },
    {
        "id": "T13", "persona": "李先生", "scenario": "健康管理",
        "query": "低脂牛肉做法",
        "relevance_hints": {
            "nutrition_tags_any": ["低脂"],
            "main_ingredients_any": ["牛肉"],
        },
        "constraints": {"nutrition_tags": ["低脂"]},
    },
    {
        "id": "T14", "persona": "李先生", "scenario": "健康管理",
        "query": "减脂期能吃的菜",
        "relevance_hints": {
            "nutrition_tags_any": ["低卡", "低脂"],
        },
        "constraints": {"nutrition_tags": ["低卡"]},
    },
    {
        "id": "T15", "persona": "李先生", "scenario": "健康管理",
        "query": "纯瘦肉做的菜",
        "relevance_hints": {
            "main_ingredients_any": ["里脊", "瘦肉", "鸡胸肉"],
        },
        "constraints": {},
    },
    {
        "id": "T16", "persona": "李先生", "scenario": "健康管理",
        "query": "无辣椒的川菜",
        "relevance_hints": {
            "tags_any": ["川菜"],
        },
        "constraints": {"exclude_ingredients": ["辣椒", "干辣椒"]},
    },
    {
        "id": "T17", "persona": "李先生", "scenario": "健康管理",
        "query": "高纤维蔬菜做法",
        "relevance_hints": {
            "tags_any": ["素菜", "蔬菜"],
        },
        "constraints": {},
    },
    {
        "id": "T18", "persona": "李先生", "scenario": "健康管理",
        "query": "不含花生的炒菜",
        "relevance_hints": {
            "tags_any": ["炒菜", "家常菜"],
        },
        "constraints": {"exclude_ingredients": ["花生"]},
    },
    {
        "id": "T19", "persona": "李先生", "scenario": "健康管理",
        "query": "少油的清淡菜",
        "relevance_hints": {
            "nutrition_tags_any": ["低脂"],
            "title_contains": ["清蒸", "白灼", "凉拌"],
        },
        "constraints": {"nutrition_tags": ["低脂"]},
    },
    {
        "id": "T20", "persona": "李先生", "scenario": "健康管理",
        "query": "高蛋白的鱼肉做法",
        "relevance_hints": {
            "nutrition_tags_any": ["高蛋白"],
            "main_ingredients_any": ["鱼", "鲈鱼", "带鱼", "三文鱼"],
        },
        "constraints": {"nutrition_tags": ["高蛋白"]},
    },
    # ================= 王同学(学习入门)10 题 =================
    {
        "id": "T21", "persona": "王同学", "scenario": "学习入门",
        "query": "宫保鸡丁",
        "relevance_hints": {
            "title_contains": ["宫保鸡丁"],
        },
        "constraints": {},
    },
    {
        "id": "T22", "persona": "王同学", "scenario": "学习入门",
        "query": "红烧肉",
        "relevance_hints": {
            "title_contains": ["红烧肉"],
        },
        "constraints": {},
    },
    {
        "id": "T23", "persona": "王同学", "scenario": "学习入门",
        "query": "清蒸鲈鱼",
        "relevance_hints": {
            "title_contains": ["清蒸鲈鱼"],
        },
        "constraints": {},
    },
    {
        "id": "T24", "persona": "王同学", "scenario": "学习入门",
        "query": "鱼香肉丝",
        "relevance_hints": {
            "title_contains": ["鱼香肉丝"],
        },
        "constraints": {},
    },
    {
        "id": "T25", "persona": "王同学", "scenario": "学习入门",
        "query": "麻婆豆腐",
        "relevance_hints": {
            "title_contains": ["麻婆豆腐"],
        },
        "constraints": {},
    },
    {
        "id": "T26", "persona": "王同学", "scenario": "学习入门",
        "query": "糖醋里脊",
        "relevance_hints": {
            "title_contains": ["糖醋里脊"],
        },
        "constraints": {},
    },
    {
        "id": "T27", "persona": "王同学", "scenario": "学习入门",
        "query": "蛋炒饭",
        "relevance_hints": {
            "title_contains": ["蛋炒饭"],
        },
        "constraints": {},
    },
    {
        "id": "T28", "persona": "王同学", "scenario": "学习入门",
        "query": "酸辣土豆丝",
        "relevance_hints": {
            "title_contains": ["酸辣土豆丝"],
        },
        "constraints": {},
    },
    {
        "id": "T29", "persona": "王同学", "scenario": "学习入门",
        "query": "西红柿炒蛋",
        "relevance_hints": {
            "title_contains": ["西红柿炒", "番茄炒"],
        },
        "constraints": {},
    },
    {
        "id": "T30", "persona": "王同学", "scenario": "学习入门",
        "query": "番茄牛腩",
        "relevance_hints": {
            "title_contains": ["番茄牛腩", "番茄炖牛"],
        },
        "constraints": {},
    },
]
