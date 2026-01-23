"""
失败文件重试上传脚本
==================

从失败记录中读取上传失败的文件，重新进行上传。

功能：
- 读取所有失败记录
- 按失败阶段分类显示
- 支持选择性重试（可跳过目录映射未找到的文件）
- 重试成功后自动移除失败记录

使用方式：
    python retry_failed_uploads.py
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
from utils import get_file_relative_dir, is_pdf_file, pdf_has_images
from failed_records import FailedRecord, FailedRecordsManager

# 确保logs文件夹存在
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志
log_filename = os.path.join(logs_dir, f"retry_uploads_{datetime.now().strftime('%Y-%m-%d')}.log")
log_formatter = logging.Formatter(
    fmt="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("retryUploads")

# ============ 配置区域 ============
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
MAX_WORKERS = 6  # 重试时使用较少的线程数
# =================================

# 统计信息
stats = {
    'total_files': 0,
    'success_count': 0,
    'skip_count': 0,
    'error_count': 0
}
stats_lock = Lock()
dataset_lock = Lock()

# 初始化失败记录管理器
failed_manager = FailedRecordsManager()


def retry_file(record: FailedRecord, base_folder: str = None):
    """重试上传单个失败文件"""
    thread_name = current_thread().name
    thread_log = logging.getLogger(f"retryUploads-{thread_name}")
    thread_log.setLevel(logging.INFO)
    if not thread_log.handlers:
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        thread_log.addHandler(file_handler)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        thread_log.addHandler(console_handler)
        thread_log.propagate = False

    file_path = record.file_path
    file_name = record.file_name
    file_classify = record.file_classify
    dataset_name = record.dataset_name or file_classify.split("/")[-1]
    
    with stats_lock:
        stats['total_files'] += 1

    thread_log.info(f"开始重试文件：{file_path}")
    thread_log.info(f"  上次失败阶段：{record.get_stage_description()}")
    thread_log.info(f"  上次错误信息：{record.error_message}")
    thread_log.info(f"  重试次数：{record.retry_count}")

    # 检查文件是否存在
    if not os.path.exists(file_path):
        thread_log.error(f"文件不存在，跳过：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return

    # 创建API实例
    lingyanDataset = LingyanDataset(api_key)
    lingyanFile = LingyanFile(api_key)

    # 获取目录ID
    folder_id = record.folder_id
    if not folder_id:
        folder_map = FolderMap.get_or_none(FolderMap.folderPath == file_classify)
        folder_id = folder_map.id if folder_map else None
        if not folder_id:
            thread_log.error(f"仍未找到目录映射，跳过：{file_path}，目录：{file_classify}")
            with stats_lock:
                stats['skip_count'] += 1
            return

    # 获取或创建知识库
    dataset_id = record.dataset_id
    with dataset_lock:
        if not dataset_id:
            response_code, datasets = lingyanDataset.list_datasets(workspace_id, folder_id)
            if response_code != 200:
                error_msg = f"获取知识库列表失败：状态码={response_code}，{datasets}"
                thread_log.error(error_msg)
                failed_manager.add_record(
                    file_path=file_path,
                    file_name=file_name,
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
            
            dataset_names = [ds.get("name") for ds in datasets]
            if dataset_name in dataset_names:
                target_dataset = datasets[dataset_names.index(dataset_name)]
                dataset_id = target_dataset.get("id")
            else:
                # 创建知识库
                response_code, created_ds = lingyanDataset.create_dataset(
                    workspace_id=workspace_id,
                    name=dataset_name,
                    folder_id=folder_id,
                    description=f"自动上传文件生成的知识库，目录：{file_classify}",
                )
                if response_code != 200:
                    error_msg = f"创建知识库失败：状态码={response_code}，{created_ds}"
                    thread_log.error(error_msg)
                    failed_manager.add_record(
                        file_path=file_path,
                        file_name=file_name,
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
                thread_log.info(f"已创建知识库：{dataset_name}，ID：{dataset_id}")

    # 重名检测
    file_name_without_ext = os.path.splitext(file_name)[0]
    response_code, response, duplicate_count = lingyanDataset.check_file(
        file_name=file_name_without_ext,
        dataset_id=dataset_id
    )
    if response_code != 200:
        error_msg = f"重名检测失败：状态码={response_code}，{response}"
        thread_log.error(error_msg)
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
        thread_log.warning(f"检测到重名文件，跳过：{file_path}")
        # 重名不算失败，移除失败记录
        failed_manager.remove_record(file_path)
        with stats_lock:
            stats['skip_count'] += 1
        return

    # 上传文件
    thread_log.info(f"开始上传文件：{file_path}")
    response_code, upload_response = lingyanFile.upload_file(
        file_path=file_path,
        file_type="dataset",
    )
    if response_code != 200:
        error_msg = f"文件上传失败：状态码={response_code}，{upload_response}"
        thread_log.error(error_msg)
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
    thread_log.info(f"文件上传成功，文件ID：{upload_file_id}")

    # 创建文档
    response_code, newDoc = lingyanDataset.create_document(
        dataset_id=dataset_id,
        file_id=upload_file_id,
    )
    if response_code != 200:
        error_msg = f"创建文档失败：状态码={response_code}，{newDoc}"
        thread_log.error(error_msg)
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
    thread_log.info(f"文档创建成功，文档ID：{newDocId}")

    # 检测是否有图片
    has_img = False
    is_pdf = False
    try:
        has_img = pdf_has_images(file_path)
        is_pdf = is_pdf_file(file_path)
    except:
        pass

    # 创建任务
    response_code, task_response = lingyanDataset.create_task(
        dataset_id,
        newDocId,
        image_task=has_img,
        parse_enhance=is_pdf
    )
    if response_code != 200:
        error_msg = f"创建任务失败：状态码={response_code}，{task_response}"
        thread_log.error(error_msg)
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

    # 成功！移除失败记录
    failed_manager.remove_record(file_path)
    thread_log.info(f"重试成功：{file_path}")
    with stats_lock:
        stats['success_count'] += 1


def main():
    print("=" * 60)
    print("失败文件重试上传工具")
    print("=" * 60)
    
    # 显示当前失败记录统计
    failed_manager.print_summary()
    
    # 获取可重试的记录
    retryable_records = failed_manager.get_retryable_records()
    
    if len(retryable_records) == 0:
        print("没有可重试的失败记录")
        return
    
    print(f"\n找到 {len(retryable_records)} 个可重试的文件")
    
    # 询问是否继续
    user_input = input("\n是否开始重试？(y/n): ").strip().lower()
    if user_input != 'y':
        print("已取消")
        return
    
    print(f"\n开始重试，使用 {MAX_WORKERS} 个线程...")
    
    # 使用线程池重试
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(retry_file, retryable_records))
    
    # 输出统计
    print("\n" + "=" * 60)
    print("重试完成！统计信息：")
    print(f"总文件数：{stats['total_files']}")
    print(f"成功处理：{stats['success_count']}")
    print(f"跳过文件：{stats['skip_count']}")
    print(f"仍然失败：{stats['error_count']}")
    print("=" * 60)
    
    # 显示剩余失败记录
    remaining = failed_manager.get_all_records()
    if remaining:
        print(f"\n剩余 {len(remaining)} 个失败记录：")
        for r in remaining[:10]:  # 只显示前10个
            print(f"  - {r.file_name}: {r.get_stage_description()}")
        if len(remaining) > 10:
            print(f"  ... 还有 {len(remaining) - 10} 个")


if __name__ == "__main__":
    main()
