"""
Excel文件批量上传脚本
=====================

本脚本扫描指定目录，批量上传Excel文件到灵燕AI知识库。
与 autoUploads.py 类似，但专门处理Excel文件（.xls, .xlsx等）。

目录结构要求：
├── XXX知识库
│   ├── 表格1.xlsx
│   └── 表格2.xls
└── YYY知识库
    ├── 数据1.xlsx
    └── 数据2.xlsx

使用方法：
1. 修改下方配置区域的 base_folders（上传目录）
2. 修改 workspace_id 和 api_key
3. 运行脚本
"""

import os
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, current_thread
import logging

# 获取脚本所在目录和项目根目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# 添加核心模块到路径
sys.path.insert(0, os.path.join(project_root, '1_核心模块'))
from LingyanAi import LingyanDataset, LingyanFile
from models import FolderMap
from utils import get_file_relative_dir, list_files
from failed_records import FailedRecord, FailedRecordsManager

# 确保logs文件夹存在
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志文件名（按日期）
log_filename = os.path.join(logs_dir, f"autoUploadsExcel_{datetime.now().strftime('%Y-%m-%d')}.log")

# 创建日志格式化器
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
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("autoUploadsExcel")

# ============ 配置区域 ============
# 支持多个目录同时上传，每行一个目录路径
base_folders = [
    r'E:\0-智能体资料汇总收集\确定目录的资料',
    # r'E:\其他资料目录',          # 取消注释添加更多目录
]
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"       # 工作区id
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"    # 灵燕平台 api key
# ==================================

log.info(f"配置了 {len(base_folders)} 个上传目录")

# ============ 性能配置 ============
MAX_WORKERS = 20              # 并发线程数
# ==================================

# Excel文件扩展名
EXCEL_EXTENSIONS = ['.xlsx', '.xls', '.csv']

# 统计信息
stats = {
    'total_files': 0,
    'success_count': 0,
    'skip_count': 0,
    'error_count': 0
}
stats_lock = Lock()

# 知识库缓存
dataset_cache = {}
dataset_cache_lock = Lock()

# 初始化失败记录管理器
failed_manager = FailedRecordsManager()


