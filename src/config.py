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
API_HOST = "https://ai.yxgswater.com:18080"
API_KEY = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMDIzY2EzZDUyY2YwNDY0N2EwM2IyN2JhMWExMmNhMDUiLCJ1c2VybmFtZSI6IjEzNjI0ODM1MTE2IiwiaXNfc3VwZXJ1c2VyIjp0cnVlLCJleHAiOjE3NzI0NDQ5ODJ9.-J8hcZG_j5OQyCUABp9DnN04T7GgACt7KXE7MntziMk"

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

# =============================================================================
# 优先处理文件夹配置
# =============================================================================
# 优先处理的文件夹ID列表（用于retry_failed_tasks.py、segment_index.py、doc_summary.py）
# 如果设置了此值，会优先处理这些文件夹下的知识库，然后再处理其他文件夹
PRIORITY_FOLDER_IDS = [
    # "10aab4f5-3191-4e12-a11c-2f3c4efb8204",  # 09正式稿设计图纸汇总至20260114--已完成
    # "10aab4f5-3191-4e12-a11c-2f3c4efb8204",
    # "2b937293-4bce-4228-a795-f381bfc34b6e",
    # "d24a3f53-d00f-4463-9c15-7e665960fe46",
    # "b6977a07-3a97-4281-ab99-dc15e66d74be", # 安全管理
    # "078844da-f6f2-4659-8b95-06850bc9ee53", # 应急评估
    # "1a82209a-32b8-4090-af3d-22a905a3872d", # 应急处置
    # "f30c6fbe-1881-4fec-9da5-edfafbc2db0e", # 应急准备
    # "13cd1f5f-a51d-43db-b7aa-e14fa406f321", #安全事故管理
    # "5ce66bf4-ca6c-49d3-8ae6-dcf5b997defa", # 事故调查和处理
    # "2a12fba5-96b4-413a-b44b-26fd8c7f41f4", # 作业安全
    # "461fd079-d597-48bb-8869-626a819e12a5", # 安全教育管理
    # "127d1ee9-8086-4bb1-80ef-abffba454599", # 安全文档管理
    # "e4fc92e3-ec13-4dd0-a468-34ca7f9c16d9", # 法规法律识别
    # "aedb8b38-69c4-4aa3-bbf9-7d2507f05ef5", # 隐患排查治理
    # "65f3a554-9206-45ab-a116-c18d739edfae", #安全文化建设
    # "82d5f01f-42c6-4955-8e6c-ef7d212922ca", # 持续改进
    # "b6977a07-3a97-4281-ab99-dc15e66d74be",


    
    



]

# 是否只处理优先文件夹（如果为True，只处理PRIORITY_FOLDER_IDS指定的文件夹）
ONLY_PRIORITY_FOLDER = False

# =============================================================================
# 目标文件夹路径配置（用于只处理指定目录树下的文件）
# =============================================================================
# 目标文件夹路径，如 "08安全管理"。当设置后，只处理该路径及其子路径下的文件
# 空字符串表示不按路径过滤，处理全部
TARGET_FOLDER_PATH = "08安全管理"
# TARGET_FOLDER_PATH = ""

# 为True时，仅处理TARGET_FOLDER_PATH下的文件（忽略PRIORITY_FOLDER_IDS，只处理08安全管理目录树）
ONLY_TARGET_FOLDER = True







# =============================================================================
# 远程服务器配置（用于上传统计报告等文件）
# =============================================================================
REMOTE_SERVER = {
    "host": "10.4.49.67",
    "port": 22,
    "username": "root",
    "password": "2Vu&*6+f!adc",
    "upload_dir": "/data/need_upload_file",  # 上传目标目录
}
