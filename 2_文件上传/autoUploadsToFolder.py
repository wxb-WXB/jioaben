# -*- coding: utf-8 -*-
"""
指定目录上传工具

功能：
把本地文件夹中的所有文件上传到指定的远程目录（通过 folder_id 指定）

使用方法：
1. 修改下方的配置区域
2. 运行脚本

与 autoUploads.py 的区别：
- autoUploads.py：根据本地目录结构自动匹配远程目录
- 本脚本：直接指定本地文件夹 → 远程目录ID，不需要路径匹配
"""

import os
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, current_thread
import logging
import time
import requests.exceptions

# 获取脚本所在目录和项目根目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# 添加核心模块到路径
sys.path.insert(0, os.path.join(project_root, '1_核心模块'))
from LingyanAi import LingyanDataset, LingyanFile
from utils import is_pdf_file, pdf_has_images
from failed_records import FailedRecord, FailedRecordsManager, SuccessRecordsManager

# 确保logs文件夹存在
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志
log_filename = os.path.join(logs_dir, f"autoUploadsToFolder_{datetime.now().strftime('%Y-%m-%d')}.log")
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
log = logging.getLogger("autoUploadsToFolder")

# ============ 配置区域 ============
# 本地文件夹路径（会上传该文件夹下的所有文件，包括子文件夹中的文件）
LOCAL_FOLDER = r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\02先行段施工施工文件'

# 远程目录ID（从 folder.db 或平台获取）
# 示例：档案管理知识库/B1环北部湾广东水资源配置工程（档案）/02先行段施工施工文件
FOLDER_ID = "75fd2157-9386-4594-91fc-b20f3ecf45d1"

# 知识库名称（如果该目录下没有知识库，会自动创建）
DATASET_NAME = "02先行段施工施工文件"

# 工作区ID和API Key
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
# ==================================

# ============ 性能配置 ============
MAX_WORKERS = 5               # 并发线程数
SKIP_IMAGE_CHECK = True       # 是否跳过PDF图片检测
REQUEST_INTERVAL = 0.3        # 请求间隔时间（秒）
# ==================================

# ============ 过滤配置 ============
# 需要跳过的文件扩展名
SKIP_EXTENSIONS = [
    '.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xltm',  # Excel
    '.rar', '.zip', '.7z',  # 压缩包
    '.htm', '.html', '.css', '.ico',  # 网页
    '.mov', '.mp4', '.avi',  # 视频
    '.png', '.jpg', '.jpeg', '.gif', '.bmp',  # 图片
    '.dwg', '.dxf',  # CAD
    '.wps', '.pptx', '.pdg', '.dat', '.xml',  # 其他
]
# ==================================

# 统计信息
stats = {
    'total_files': 0,
    'success_count': 0,
    'skip_count': 0,
    'error_count': 0
}
stats_lock = Lock()

# 请求限流
last_request_time = 0
request_lock = Lock()

def rate_limited_sleep():
    global last_request_time
    with request_lock:
        current_time = time.time()
        elapsed = current_time - last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        last_request_time = time.time()

# 初始化记录管理器
failed_manager = FailedRecordsManager()
success_manager = SuccessRecordsManager()

# 知识库ID缓存（避免重复查询/创建）
dataset_id_cache = None
dataset_cache_lock = Lock()


def get_all_files(folder_path):
    """
    获取文件夹下所有文件（包括子文件夹）
    
    Returns:
        list: [(相对路径, 绝对路径), ...]
    """
    files = []
    for root, _, filenames in os.walk(folder_path):
        for filename in filenames:
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, folder_path)
            files.append((rel_path, abs_path))
    return files


