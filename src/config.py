"""
灵燕知识库自动化工具 - 配置文件
===================================

所有可配置参数都在这里定义。
可复制此文件为 config_local.py 进行本地修改（不会被git跟踪）。

使用方式：
    from src.config import API_KEY, WORKSPACE_ID
"""
import os

# =============================================================================
# 项目路径配置
# =============================================================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
FAILED_RECORDS_DIR = os.path.join(DATA_DIR, "failed_records")
SUCCESS_RECORDS_DIR = os.path.join(DATA_DIR, "success_records")

# 自动创建目录
for _dir in [LOGS_DIR, DATA_DIR, FAILED_RECORDS_DIR, SUCCESS_RECORDS_DIR]:
    os.makedirs(_dir, exist_ok=True)

# =============================================================================
# API配置
# =============================================================================
API_HOST = "http://10.4.49.66:18080"
API_KEY = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMDIzY2EzZDUyY2YwNDY0N2EwM2IyN2JhMWExMmNhMDUiLCJ1c2VybmFtZSI6IjEzNjI0ODM1MTE2IiwiaXNfc3VwZXJ1c2VyIjp0cnVlLCJleHAiOjE3NzAxNzE0NTR9.WrKRQc501Uly3T-c_9V2HwYbyCg40DYyhfr_m_qzv7w"

# =============================================================================
# 工作空间配置
# =============================================================================
WORKSPACES = [
    {
        "id": "9c6857a6-f87b-4db8-8978-2f2e117f05a0",
        "name": "环北知识库",
    },
    {
        "id": "2f6118d7-20c5-48fd-8c44-b34bfab1ac30",
        "name": "第二个知识库",
    },
]

# 默认工作空间（使用第一个）
DEFAULT_WORKSPACE_ID = WORKSPACES[0]["id"]
DEFAULT_WORKSPACE_NAME = WORKSPACES[0]["name"]

# 兼容旧代码的别名
WORKSPACE_ID = DEFAULT_WORKSPACE_ID
WORKSPACE_NAME = DEFAULT_WORKSPACE_NAME

# 工作空间ID列表（元组格式，兼容旧代码）
WORKSPACE_IDS = [(ws["id"], ws["name"]) for ws in WORKSPACES]

# API基础URL
BASE_URL = f"{API_HOST}/api/v1"

# =============================================================================
# 上传配置
# =============================================================================
# 并发控制
MAX_WORKERS = 5                    # 每个任务的并发线程数
MAX_CONCURRENT_TASKS = 2           # 同时处理的任务数（几个文件夹同时上传）
REQUEST_INTERVAL = 0.5             # 请求间隔时间（秒）

# 连接错误重试
CONNECTION_RETRY_DELAY = 3         # 连接重试等待时间（秒）
MAX_CONNECTION_RETRIES = 5         # 连接错误最大重试次数

# 上传API错误重试（针对502/503/504服务器错误）
MAX_UPLOAD_RETRIES = 3             # 上传失败最大重试次数
UPLOAD_RETRY_DELAY = 10            # 上传失败重试等待时间（秒）

# PDF处理
SKIP_IMAGE_CHECK = True            # 是否跳过PDF图片检测（加快上传速度）

# 兼容旧代码的UPLOAD字典
UPLOAD = {
    "max_workers": MAX_WORKERS,
    "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
    "request_interval": REQUEST_INTERVAL,
    "connection_retry_delay": CONNECTION_RETRY_DELAY,
    "max_connection_retries": MAX_CONNECTION_RETRIES,
    "max_upload_retries": MAX_UPLOAD_RETRIES,
    "upload_retry_delay": UPLOAD_RETRY_DELAY,
    "skip_image_check": SKIP_IMAGE_CHECK,
}

# =============================================================================
# 需要跳过的文件扩展名
# =============================================================================
SKIP_EXTENSIONS = [
    # Excel表格
    '.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xltm',
    # 压缩包
    '.rar', '.zip', '.7z',
    # 网页文件
    '.htm', '.html', '.css', '.ico',
    # 视频文件
    '.mov', '.mp4', '.avi',
    # 图片文件
    '.png', '.jpg', '.jpeg', '.gif', '.bmp',
    # CAD文件
    '.dwg', '.dxf',
    # 其他
    '.wps', '.pptx', '.pdg', '.dat', '.xml',
]

# =============================================================================
# LLM模型配置（用于内容生成、索引等）
# =============================================================================
LLM_CONFIG = {
    "provider": "langgenius/openai_api_compatible/openai_api_compatible",
    "name": "deepseekv3-0324",
    "mode": "chat",
    "size": 32768,
    "completion_params": {
        "temperature": 0.2,
        "top_p": 0.75,
        "max_tokens": 8000,
    },
}

# =============================================================================
# 任务配置（FAQ生成、摘要生成等）
# =============================================================================
TASK = {
    "request_interval": 3,         # 每次成功请求后的间隔时间（秒）
    "max_retries": 1,              # 单个文档最大重试次数
    "retry_interval": 2,           # 重试间隔（秒）
    "max_concurrent": 5,           # 最大并发任务数（滑动窗口大小）
    "timeout": 120,                # 请求超时时间（秒）
    "max_wait_time": 2400,         # 单个任务最大等待时间（秒）
}

# =============================================================================
# 日志配置
# =============================================================================
LOGGING = {
    "level": "INFO",
    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    "date_format": "%Y-%m-%d %H:%M:%S",
}

# =============================================================================
# 本地扫描配置（用于scan_local_files.py）
# =============================================================================
LOCAL_SCAN = {
    # 默认扫描目录（可以是多个）
    "scan_dirs": [
        r"F:\0-智能体资料汇总收集",
        r"F:\办公室档案知识库资料1",
        r"F:\办公室档案知识库资料2",
        r"F:\办公室档案知识库资料3",
        r"F:\01 知识库答案文本",
    ],
}
