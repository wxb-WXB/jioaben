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
# 批量上传配置：每个字典包含一个上传任务
# - local_folder: 本地文件夹路径
# - folder_id: 远程目录ID（从 folder.db 或平台获取）
# - dataset_name: 知识库名称（如果不存在会自动创建）
UPLOAD_TASKS = [
    # 已传完：总数：2781
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\02先行段施工施工文件',
    #     "folder_id": "75fd2157-9386-4594-91fc-b20f3ecf45d1",
    #     "dataset_name": "02先行段施工施工文件",
    # },
    # 已传完：总数：17697
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\03土建A1施工文件',
    #     "folder_id": "eb7d5b3b-a8ef-4622-9cfb-e32239e299ec",
    #     "dataset_name": "03土建A1施工文件",
    # },
    # 已上传：总数：7091
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\04土建A2施工文件',
    #     "folder_id": "a0f17c82-8442-4e0e-8b44-06a687383c83",
    #     "dataset_name": "04土建A2施工文件",
    # },
    # 已上传：总数：11115
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\05土建A3施工文件',
    #     "folder_id": "2bfa4cd1-0f28-4077-82d8-85f611efa92a",
    #     "dataset_name": "05土建A3施工文件",
    # },
    # 总数：5903
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\06土建A4施工文件',
    #     "folder_id": "7c122d22-37cf-4efc-a556-63b64ce21a04",
    #     "dataset_name": "06土建A4施工文件",
    # },
    # 总数：11395
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\07土建A5施工文件',
    #     "folder_id": "f7ca95e3-69c2-4efb-a2a9-80cb3a9d5a26",
    #     "dataset_name": "07土建A5施工文件",
    # },
    # 总数：11395
     {
        "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\08土建A6施工文件',
        "folder_id": "d9439792-b847-4466-923b-2c5b46f2847b",
        "dataset_name": "08土建A6施工文件",
    },
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\09土建A7施工文件',
    #     "folder_id": "3a4523b1-c495-432a-b0dd-feeb60bc9600",
    #     "dataset_name": "09土建A7施工文件",
    # },
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\10土建B1施工文件',
    #     "folder_id": "f4b75b0f-f53c-41c6-9471-0fbc5015c9fa",
    #     "dataset_name": "10土建B1施工文件",
    # },
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\11土建B2施工文件',
    #     "folder_id": "92ef6fbe-815e-4e1d-8cc8-20ae62bd2700",
    #     "dataset_name": "11土建B2施工文件",
    # },
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\12土建B3施工文件',
    #     "folder_id": "b85d37f0-6a79-4948-984c-e4f92716bbcb",
    #     "dataset_name": "12土建B3施工文件",
    # },
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\13土建B4施工文件',
    #     "folder_id": "a832949d-6946-40fc-b326-a5d94504e218",
    #     "dataset_name": "13土建B4施工文件",
    # },
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\14土建C1施工文件',
    #     "folder_id": "f7a3d711-f03f-46c3-bbd2-72c7c8d10197",
    #     "dataset_name": "14土建C1施工文件",
    # },
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\15土建C2施工文件',
    #     "folder_id": "ca8036d3-ef54-49e2-b6be-8a9d9af98369",
    #     "dataset_name": "15土建C2施工文件",
    # },
    # 开始传-暂停
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\16土建D1施工文件',
    #     "folder_id": "9260f6d0-136d-4a28-9e22-ac8b1b2359df",
    #     "dataset_name": "16土建D1施工文件",
    # },
    #   # 开始传-暂停
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\17土建D2施工文件',
    #     "folder_id": "3440be43-94b7-4db7-bbc2-a8c1b57c1431",
    #     "dataset_name": "17土建D2施工文件",
    # },
    # # 开始传----上传中--个文件-23888-还没传完-暂停
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\18土建D3施工文件',
    #     "folder_id": "c5fc7625-82f2-45e2-a538-765b835e0755",
    #     "dataset_name": "18土建D3施工文件",
    # },
    # # 已确认----已上传--个文件-还没传完-服务器压力大
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\19土建D4施工文件',
    #     "folder_id": "7b25720a-260c-42c4-8556-a9ffe1ef1c85",
    #     "dataset_name": "19土建D4施工文件",
    # },
     # # 已确认----已上传--966个文件-成功上传 -------
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\20安全监测01标',
    #     "folder_id": "3979fc59-2256-40cf-882b-a284588fc659",
    #     "dataset_name": "20安全监测01标",
    # },
    # # 已确认----已上传--358个文件-成功上传 -------有问题-待处理
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\21安全监测02标',
    #     "folder_id": "6331f863-f6f4-4535-b281-e7c763e60ebb",
    #     "dataset_name": "21安全监测02标",
    # },
    # 已确认----已上传--891个文件-成功上传 595 跳过文件 295 失败 1
    #   {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\22安全监测03标',
    #     "folder_id": "ddae4a90-dc50-4310-940d-50465739bddb",
    #     "dataset_name": "22安全监测03标",
    # },
    # 已确认----已上传--1401个文件-成功上传 1359
    # {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\23安全监测04标',
    #     "folder_id": "b5c18d5d-1df0-4120-a7fd-f1225668cd87",
    #     "dataset_name": "23安全监测04标",
    # },
    # 已确认----已传完--99个文件
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\26临时用电施工项目',
    #     "folder_id": "c80561a7-7a91-4564-81f9-16037e988557",
    #     "dataset_name": "26临时用电施工项目",
    # },
    # 已确认----已传完--26个文件
    #  {
    #     "local_folder": r'E:\环北部湾广东水资源配置工程\B项目档案\B1环北部湾广东水资源配置工程\B1.2施工管理\27穿铁项目',
    #     "folder_id": "b00baecd-d3a4-4f7a-87c6-e404bc7d1130",
    #     "dataset_name": "27穿铁项目",
    # },
     
]

