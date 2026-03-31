# 食谱推荐系统（RAG）

基于检索增强生成（RAG）的智能食谱推荐系统。

## 技术栈

- **RAG 框架**：LlamaIndex
- **向量数据库**：Qdrant（本地持久化模式）
- **Embedding 模型**：Qwen3-Embedding-0.6B（本地）
- **LLM**：通义千问 Qwen API（DashScope）
- **主营养数据源**：中国食物成分表（Excel，离线预处理后本地查询）
- **营养补全接口**：FatSecret API（仅在本地缺失食材时按需调用）
- **Web UI**：Gradio

## 营养数据策略

- 采用“预处理优先，在线补全兜底”的策略。
- 优先使用中国食物成分表构建本地营养库，减少在线调用次数。
- 用户发起营养约束查询时，先查本地营养库；仅对缺失食材调用 FatSecret。
- FatSecret 返回结果会回写到本地缓存，后续同类查询直接复用。

## 环境准备

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入你的 DashScope API Key：

```bash
cp .env.example .env
```

```
DASHSCOPE_API_KEY=你的API Key
```

### 3. Embedding 模型

确保本地已下载 Qwen3-Embedding-0.6B 模型到 `D:\models\Qwen3-Embedding-0.6B`。

## 使用方法

### 第一步：构建索引（首次使用必须执行）

```bash
# 用少量数据测试（推荐先用 50 条验证）
python -m src.cli.main --build --limit 50

# 构建全量索引（155 万条，耗时较长）
python -m src.cli.main --build
```

### 第二步：启动 Web UI

```bash
python -m src.cli.main --ui
```

启动后会输出类似：

```
Running on local URL:  http://127.0.0.1:7860
```

浏览器打开该地址即可使用。

### 其他命令

```bash
# 单次查询（CLI 模式，调试用）
python -m src.cli.main --query "红烧肉怎么做"

# 默认行为（不加参数 = 启动 Web UI）
python -m src.cli.main
```

## 项目结构

```
src/
├── config.py              # 全局配置（路径、模型、参数）
├── data/
│   └── loader.py          # 食谱数据加载与文档构建
├── pipeline/
│   └── rag_pipeline.py    # RAG 核心流程（索引构建、查询）
├── ui/
│   └── app.py             # Gradio Web 界面
└── cli/
    └── main.py            # 命令行入口
```
