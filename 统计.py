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
lingyanDataset = LingyanDataset(api_key)

response_code, datasets = lingyanDataset.list_datasets(workspace_id)
if response_code != 200:
    log.error(f"获取知识库列表失败: {response_code}, {datasets}")
    exit()

log.debug(f"获取知识库列表成功: {datasets}")

# 创建 folder_path 到 files_count 的映射字典
folder_path_to_files_count = {}

for dataset in datasets:
    name = dataset.get("name")
    id = dataset.get("id")
    folder_id = dataset.get("folder_id")
    files_count = dataset.get("files_count")

    folder_map = FolderMap.get_or_none(FolderMap.id == folder_id)
    if not folder_map:
        log.error(f"未找到目录映射: {folder_id}")
        continue
    folder_path = folder_map.folderPath
    folder_path_to_files_count[folder_path] = files_count
    log.debug(f"目录: {folder_path}, 知识库: {name}")
    log.info(f"目录: {folder_path}, 知识库: {name}, 文件数: {files_count}")

# 读取 total.csv 文件
csv_file = "total.csv"
output_rows = []

with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    for row in reader:
        if row:  # 确保行不为空
            folder_path = row[0].strip()  # 第一列是目录名
            files_count = folder_path_to_files_count.get(folder_path, "未找到")
            # 在目录名右侧添加文件数
            output_rows.append([folder_path, files_count])
            log.info(f"CSV行: {folder_path} -> 文件数: {files_count}")

# 写回 CSV 文件
with open(csv_file, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(output_rows)

log.info(f"已更新 {csv_file} 文件，共 {len(output_rows)} 行")