# 工作区ID和API Key
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
# ==================================

# ============ 运行模式 ============
# "check"  - 只检查上传情况，不上传
# "upload" - 直接上传（跳过已上传的文件）
# "both"   - 先检查，确认后再上传
RUN_MODE = "upload"
# ==================================

# ============ 性能配置 ============
MAX_WORKERS = 4               # 每个任务的并发线程数（降低并发避免503）
MAX_CONCURRENT_TASKS = 2      # 同时处理的任务数
SKIP_IMAGE_CHECK = True       # 是否跳过PDF图片检测
REQUEST_INTERVAL = 0.5        # 请求间隔时间（秒）
CONNECTION_RETRY_DELAY = 3    # 连接被拒绝时的重试等待时间（秒）
MAX_CONNECTION_RETRIES = 5    # 连接错误最大重试次数
MAX_UPLOAD_RETRIES = 3        # 上传失败最大重试次数（针对503等错误）
UPLOAD_RETRY_DELAY = 10       # 上传失败重试等待时间（秒）
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
    'error_count': 0,
    'pending_total': 0,      # 待上传总数
    'processed_count': 0,    # 已处理数（成功+跳过+失败）
    'start_time': None,      # 开始时间
}
stats_lock = Lock()

# 请求限流
last_request_time = 0
request_lock = Lock()

# 进度显示锁
progress_lock = Lock()
last_progress_time = 0

def rate_limited_sleep():
    global last_request_time
    with request_lock:
        current_time = time.time()
        elapsed = current_time - last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        last_request_time = time.time()


