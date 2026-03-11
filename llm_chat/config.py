"""
LLM Chat API 配置
=================
建议将 API_KEY 移至环境变量 FLYDIYSZ_API_KEY，避免泄露
"""
import os

# API 配置
API_BASE_URL = "https://new-api.flydiysz.cn/v1"
API_KEY = os.getenv("FLYDIYSZ_API_KEY", "sk-MF9e7hSIxnucWTXCrBxgiD1VnUO8cbtecGIy1VYcvvxVjUIC")

# 默认模型（该 token 当前可用：qwen-turbo）
DEFAULT_MODEL = "qwen-turbo"