def get_or_create_dataset(lingyanDataset):
    """
    获取或创建知识库，返回知识库ID
    """
    global dataset_id_cache
    
    with dataset_cache_lock:
        if dataset_id_cache:
            return dataset_id_cache
        
        # 查询该目录下的知识库
        log.info(f"正在查询目录下的知识库，folder_id={FOLDER_ID}")
        response_code, datasets = lingyanDataset.list_datasets(workspace_id, FOLDER_ID)
        
        if response_code != 200:
            log.error(f"获取知识库列表失败：{response_code}, {datasets}")
            return None
        
        # 查找是否已有同名知识库
        for ds in datasets:
            if ds.get("name") == DATASET_NAME:
                dataset_id_cache = ds.get("id")
                log.info(f"找到已存在的知识库：{DATASET_NAME}，ID={dataset_id_cache}")
                return dataset_id_cache
        
        # 不存在则创建
        log.info(f"知识库不存在，正在创建：{DATASET_NAME}")
        response_code, created_ds = lingyanDataset.create_dataset(
            workspace_id=workspace_id,
            name=DATASET_NAME,
            folder_id=FOLDER_ID,
            description=f"自动上传工具创建的知识库",
        )
        
        if response_code != 200:
            log.error(f"创建知识库失败：{response_code}, {created_ds}")
            return None
        
        dataset_id_cache = created_ds.get("id")
        log.info(f"知识库创建成功：{DATASET_NAME}，ID={dataset_id_cache}")
        return dataset_id_cache


