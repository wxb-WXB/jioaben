from datetime import datetime
import logging
import os
import csv
from LingyanAi import LingyanDataset
from models import FolderMap

# 确保logs文件夹存在
logs_dir = "logs"
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志文件名（按日期）
log_filename = os.path.join(
    logs_dir, f"batchUpdateDatasetConfig_{datetime.now().strftime('%Y-%m-%d')}.log"
)

# 创建日志格式化器（供所有日志记录器使用）
log_formatter = logging.Formatter(
    fmt="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),  # 文件处理器
        logging.StreamHandler(),  # 控制台处理器
    ],
)
log = logging.getLogger("batchUpdateDatasetConfig")

api_key = "sk-mZaD8UalsAxMa9E87rn2zmptaeu0XW2wH7LkcKxS"
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"
dataset_id = "11076740-a2e7-416a-b9de-efdfc9facf21"

lingyanDataset = LingyanDataset(api_key)

status_code, documents = lingyanDataset.list_documents(dataset_id)
if status_code != 200:
    log.error(f"获取文档列表失败: {status_code}, {documents}")
    exit()

for document in documents:
    file_id = document.get("file_id")
