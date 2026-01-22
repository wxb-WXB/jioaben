from datetime import datetime
import logging
import os
from LingyanAi import LingyanDataset

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
    print(f"获取知识库列表失败: {response_code}, {datasets}")
    exit()

if len(datasets) == 0 or response_code != 200:
    print(f"获取知识库列表失败: {response_code}, {datasets}")
    exit()

for dataset in datasets:
    dataset["default_process_config"] = {
        "chunk_size": 2000,
        "overlap": 50,
        "chinese_title_enhance": False,
        "process_type": "NORMAL",
        "separators": "\\n",
        "replace_spaces_tabs": False,
        "delete_url_email": False,
        "parse_enhance": True,
        "parse_toc": False,
        "index_config": {
            "title": {
                "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                "name": "deepseekv3-0324",
                "mode": "chat",
                "size": 8000,
                "completion_params": {
                    "temperature": 0.2,
                    "top_p": 0.75,
                    "frequency_penalty": 0.5,
                    "presence_penalty": 0.5,
                    "max_tokens": 512,
                },
            },
            "summary": {
                "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                "name": "deepseekv3-0324",
                "mode": "chat",
                "size": 8000,
                "completion_params": {
                    "temperature": 0.2,
                    "top_p": 0.75,
                    "frequency_penalty": 0.5,
                    "presence_penalty": 0.5,
                    "max_tokens": 512,
                },
            },
            "question": {
                "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                "name": "deepseekv3-0324",
                "mode": "chat",
                "size": 8000,
                "completion_params": {
                    "temperature": 0.2,
                    "top_p": 0.75,
                    "frequency_penalty": 0.5,
                    "presence_penalty": 0.5,
                    "max_tokens": 512,
                },
            },
        },
        "md_split_by_headers": False,
        "md_max_header_level": 3,
        "doc_summary": True,
        "doc_summary_config": {
            "provider": "langgenius/openai_api_compatible/openai_api_compatible",
            "name": "deepseekv3-0324",
            "mode": "chat",
            "size": 8000,
            "completion_params": {
                "temperature": 0.2,
                "top_p": 0.75,
                "frequency_penalty": 0.5,
                "presence_penalty": 0.5,
                "max_tokens": 512,
            },
        },
        "segment_type": "semantic",
    }
    # 修改dataset
    response_code, response = lingyanDataset.update_dataset(dataset)
    if response_code != 200:
        log.error(f"更新知识库配置失败: {response_code}, {response}")
        continue
    log.info(f"更新知识库配置成功: {response}")
pass
