"""
统一启动入口

用法：python -m src.api
"""

import uvicorn

uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
