# 个性化食谱推荐系统（RAG）

基于检索增强生成（RAG）的个性化中文食谱推荐系统。

## 技术栈

| 组件           | 技术                                |
| -------------- | ----------------------------------- |
| RAG 框架       | LlamaIndex                          |
| 向量数据库     | Qdrant（本地持久化）                |
| Embedding 模型 | Qwen3-Embedding-0.6B（本地）        |
| LLM            | 通义千问 qwen-plus（DashScope API） |
| 营养数据源     | 食物营养 SQLite 数据库（离线查询）  |
| 后端           | FastAPI                             |
| 前端           | Vue3 + Vite + Element Plus + Pinia  |
| 认证           | JWT（30 天有效期）                  |

## 快速开始

### 1. 安装后端依赖

`ash
pip install -r requirements.txt
`

### 2. 安装前端依赖

`ash
cd frontend && npm install
`

### 3. 配置环境变量

复制 .env.example 为 .env，填入 DashScope API Key：

`DASHSCOPE_API_KEY=你的API_Key`

### 4. 确保 Embedding 模型就绪

本地需下载 Qwen3-Embedding-0.6B 模型至 D:\models\Qwen3-Embedding-0.6B。

### 5. 构建索引（首次使用）

`ash

# 测试用少量数据

python -m src.cli.main --build --limit 50

# 全量构建（约 5 万条）

python -m src.cli.main --build
`

### 6. 启动系统

#### 开发模式（前后端分离）

`ash

# 终端 1：启动后端

python -m src.api

# 终端 2：启动前端开发服务器

cd frontend && npm run dev
`

访问 http://localhost:5173

#### 生产模式（一体化部署）

`ash

# 先构建前端

cd frontend && npm run build

# 启动服务（自动托管前端静态文件）

python -m src.api
`

访问 http://localhost:8000

## 项目结构

`
src/
├── api/ # FastAPI 后端
│ ├── main.py # 应用入口 + 生命周期管理
│ ├── routers/ # API 路由（auth/recommend/recipe/preference/history）
│ ├── schemas.py # Pydantic 请求/响应模型
│ ├── database.py # SQLite 数据库
│ └── auth_utils.py # JWT + 密码哈希
├── data/ # 数据处理模块
│ ├── csv_loader.py # CSV 加载器
│ ├── csv_cleaner.py # 数据清洗管线
│ ├── nutrition_enricher.py # 营养预计算
│ ├── text_preprocessor.py # 文本清洗
│ ├── document_builder.py # 父子文本块构建
│ └── nutrition_matcher.py # 营养匹配
├── pipeline/ # RAG Pipeline
│ ├── rag_pipeline.py # 核心流程编排
│ ├── indexer.py # 索引构建
│ └── retriever.py # 混合检索
├── ui/
│ └── app.py # Gradio 备用演示界面
└── cli/
└── main.py # 命令行入口

frontend/ # Vue3 前端
├── src/
│ ├── views/ # 8 个页面
│ ├── components/ # 可复用组件
│ ├── stores/ # Pinia 状态管理
│ └── api/ # Axios 封装
└── vite.config.js
`

## API 文档

启动后端后访问 http://localhost:8000/docs 查看 Swagger 交互式文档。