def _print_progress():
    """打印上传进度（需在 stats_lock 内调用）"""
    global last_progress_time
    
    current_time = time.time()
    
    # 限制刷新频率，每0.5秒最多刷新一次
    with progress_lock:
        if current_time - last_progress_time < 0.5:
            return
        last_progress_time = current_time
    
    pending_total = stats['pending_total']
    processed = stats['processed_count']
    success = stats['success_count']
    skip = stats['skip_count']
    error = stats['error_count']
    start_time = stats['start_time']
    
    if pending_total <= 0:
        return
    
    # 计算进度百分比
    progress = (processed / pending_total) * 100 if pending_total > 0 else 0
    
    # 计算预计剩余时间
    eta_str = "计算中..."
    if start_time and processed > 0:
        elapsed = current_time - start_time
        avg_time_per_file = elapsed / processed
        remaining = pending_total - processed
        eta_seconds = remaining * avg_time_per_file
        
        if eta_seconds < 60:
            eta_str = f"{int(eta_seconds)}秒"
        elif eta_seconds < 3600:
            eta_str = f"{int(eta_seconds // 60)}分{int(eta_seconds % 60)}秒"
        else:
            hours = int(eta_seconds // 3600)
            minutes = int((eta_seconds % 3600) // 60)
            eta_str = f"{hours}小时{minutes}分"
        
        # 计算预计完成时间
        finish_time = datetime.fromtimestamp(current_time + eta_seconds)
        finish_str = finish_time.strftime("%H:%M:%S")
        eta_str = f"{eta_str} (预计{finish_str}完成)"
    
    # 打印进度条
    progress_bar_len = 20
    filled = int(progress_bar_len * processed / pending_total) if pending_total > 0 else 0
    bar = "█" * filled + "░" * (progress_bar_len - filled)
    
    print(f"\r📊 进度: [{bar}] {progress:.1f}% | 总数:{pending_total} 成功:{success} 跳过:{skip} 失败:{error} | 剩余:{eta_str}    ", end="", flush=True)

# 初始化记录管理器
failed_manager = FailedRecordsManager()
success_manager = SuccessRecordsManager()

# 知识库ID缓存（避免重复查询/创建）
# key: (folder_id, dataset_name), value: dataset_id
dataset_id_cache = {}
dataset_cache_lock = Lock()

# 当前任务配置（会在处理每个任务时更新）
current_task = {
    "local_folder": "",
    "folder_id": "",
    "dataset_name": "",
}


def get_all_files(folder_path, show_progress=False, task_name=""):
    """
    获取文件夹下所有文件（包括子文件夹）
    
    Args:
        folder_path: 文件夹路径
        show_progress: 是否显示扫描进度
        task_name: 任务名称（用于进度显示）
    
    Returns:
        list: [(相对路径, 绝对路径), ...]
    """
    files = []
    dir_count = 0
    
    for root, dirs, filenames in os.walk(folder_path):
        dir_count += 1
        if show_progress:
            print(f"\r  [{task_name}] 扫描中... 已扫描 {dir_count} 个目录, 找到 {len(files)} 个文件", end="", flush=True)
        
        for filename in filenames:
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, folder_path)
            files.append((rel_path, abs_path))
    
    if show_progress:
        print(f"\r  [{task_name}] 扫描完成: {dir_count} 个目录, {len(files)} 个文件" + " " * 20)
    
    return files


def get_or_create_dataset(lingyanDataset, folder_id, dataset_name):
    """
    获取或创建知识库，返回知识库ID
    
    Args:
        lingyanDataset: API实例
        folder_id: 远程目录ID
        dataset_name: 知识库名称
    """
    global dataset_id_cache
    
    cache_key = (folder_id, dataset_name)
    
    with dataset_cache_lock:
        if cache_key in dataset_id_cache:
            return dataset_id_cache[cache_key]
        
        # 查询该目录下的知识库
        log.info(f"正在查询目录下的知识库，folder_id={folder_id}")
        response_code, datasets = lingyanDataset.list_datasets(workspace_id, folder_id)
        
        if response_code != 200:
            log.error(f"获取知识库列表失败：{response_code}, {datasets}")
            return None
        
        # 查找是否已有同名知识库
        for ds in datasets:
            if ds.get("name") == dataset_name:
                dataset_id = ds.get("id")
                dataset_id_cache[cache_key] = dataset_id
                log.info(f"找到已存在的知识库：{dataset_name}，ID={dataset_id}")
                return dataset_id
        
        # 不存在则创建
        log.info(f"知识库不存在，正在创建：{dataset_name}")
        response_code, created_ds = lingyanDataset.create_dataset(
            workspace_id=workspace_id,
            name=dataset_name,
            folder_id=folder_id,
            description=f"自动上传工具创建的知识库",
        )
        
        if response_code != 200:
            log.error(f"创建知识库失败：{response_code}, {created_ds}")
            return None
        
        dataset_id = created_ds.get("id")
        dataset_id_cache[cache_key] = dataset_id
        log.info(f"知识库创建成功：{dataset_name}，ID={dataset_id}")
        return dataset_id


def process_file(file_info):
    """
    处理单个文件
    
    Args:
        file_info: (相对路径, 绝对路径, folder_id, dataset_name)
    """
    rel_path, abs_path, folder_id, dataset_name = file_info
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
            stats['processed_count'] += 1
            _print_progress()
        return
    
    # 检查文件扩展名
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext in SKIP_EXTENSIONS:
        thread_log.warning(f"不支持的文件类型，跳过：{rel_path}")
        with stats_lock:
            stats['skip_count'] += 1
            stats['processed_count'] += 1
            _print_progress()
        return
    
    # 获取知识库ID
    dataset_id = get_or_create_dataset(lingyanDataset, folder_id, dataset_name)
    if not dataset_id:
        thread_log.error(f"无法获取知识库ID，跳过：{rel_path}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            file_classify=dataset_name,
            error_stage=FailedRecord.STAGE_LIST_DATASETS,
            error_message="无法获取或创建知识库",
            dataset_name=dataset_name,
            folder_id=folder_id,
        )
        with stats_lock:
            stats['error_count'] += 1
            stats['processed_count'] += 1
            _print_progress()
        return
    
    # 重名检测
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
            file_classify=dataset_name,
            error_stage=FailedRecord.STAGE_CHECK_FILE,
            error_message=f"重名检测失败：{response_code}, {response}",
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
            stats['processed_count'] += 1
            _print_progress()
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
            stats['processed_count'] += 1
            _print_progress()
        return
    
    # 上传文件（带重试机制，处理503等服务器错误）
    thread_log.info(f"开始上传：{rel_path}")
    upload_file_id = None
    
    for upload_attempt in range(MAX_UPLOAD_RETRIES + 1):
        response_code, upload_response = lingyanFile.upload_file(
            file_path=abs_path,
            file_type="dataset",
        )
        
        if response_code == 200:
            upload_file_id = upload_response.get("id")
            thread_log.info(f"文件上传成功：{rel_path}，文件ID={upload_file_id}")
            break
        elif response_code in [502, 503, 504]:
            # 服务器过载，等待后重试
            if upload_attempt < MAX_UPLOAD_RETRIES:
                wait_time = UPLOAD_RETRY_DELAY * (upload_attempt + 1)
                thread_log.warning(f"服务器繁忙({response_code})，{wait_time}秒后重试 ({upload_attempt + 1}/{MAX_UPLOAD_RETRIES})：{rel_path}")
                time.sleep(wait_time)
            else:
                thread_log.error(f"文件上传失败（服务器繁忙，已重试{MAX_UPLOAD_RETRIES}次）：{rel_path}，{response_code}")
                failed_manager.add_record(
                    file_path=abs_path,
                    file_name=file_name,
                    file_classify=dataset_name,
                    error_stage=FailedRecord.STAGE_UPLOAD_FILE,
                    error_message=f"上传失败（服务器繁忙）：{response_code}, {upload_response}",
                    error_code=response_code,
                    dataset_name=dataset_name,
                    folder_id=folder_id,
                    dataset_id=dataset_id,
                )
                with stats_lock:
                    stats['error_count'] += 1
                    stats['processed_count'] += 1
                    _print_progress()
                return
        else:
            # 其他错误，不重试
            thread_log.error(f"文件上传失败：{rel_path}，{response_code}, {upload_response}")
            failed_manager.add_record(
                file_path=abs_path,
                file_name=file_name,
                file_classify=dataset_name,
                error_stage=FailedRecord.STAGE_UPLOAD_FILE,
                error_message=f"上传失败：{response_code}, {upload_response}",
                error_code=response_code,
                dataset_name=dataset_name,
                folder_id=folder_id,
                dataset_id=dataset_id,
            )
            with stats_lock:
                stats['error_count'] += 1
                stats['processed_count'] += 1
                _print_progress()
            return
    
    if not upload_file_id:
        return
    
    # 创建文档
    response_code, newDoc = lingyanDataset.create_document(
        dataset_id=dataset_id,
        file_id=upload_file_id,
    )
    
    if response_code != 200:
        thread_log.error(f"创建文档失败：{rel_path}，{response_code}, {newDoc}")
        failed_manager.add_record(
            file_path=abs_path,
            file_name=file_name,
            file_classify=dataset_name,
            error_stage=FailedRecord.STAGE_CREATE_DOCUMENT,
            error_message=f"创建文档失败：{response_code}, {newDoc}",
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
            stats['processed_count'] += 1
            _print_progress()
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
            file_classify=dataset_name,
            error_stage=FailedRecord.STAGE_CREATE_TASK,
            error_message=f"创建任务失败：{response_code}, {task_response}",
            error_code=response_code,
            dataset_name=dataset_name,
            folder_id=folder_id,
            dataset_id=dataset_id,
        )
        with stats_lock:
            stats['error_count'] += 1
            stats['processed_count'] += 1
            _print_progress()
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
        stats['processed_count'] += 1
        _print_progress()
    thread_log.info(f"✅ 上传完成：{rel_path}")


def process_file_safe(file_info):
    """安全包装，捕获异常，带连接错误重试"""
    rel_path, abs_path, folder_id, dataset_name = file_info
    
    for retry in range(MAX_CONNECTION_RETRIES + 1):
        try:
            process_file(file_info)
            return  # 成功则直接返回
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout,
                ConnectionRefusedError,
                ConnectionResetError) as e:
            if retry < MAX_CONNECTION_RETRIES:
                wait_time = CONNECTION_RETRY_DELAY * (retry + 1)
                log.warning(f"连接错误，{wait_time}秒后重试({retry+1}/{MAX_CONNECTION_RETRIES})：{rel_path}")
                time.sleep(wait_time)
            else:
                log.error(f"连接错误，已达最大重试次数：{rel_path}，错误：{str(e)}")
                failed_manager.add_record(
                    file_path=abs_path,
                    file_name=os.path.basename(abs_path),
                    file_classify=dataset_name,
                    error_stage=FailedRecord.STAGE_UNKNOWN,
                    error_message=f"连接错误：{str(e)}",
                )
                with stats_lock:
                    stats['error_count'] += 1
                    stats['processed_count'] += 1
                    _print_progress()
        except Exception as e:
            log.error(f"处理文件时发生异常：{rel_path}，错误：{str(e)}")
            failed_manager.add_record(
                file_path=abs_path,
                file_name=os.path.basename(abs_path),
                file_classify=dataset_name,
                error_stage=FailedRecord.STAGE_UNKNOWN,
                error_message=f"未知错误：{str(e)}",
            )
            with stats_lock:
                stats['error_count'] += 1
                stats['processed_count'] += 1
                _print_progress()
            return  # 非连接错误不重试