def process_file(file_info):
    """
    处理单个文件
    
    Args:
        file_info: (相对路径, 绝对路径)
    """
    rel_path, abs_path = file_info
    file_name = os.path.basename(abs_path)
    
    # 线程日志
    thread_name = current_thread().name
    thread_log = logging.getLogger(f"autoUploadsToFolder-{thread_name}")
    thread_log.setLevel(logging.INFO)
    if not thread_log.handlers:
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        thread_log.addHandler(file_handler)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        thread_log.addHandler(console_handler)
        thread_log.propagate = False
    
    # 创建API实例
    lingyanDataset = LingyanDataset(api_key)
    lingyanFile = LingyanFile(api_key)
    
    with stats_lock:
        stats['total_files'] += 1
    
    # 检查是否已上传过
    if success_manager.is_uploaded(abs_path):
        thread_log.info(f"已上传过，跳过：{rel_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    
    # 检查文件扩展名
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext in SKIP_EXTENSIONS:
        thread_log.warning(f"不支持的文件类型，跳过：{rel_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    
    # 获取知识库ID
    dataset_id = get_or_create_dataset(lingyanDataset)
    if not dataset_id:
        thread_log.error(f"无法获取知识库ID，跳过：{rel_path}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            file_classify=DATASET_NAME,
            error_stage=FailedRecord.STAGE_LIST_DATASETS,
            error_message="无法获取或创建知识库",
            dataset_name=DATASET_NAME,
            folder_id=FOLDER_ID,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    # 重名检测
    rate_limited_sleep()
    file_name_without_ext = os.path.splitext(file_name)[0]
    response_code, response, duplicate_count = lingyanDataset.check_file(
        file_name=file_name_without_ext,
        dataset_id=dataset_id
    )
    
    if response_code != 200:
        thread_log.error(f"重名检测失败：{rel_path}，{response_code}, {response}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            file_classify=DATASET_NAME,
            error_stage=FailedRecord.STAGE_CHECK_FILE,
            error_message=f"重名检测失败：{response_code}, {response}",
            error_code=response_code,
            dataset_name=DATASET_NAME,
            folder_id=FOLDER_ID,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    if duplicate_count > 0:
        thread_log.warning(f"文件已存在，跳过：{rel_path}")
        success_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            dataset_id=dataset_id,
            document_id="",
        )
        with stats_lock:
            stats['skip_count'] += 1
        return
    
    # 上传文件
    thread_log.info(f"开始上传：{rel_path}")
    rate_limited_sleep()
    response_code, upload_response = lingyanFile.upload_file(
        file_path=abs_path,
        file_type="dataset",
    )
    
    if response_code != 200:
        thread_log.error(f"文件上传失败：{rel_path}，{response_code}, {upload_response}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            file_classify=DATASET_NAME,
            error_stage=FailedRecord.STAGE_UPLOAD_FILE,
            error_message=f"上传失败：{response_code}, {upload_response}",
            error_code=response_code,
            dataset_name=DATASET_NAME,
            folder_id=FOLDER_ID,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    upload_file_id = upload_response.get("id")
    thread_log.info(f"文件上传成功：{rel_path}，文件ID={upload_file_id}")
    
    # 创建文档
    rate_limited_sleep()
    response_code, newDoc = lingyanDataset.create_document(
        dataset_id=dataset_id,
        file_id=upload_file_id,
    )
    
    if response_code != 200:
        thread_log.error(f"创建文档失败：{rel_path}，{response_code}, {newDoc}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            file_classify=DATASET_NAME,
            error_stage=FailedRecord.STAGE_CREATE_DOCUMENT,
            error_message=f"创建文档失败：{response_code}, {newDoc}",
            error_code=response_code,
            dataset_name=DATASET_NAME,
            folder_id=FOLDER_ID,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    newDocId = newDoc[0].get("id")
    thread_log.info(f"文档创建成功：{rel_path}，文档ID={newDocId}")
    
    # PDF处理配置
    is_pdf = is_pdf_file(abs_path)
    if SKIP_IMAGE_CHECK:
        has_img = False
    else:
        try:
            has_img = pdf_has_images(abs_path) if is_pdf else False
        except:
            has_img = False
    
    # 创建任务
    rate_limited_sleep()
    response_code, task_response = lingyanDataset.create_task(
        dataset_id,
        newDocId,
        image_task=has_img,
        parse_enhance=is_pdf
    )
    
    if response_code != 200:
        thread_log.error(f"创建任务失败：{rel_path}，{response_code}, {task_response}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            file_classify=DATASET_NAME,
            error_stage=FailedRecord.STAGE_CREATE_TASK,
            error_message=f"创建任务失败：{response_code}, {task_response}",
            error_code=response_code,
            dataset_name=DATASET_NAME,
            folder_id=FOLDER_ID,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
        return
    
    # 成功
    failed_manager.remove_record(abs_path)
    success_manager.add_record(
        file_path=abs_path,
        file_name=file_name,
        dataset_id=dataset_id,
        document_id=newDocId,
    )
    
    with stats_lock:
        stats['success_count'] += 1
    thread_log.info(f"✅ 上传完成：{rel_path}")


def process_file_safe(file_info):
    """安全包装，捕获异常"""
    try:
        process_file(file_info)
    except Exception as e:
        rel_path, abs_path = file_info
        log.error(f"处理文件时发生异常：{rel_path}，错误：{str(e)}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=os.path.basename(abs_path),
            file_classify=DATASET_NAME,
            error_stage=FailedRecord.STAGE_UNKNOWN,
            error_message=f"未知错误：{str(e)}",
        )
        with stats_lock:
            stats['error_count'] += 1


def main():
    print("=" * 60)
    print("指定目录上传工具")
    print("=" * 60)
    
    # 检查配置
    if not os.path.exists(LOCAL_FOLDER):
        log.error(f"本地文件夹不存在：{LOCAL_FOLDER}")
        return
    
    if FOLDER_ID == "从check_folder_match.py输出或平台获取":
        log.error("请先配置 FOLDER_ID！")
        log.info("运行 check_folder_match.py 搜索目录ID，或从平台获取")
        return
    
    log.info(f"本地文件夹：{LOCAL_FOLDER}")
    log.info(f"远程目录ID：{FOLDER_ID}")
    log.info(f"知识库名称：{DATASET_NAME}")
    
    # 扫描文件
    log.info("正在扫描本地文件...")
    files = get_all_files(LOCAL_FOLDER)
    log.info(f"找到 {len(files)} 个文件")
    
    if not files:
        log.warning("没有找到文件，退出")
        return
    
    # 显示文件列表预览
    log.info("文件列表预览（前10个）：")
    for rel_path, _ in files[:10]:
        log.info(f"  - {rel_path}")
    if len(files) > 10:
        log.info(f"  ... 还有 {len(files) - 10} 个文件")
    
    # 确认上传
    print("\n" + "=" * 60)
    confirm = input("确认开始上传？(y/n): ").strip().lower()
    if confirm != 'y':
        log.info("用户取消上传")
        return
    
    # 开始上传
    log.info(f"开始上传，线程数：{MAX_WORKERS}")
    log.info(f"已加载 {success_manager.get_count()} 条成功记录")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(process_file_safe, files))
    
    # 保存记录
    success_manager.flush()
    
    # 输出统计
    print("\n" + "=" * 60)
    log.info("上传完成！统计信息：")
    log.info(f"  总文件数：{stats['total_files']}")
    log.info(f"  成功上传：{stats['success_count']}")
    log.info(f"  跳过文件：{stats['skip_count']}")
    log.info(f"  失败文件：{stats['error_count']}")
    
    if stats['error_count'] > 0:
        failed_manager.print_summary()
        log.info(f"失败记录已保存到：{failed_manager.records_dir}")


if __name__ == "__main__":
    main()
