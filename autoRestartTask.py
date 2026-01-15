from datetime import datetime
import logging
import os
import requests

from LingyanAi import LingyanDataset

logs_dir = "logs"
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志文件名（按日期）
log_filename = os.path.join(logs_dir, f"autoRestartTask_{datetime.now().strftime('%Y-%m-%d')}.log")

# 创建日志格式化器（供所有日志记录器使用）
log_formatter = logging.Formatter(
    fmt="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),  # 文件处理器
        logging.StreamHandler()  # 控制台处理器
    ]
)
log = logging.getLogger("autoRestartTask")

workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"
api_key = "sk-mZaD8UalsAxMa9E87rn2zmptaeu0XW2wH7LkcKxS"

headers = {
    "X-API-Key": api_key
}

lingyanDataset = LingyanDataset(api_key)
response_code, datasets = lingyanDataset.list_datasets(workspace_id)
if response_code != 200:
    log.error(f"获取知识库列表失败: {response_code}, {datasets}")
    exit()

for dataset in datasets:
    log.info(f"处理知识库: {dataset.get("name")}")
    # 查看文档
    url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset.get("id")}/documents"

    query = {
        "page_size": 2000
    }

    response = requests.get(url, headers=headers)
    for data in response.json().get("data"):
        document_id = data.get("id")
        if data.get("segment_count") == 0:
            # 如果没有切片,创建任务
            response_code, response = lingyanDataset.create_task(dataset.get("id"), document_id)
            if response_code != 200:
                log.error(f"创建任务失败: {response_code}, {response}")
                continue
            log.info(f"创建任务成功: {response}")