def check_upload_status(valid_tasks):
    """
    检查所有任务的上传情况，并保存到文件
    
    控制台只显示摘要，详细文件列表保存到文件
    
    Returns:
        list: 每个任务的统计信息 [(dataset_name, total, uploaded, pending), ...]
        int: 总待上传文件数
    """
    # 检查报告文件路径
    report_filename = os.path.join(logs_dir, f"upload_check_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt")
    
    # 详细报告只写入文件
    report_lines = []
    
    def file_output(line=""):
        """只写入文件"""
        report_lines.append(line)
    
    def console_output(line=""):
        """只打印到控制台"""
        print(line)
    
    def both_output(line=""):
        """同时打印和写入文件"""
        print(line)
        report_lines.append(line)
    
    both_output("=" * 60)
    both_output("📊 上传情况检查")
    both_output(f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    both_output("=" * 60)
    
    all_stats = []
    total_pending = 0
    total_uploaded = 0
    total_files = 0
    
    for i, task in enumerate(valid_tasks):
        local_folder = task["local_folder"]
        dataset_name = task["dataset_name"]
        folder_id = task["folder_id"]
        
        console_output(f"\n正在扫描任务 {i+1}/{len(valid_tasks)}: {dataset_name}...")
        
        # 扫描文件（显示进度）
        task_files = get_all_files(local_folder, show_progress=True, task_name=dataset_name)
        
        # 统计已上传和待上传
        uploaded_files = []
        pending_files = []
        for rel_path, abs_path in task_files:
            if success_manager.is_uploaded(abs_path):
                uploaded_files.append(rel_path)
            else:
                pending_files.append(rel_path)
        
        total_count = len(task_files)
        uploaded_count = len(uploaded_files)
        pending_count = len(pending_files)
        
        all_stats.append((dataset_name, total_count, uploaded_count, pending_count))
        
        total_files += total_count
        total_uploaded += uploaded_count
        total_pending += pending_count
        
        # 计算进度百分比
        progress = (uploaded_count / total_count * 100) if total_count > 0 else 100
        status_icon = "✅" if pending_count == 0 else "🔄"
        
        # 控制台只显示摘要
        both_output(f"{status_icon} 任务 {i+1}: {dataset_name}")
        both_output(f"   总文件: {total_count} | 已上传: {uploaded_count} | 待上传: {pending_count} | 进度: {progress:.1f}%")
        
        # 详细信息只写入文件
        file_output(f"   本地路径: {local_folder}")
        file_output(f"   远程目录ID: {folder_id}")
        
        # 列出待上传的文件（只写入文件）
        if pending_files:
            file_output(f"   -------- 待上传文件列表 ({pending_count}个) --------")
            for idx, f in enumerate(pending_files, 1):
                file_output(f"   [{idx}] {f}")
        
        # 列出已上传的文件（只写入文件）
        if uploaded_files:
            file_output(f"   -------- 已上传文件列表 ({uploaded_count}个) --------")
            for idx, f in enumerate(uploaded_files, 1):
                file_output(f"   [{idx}] {f}")
        
        file_output("")  # 空行分隔
    
    # 总结
    both_output("\n" + "=" * 60)
    total_progress = (total_uploaded / total_files * 100) if total_files > 0 else 100
    both_output(f"📈 总计统计")
    both_output(f"   总文件数: {total_files}")
    both_output(f"   已上传: {total_uploaded}")
    both_output(f"   待上传: {total_pending}")
    both_output(f"   总进度: {total_progress:.1f}%")
    both_output("=" * 60)
    
    # 保存到文件
    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    console_output(f"\n📄 详细报告已保存到: {report_filename}")
    
    return all_stats, total_pending


def do_upload(valid_tasks):
    """执行上传任务"""
    print("\n" + "=" * 60)
    log.info(f"共有 {len(valid_tasks)} 个上传任务")
    log.info(f"同时处理任务数：{MAX_CONCURRENT_TASKS}")
    log.info(f"每任务并发线程数：{MAX_WORKERS}")
    log.info(f"已加载 {success_manager.get_count()} 条成功记录")
    print("=" * 60)
    
    # 先扫描所有任务，统计待上传总数
    print("\n📂 正在扫描所有任务...")
    all_pending_files = []  # [(rel_path, abs_path, folder_id, dataset_name), ...]
    skipped_by_ext = 0      # 因文件类型跳过的数量
    skipped_by_uploaded = 0  # 因已上传跳过的数量
    
    for i, task in enumerate(valid_tasks):
        local_folder = task["local_folder"]
        folder_id = task["folder_id"]
        dataset_name = task["dataset_name"]
        
        task_files = get_all_files(local_folder, show_progress=True, task_name=dataset_name)
        
        # 过滤已上传的文件和不支持的文件类型
        for rel_path, abs_path in task_files:
            # 检查文件类型
            file_ext = os.path.splitext(abs_path)[1].lower()
            if file_ext in SKIP_EXTENSIONS:
                skipped_by_ext += 1
                continue
            
            # 检查是否已上传
            if success_manager.is_uploaded(abs_path):
                skipped_by_uploaded += 1
                continue
            
            all_pending_files.append((rel_path, abs_path, folder_id, dataset_name))
    
    total_pending = len(all_pending_files)
    print(f"  跳过不支持的文件类型: {skipped_by_ext} 个")
    print(f"  跳过已上传的文件: {skipped_by_uploaded} 个")
    print(f"\n📊 扫描完成：共 {total_pending} 个文件待上传")
    print("=" * 60)
    
    if total_pending == 0:
        print("✅ 所有文件均已上传，无需操作！")
        return
    
    # 初始化统计信息
    with stats_lock:
        stats['pending_total'] = total_pending
        stats['processed_count'] = 0
        stats['success_count'] = 0
        stats['skip_count'] = 0
        stats['error_count'] = 0
        stats['start_time'] = time.time()
    
    print(f"\n🚀 开始上传 {total_pending} 个文件...\n")
    
    def process_single_task(task_info):
        """处理单个任务（扫描 + 上传）"""
        task_index, task = task_info
        local_folder = task["local_folder"]
        folder_id = task["folder_id"]
        dataset_name = task["dataset_name"]
        
        log.info(f"【任务 {task_index}/{len(valid_tasks)}】开始处理")
        log.info(f"  [{dataset_name}] 本地文件夹：{local_folder}")
        log.info(f"  [{dataset_name}] 远程目录ID：{folder_id}")
        
        # 扫描该任务的文件（显示进度）
        log.info(f"  [{dataset_name}] 正在扫描文件...")
        task_files = get_all_files(local_folder, show_progress=True, task_name=dataset_name)
        total_scanned = len(task_files)
        log.info(f"  [{dataset_name}] 扫描完成，共找到 {total_scanned} 个文件")
        
        if not task_files:
            log.warning(f"  [{dataset_name}] 该任务没有文件，跳过")
            return
        
        # 过滤已上传的文件和不支持的文件类型
        already_uploaded = []
        skipped_ext = []
        pending_files = []
        for rel_path, abs_path in task_files:
            # 检查文件类型
            file_ext = os.path.splitext(abs_path)[1].lower()
            if file_ext in SKIP_EXTENSIONS:
                skipped_ext.append(rel_path)
                continue
            
            if success_manager.is_uploaded(abs_path):
                already_uploaded.append(rel_path)
            else:
                pending_files.append((rel_path, abs_path))
        
        # 记录所有文件名到日志
        log.info(f"  [{dataset_name}] -------- 文件列表开始 --------")
        for idx, (rel_path, _) in enumerate(task_files, 1):
            if rel_path in skipped_ext:
                status = "[跳过类型]"
            elif rel_path in already_uploaded:
                status = "[已上传]"
            else:
                status = "[待上传]"
            log.info(f"  [{dataset_name}] [{idx}] {status} {rel_path}")
        log.info(f"  [{dataset_name}] -------- 文件列表结束 --------")
        log.info(f"  [{dataset_name}] 统计：总共 {total_scanned} 个，跳过类型 {len(skipped_ext)} 个，已上传 {len(already_uploaded)} 个，待上传 {len(pending_files)} 个")
        
        # 如果全部已上传，跳过该任务
        if not pending_files:
            log.info(f"  [{dataset_name}] 所有文件均已上传，跳过该任务")
            return
        
        # 构建文件信息列表
        files_with_info = [(rel_path, abs_path, folder_id, dataset_name) 
                          for rel_path, abs_path in pending_files]
        
        # 开始上传该任务
        log.info(f"  [{dataset_name}] 开始上传 {len(pending_files)} 个文件...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(process_file_safe, files_with_info))
        
        # 每个任务完成后保存记录
        success_manager.flush()
        
        log.info(f"【任务 {task_index}/{len(valid_tasks)}】[{dataset_name}] 完成")
    
    # 使用线程池并发处理多个任务
    task_infos = [(i+1, task) for i, task in enumerate(valid_tasks)]
    
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS) as task_executor:
        list(task_executor.map(process_single_task, task_infos))
    
    # 计算总耗时
    total_time = time.time() - stats['start_time'] if stats['start_time'] else 0
    if total_time < 60:
        time_str = f"{int(total_time)}秒"
    elif total_time < 3600:
        time_str = f"{int(total_time // 60)}分{int(total_time % 60)}秒"
    else:
        hours = int(total_time // 3600)
        minutes = int((total_time % 3600) // 60)
        time_str = f"{hours}小时{minutes}分"
    
    # 输出总统计
    print("\n\n" + "=" * 60)
    log.info("全部任务完成！总统计信息：")
    log.info(f"  待上传总数：{stats['pending_total']}")
    log.info(f"  成功上传：{stats['success_count']}")
    log.info(f"  跳过文件：{stats['skip_count']}")
    log.info(f"  失败文件：{stats['error_count']}")
    log.info(f"  总耗时：{time_str}")
    
    if stats['error_count'] > 0:
        failed_manager.print_summary()
        log.info(f"失败记录已保存到：{failed_manager.records_dir}")


def main():
    print("=" * 60)
    print("指定目录上传工具（支持批量任务）")
    print(f"运行模式：{RUN_MODE}")
    print("=" * 60)
    
    # 检查配置
    if not UPLOAD_TASKS:
        log.error("请先配置 UPLOAD_TASKS！")
        return
    
    # 验证所有任务配置
    valid_tasks = []
    for i, task in enumerate(UPLOAD_TASKS):
        local_folder = task.get("local_folder", "")
        folder_id = task.get("folder_id", "")
        dataset_name = task.get("dataset_name", "")
        
        if not local_folder or not folder_id or not dataset_name:
            log.warning(f"任务 {i+1} 配置不完整，跳过")
            continue
        
        if not os.path.exists(local_folder):
            log.warning(f"任务 {i+1} 本地文件夹不存在，跳过：{local_folder}")
            continue
        
        valid_tasks.append(task)
    
    if not valid_tasks:
        log.error("没有有效的上传任务！")
        return
    
    log.info(f"共有 {len(valid_tasks)} 个有效任务")
    
    # 根据运行模式执行
    if RUN_MODE == "check":
        # 只检查，不上传
        check_upload_status(valid_tasks)
        
    elif RUN_MODE == "upload":
        # 直接上传
        do_upload(valid_tasks)
        
    elif RUN_MODE == "both":
        # 先检查，然后直接上传
        all_stats, total_pending = check_upload_status(valid_tasks)
        
        if total_pending == 0:
            print("\n✅ 所有文件均已上传完成，无需操作！")
            return
        
        print(f"\n有 {total_pending} 个文件待上传，开始上传...")
        do_upload(valid_tasks)
    
    else:
        log.error(f"未知的运行模式：{RUN_MODE}，请设置为 check/upload/both")


if __name__ == "__main__":
    main()