def list_excel_files(root, skip_hidden=True):
    """
    列出目录下所有Excel文件
    
    Args:
        root: 根目录
        skip_hidden: 是否跳过隐藏文件
        
    Returns:
        list: Excel文件路径列表
    """
    from pathlib import Path
    
    if not isinstance(root, Path):
        root = Path(root)
    
    if not root.exists():
        raise FileNotFoundError(f"路径不存在：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"不是目录：{root}")
    
    excel_files = []
    
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        
        # 跳过隐藏文件
        if skip_hidden and any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        
        # 检查是否为Excel文件
        if p.suffix.lower() in EXCEL_EXTENSIONS:
            excel_files.append(p.as_posix())
    
    excel_files.sort()
    return excel_files


# 扫描所有配置的目录，收集Excel文件
all_files_info = []
for base_folder in base_folders:
    if not os.path.exists(base_folder):
        log.warning(f"目录不存在，跳过：{base_folder}")
        continue
    log.info(f"开始扫描目录：{base_folder}")
    files = list_excel_files(base_folder, skip_hidden=True)
    log.info(f"  发现 {len(files)} 个Excel文件")
    for f in files:
        all_files_info.append((f, base_folder))

log.info(f"扫描完成，共发现 {len(all_files_info)} 个Excel文件")


def process_file(file_info):
    """
    处理单个Excel文件的上传
    
    Args:
        file_info: 元组 (file_path, base_folder)
    """
    file_path, base_folder = file_info
    
    # 为每个线程创建独立的日志记录器
    thread_name = current_thread().name
    thread_log = logging.getLogger(f"autoUploadsExcel-{thread_name}")
    thread_log.setLevel(logging.INFO)
    if not thread_log.handlers:
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        thread_log.addHandler(file_handler)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        thread_log.addHandler(console_handler)
        thread_log.propagate = False

    # 每个线程创建自己的实例
    lingyanDataset = LingyanDataset(api_key)
    lingyanFile = LingyanFile(api_key)

    with stats_lock:
        stats['total_files'] += 1

    # file_classify是文件的分类,也是知识库的目录
    file_classify = get_file_relative_dir(file_path, base_folder)
    # 知识库名
    dataset_name = file_classify.split("/")[-1]

    thread_log.info(f"文件：{file_path}，分类目录：{file_classify}，知识库名：{dataset_name}")

    # 查找文件夹ID
    folder_map = FolderMap.get_or_none(FolderMap.folderPath == file_classify)
    folder_id = folder_map.id if folder_map else None
    if not folder_id:
        thread_log.warning(f"未找到目录映射，跳过文件上传：{file_path}，目录：{file_classify}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=os.path.basename(file_path),
            file_classify=file_classify,
            error_stage=FailedRecord.STAGE_FOLDER_NOT_FOUND,
            error_message=f"目录映射未找到，目录：{file_classify}",
            dataset_name=dataset_name,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    thread_log.info(f"准备上传文件：{file_path}，目录：{file_classify}，目录ID：{folder_id}")

    # 获取或创建知识库（使用缓存）
    dataset_id = None
    
    # 先检查缓存
    if folder_id in dataset_cache and dataset_name in dataset_cache[folder_id]:
        dataset_id = dataset_cache[folder_id][dataset_name]
        thread_log.info(f"从缓存获取知识库ID：{dataset_id}")
    
    if not dataset_id:
        with dataset_cache_lock:
            # 双重检查
            if folder_id in dataset_cache and dataset_name in dataset_cache[folder_id]:
                dataset_id = dataset_cache[folder_id][dataset_name]
            else:
                if folder_id not in dataset_cache:
                    dataset_cache[folder_id] = {}
                    response_code, datasets = lingyanDataset.list_datasets(workspace_id, folder_id)
                    if response_code != 200:
                        error_msg = f"状态码：{response_code}，错误信息：{datasets}"
                        thread_log.error(f"获取知识库列表失败：{file_path}，{error_msg}")
                        failed_manager.add_record(
                            file_path=file_path,
                            file_name=os.path.basename(file_path),
                            file_classify=file_classify,
                            error_stage=FailedRecord.STAGE_LIST_DATASETS,
                            error_message=error_msg,
                            error_code=response_code,
                            dataset_name=dataset_name,
                            folder_id=folder_id,
                        )
                        with stats_lock:
                            stats['error_count'] += 1
                        return
                    for ds in datasets:
                        dataset_cache[folder_id][ds.get("name")] = ds.get("id")
                    thread_log.info(f"已缓存 {len(datasets)} 个知识库（folder_id={folder_id}）")
                
                if dataset_name in dataset_cache[folder_id]:
                    dataset_id = dataset_cache[folder_id][dataset_name]
                    thread_log.info(f"使用已存在的知识库ID：{dataset_id}")
                else:
                    # 创建知识库
                    thread_log.info(f"知识库不存在，开始创建：{dataset_name}")
                    response_code, created_ds = lingyanDataset.create_dataset(
                        workspace_id=workspace_id,
                        name=dataset_name,
                        folder_id=folder_id,
                        description=f"自动上传Excel文件生成的知识库，目录：{file_classify}",
                    )
                    if response_code != 200:
                        error_msg = f"状态码：{response_code}，错误信息：{created_ds}"
                        thread_log.error(f"创建知识库失败：{file_path}，{error_msg}")
                        failed_manager.add_record(
                            file_path=file_path,
                            file_name=os.path.basename(file_path),
                            file_classify=file_classify,
                            error_stage=FailedRecord.STAGE_CREATE_DATASET,
                            error_message=error_msg,
                            error_code=response_code,
                            dataset_name=dataset_name,
                            folder_id=folder_id,
                        )
                        with stats_lock:
                            stats['error_count'] += 1
                        return
                    dataset_id = created_ds.get("id")
                    dataset_cache[folder_id][dataset_name] = dataset_id
                    thread_log.info(f"已创建知识库：{dataset_name}，ID：{dataset_id}")

    # 重名检测
    file_name = os.path.basename(file_path)
    file_name_without_ext = os.path.splitext(file_name)[0]
    thread_log.debug(f"开始重名检测：文件名={file_name_without_ext}，知识库ID={dataset_id}")
    response_code, response, duplicate_count = lingyanDataset.check_file(
        file_name=file_name_without_ext,
        dataset_id=dataset_id
    )
    if response_code != 200:
        error_msg = f"状态码：{response_code}，错误信息：{response}"
        thread_log.error(f"重名检测请求失败，跳过文件上传：{file_path}，{error_msg}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=file_name,
            file_classify=file_classify,
            error_stage=FailedRecord.STAGE_CHECK_FILE,
            error_message=error_msg,
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    if duplicate_count > 0:
        thread_log.warning(f"检测到重名文件，跳过文件上传：{file_path}，重复数量：{duplicate_count}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    thread_log.info(f"重名检测通过：{file_name_without_ext}")

    # 上传文件
    thread_log.info(f"开始上传文件：{file_path}")
    response_code, upload_response = lingyanFile.upload_file(
        file_path=file_path,
        file_type="dataset",
    )
    if response_code != 200:
        error_msg = f"状态码：{response_code}，错误信息：{upload_response}"
        thread_log.error(f"文件上传失败，跳过创建文档：{file_path}，{error_msg}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=file_name,
            file_classify=file_classify,
            error_stage=FailedRecord.STAGE_UPLOAD_FILE,
            error_message=error_msg,
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    upload_file_id = upload_response.get("id")
    thread_log.info(f"文件上传成功：{file_path}，文件ID：{upload_file_id}")

    # 新建文档
    thread_log.info(f"开始创建文档：文件ID={upload_file_id}，知识库ID={dataset_id}")
    response_code, newDoc = lingyanDataset.create_document(
        dataset_id=dataset_id,
        file_id=upload_file_id,
    )
    if response_code != 200:
        error_msg = f"状态码：{response_code}，错误信息：{newDoc}"
        thread_log.error(f"创建文档失败：{file_path}，{error_msg}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=file_name,
            file_classify=file_classify,
            error_stage=FailedRecord.STAGE_CREATE_DOCUMENT,
            error_message=error_msg,
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    newDocId = newDoc[0].get("id")
    thread_log.info(f"文档创建成功：文档ID={newDocId}，文件：{file_path}")

    # Excel文件处理流程：解析工作表 -> 解析表头 -> 创建任务
    thread_log.info("Excel文件：开始解析工作表和表头")

    # 步骤1：解析Excel工作表
    thread_log.info(f"开始解析Excel工作表：文件ID={upload_file_id}")
    response_code, sheets = lingyanDataset.parse_excel_sheets(
        file_id=upload_file_id,
        workspace_id=workspace_id
    )
    if response_code != 200:
        error_msg = f"状态码：{response_code}，错误信息：{sheets}"
        thread_log.error(f"解析Excel工作表失败：{file_path}，{error_msg}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=file_name,
            file_classify=file_classify,
            error_stage="parse_excel_sheets",
            error_message=error_msg,
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    if not sheets or len(sheets) == 0:
        error_msg = "Excel文件没有工作表"
        thread_log.error(f"Excel文件没有工作表：{file_path}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=file_name,
            file_classify=file_classify,
            error_stage="parse_excel_sheets",
            error_message=error_msg,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    # 默认使用第一个工作表
    first_sheet = sheets[0]
    sheet_name = first_sheet.get("name", "Sheet1")
    sheet_index = first_sheet.get("index", 0)
    thread_log.info(f"解析工作表成功：共 {len(sheets)} 个工作表，使用第一个：{sheet_name} (索引={sheet_index})")

    # 步骤2：解析Excel表头
    thread_log.info(f"开始解析Excel表头：工作表={sheet_name}，索引={sheet_index}")
    response_code, headers = lingyanDataset.parse_excel_headers(
        file_id=upload_file_id,
        workspace_id=workspace_id,
        sheet_index=sheet_index,
        header_row=[1, 1]  # 默认第1行为表头
    )
    if response_code != 200:
        error_msg = f"状态码：{response_code}，错误信息：{headers}"
        thread_log.error(f"解析Excel表头失败：{file_path}，{error_msg}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=file_name,
            file_classify=file_classify,
            error_stage="parse_excel_headers",
            error_message=error_msg,
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    # 构建表头列信息
    table_columns = []
    if isinstance(headers, list):
        for col in headers:
            if isinstance(col, dict):
                table_columns.append({
                    "name": col.get("name", ""),
                    "describe": col.get("describe", ""),
                    "dataType": col.get("dataType", "String"),
                })
            elif isinstance(col, str):
                table_columns.append({
                    "name": col,
                    "describe": "",
                    "dataType": "String",
                })
    
    thread_log.info(f"解析表头成功：共 {len(table_columns)} 列，列名：{[c['name'] for c in table_columns]}")

    # 步骤3：创建Excel文档处理任务
    thread_log.info(f"开始创建Excel文档处理任务：文档ID={newDocId}，知识库ID={dataset_id}，工作表={sheet_name}")
    response_code, task_response = lingyanDataset.create_excel_task(
        dataset_id=dataset_id,
        document_id=newDocId,
        sheet_name=sheet_name,
        table_columns=table_columns,
        header_range=[1, 1],
        workspace_id=workspace_id,
    )
    if response_code != 200:
        error_msg = f"状态码：{response_code}，错误信息：{task_response}"
        thread_log.error(f"创建Excel文档任务失败：{file_path}，{error_msg}")
        failed_manager.add_record(
            file_path=file_path,
            file_name=file_name,
            file_classify=file_classify,
            error_stage=FailedRecord.STAGE_CREATE_TASK,
            error_message=error_msg,
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    thread_log.info(f"Excel文档处理任务创建成功：文档ID={newDocId}，工作表={sheet_name}，文件：{file_path}")
    
    # 成功后移除失败记录
    failed_manager.remove_record(file_path)
    
    with stats_lock:
        stats['success_count'] += 1
    thread_log.info(f"✓ 文件处理完成：{file_path}")


def process_file_safe(file_info):
    """安全包装函数，捕获所有异常"""
    file_path, base_folder = file_info
    try:
        process_file(file_info)
    except Exception as e:
        thread_name = current_thread().name
        thread_log = logging.getLogger(f"autoUploadsExcel-{thread_name}")
        thread_log.setLevel(logging.INFO)
        if not thread_log.handlers:
            file_handler = logging.FileHandler(log_filename, encoding='utf-8')
            file_handler.setFormatter(log_formatter)
            thread_log.addHandler(file_handler)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(log_formatter)
            thread_log.addHandler(console_handler)
            thread_log.propagate = False
        error_msg = f"未捕获的异常：{str(e)}"
        thread_log.error(f"处理文件时发生未捕获的异常：{file_path}，错误：{str(e)}")
        file_classify = get_file_relative_dir(file_path, base_folder)
        failed_manager.add_record(
            file_path=file_path,
            file_name=os.path.basename(file_path),
            file_classify=file_classify,
            error_stage=FailedRecord.STAGE_UNKNOWN,
            error_message=error_msg,
        )
        with stats_lock:
            stats['error_count'] += 1


# 使用线程池并发处理文件
log.info(f"开始使用线程池并发处理文件，线程数：{MAX_WORKERS}")
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    list(executor.map(process_file_safe, all_files_info))

# 输出统计信息
log.info("=" * 60)
log.info(f"Excel文件处理完成！统计信息：")
log.info(f"总文件数：{stats['total_files']}")
log.info(f"成功处理：{stats['success_count']}")
log.info(f"跳过文件：{stats['skip_count']}")
log.info(f"失败文件：{stats['error_count']}")
log.info("=" * 60)

# 输出失败记录摘要
if stats['error_count'] > 0:
    failed_manager.print_summary()
    log.info(f"失败记录已保存到：{failed_manager.records_dir}")
    log.info(f"可运行 retry_failed_uploads.py 重新上传失败的文件")

# 输出每个文件夹下的Excel文件数
unique_folders = set()
for file_path, base_folder in all_files_info:
    file_classify = get_file_relative_dir(file_path, base_folder)
    unique_folders.add((file_classify, base_folder))

for folder_path, base_folder in sorted(unique_folders):
    full_path = os.path.join(base_folder, folder_path)
    if os.path.exists(full_path):
        excel_count = len(list_excel_files(full_path))
        log.info(f"文件夹：{folder_path}，Excel文件数：{excel_count}")
