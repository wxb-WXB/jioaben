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
from models import FolderMap
from utils import get_file_relative_dir, is_pdf_file, list_files, pdf_has_images
from failed_records import FailedRecord, FailedRecordsManager, SuccessRecordsManager

# from pyfiglet import figlet_format
# print(figlet_format("Auto Upload", font="slant"))

# 确保logs文件夹存在（使用项目根目录）
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志文件名（按日期）
log_filename = os.path.join(logs_dir, f"autoUploads_{datetime.now().strftime('%Y-%m-%d')}.log")

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
log = logging.getLogger("autoUploads")

# ============ 配置区域 ============
# 支持多个目录同时上传，每行一个目录路径
base_folders = [
    r'E:\0-智能体资料汇总收集\确定目录的资料',
    # r'E:\其他资料目录',          # 取消注释添加更多目录
    # r'D:\另一个目录\子目录',
]
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"       # 工作区id
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"       # 灵燕平台 api key
# ==================================

log.info(f"配置了 {len(base_folders)} 个上传目录")

# ============ 性能配置 ============
MAX_WORKERS = 8               # 并发线程数（建议3-8，太高可能导致服务器拒绝连接）
SKIP_IMAGE_CHECK = True       # 是否跳过PDF图片检测（跳过可加速，但会关闭图片索引）
REQUEST_INTERVAL = 0.3        # 每个请求之间的间隔时间（秒），防止请求过快
# ==================================

# ============ 过滤配置 ============是
# 需要过滤（跳过）的文件夹名称列表
EXCLUDE_FOLDERS = [
    "01设计管理",
    "02科研管理",
    "03数智管理",
    "04技术管理",
    "05标准规范",
    "工程专项管理",
    "进度管理",
    "征地移民管理",
    "06参考资料/湛江市引调水方案资料",
    "07工程专项管理",
    "08多媒体",

    # "质量管理",
    # 可以继续添加更多需要过滤的文件夹  标准规范还没有传完
]
# ==================================

# 统计信息（使用线程安全的字典）
stats = {
    'total_files': 0,
    'success_count': 0,
    'skip_count': 0,
    'error_count': 0
}
stats_lock = Lock()

# 请求限流器（控制全局请求速率）
last_request_time = 0
request_lock = Lock()

def rate_limited_sleep():
    """
    请求限流：确保请求之间有足够的间隔
    """
    global last_request_time
    with request_lock:
        current_time = time.time()
        elapsed = current_time - last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        last_request_time = time.time()

def retry_on_connection_error(max_retries=3, base_delay=2):
    """
    连接错误重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒），每次重试会指数增长
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            thread_name = current_thread().name
            thread_log = logging.getLogger(f"autoUploads-{thread_name}")
            
            for attempt in range(max_retries + 1):
                try:
                    # 每次请求前进行限流
                    rate_limited_sleep()
                    return func(*args, **kwargs)
                except (requests.exceptions.ConnectionError, 
                        requests.exceptions.Timeout,
                        requests.exceptions.ChunkedEncodingError) as e:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)  # 指数退避
                        thread_log.warning(f"连接错误，{delay}秒后重试 ({attempt + 1}/{max_retries}): {str(e)}")
                        time.sleep(delay)
                    else:
                        thread_log.error(f"连接错误，已达最大重试次数: {str(e)}")
                        raise
            return func(*args, **kwargs)
        return wrapper
    return decorator

# 知识库缓存：避免重复查询同一个folder_id下的知识库
# key: folder_id, value: {dataset_name: dataset_id}
dataset_cache = {}
dataset_cache_lock = Lock()

# 初始化失败记录管理器
failed_manager = FailedRecordsManager()

# 初始化成功记录管理器（用于跳过已上传的文件）
success_manager = SuccessRecordsManager()

# 检查文件路径是否包含需要过滤的文件夹
def should_exclude_file(file_path):
    """
    检查文件路径是否包含需要过滤的文件夹
    
    Args:
        file_path: 文件的相对路径
    
    Returns:
        bool: 如果应该过滤则返回True，否则返回False
    """
    # 将路径分割成各个部分
    path_parts = file_path.replace("\\", "/").split("/")
    for exclude_folder in EXCLUDE_FOLDERS:
        if exclude_folder in path_parts:
            return True
    return False

# 扫描所有配置的目录，收集文件路径和对应的base_folder
# all_files_info: [(file_path, base_folder), ...]
all_files_info = []
excluded_count = 0
for base_folder in base_folders:
    if not os.path.exists(base_folder):
        log.warning(f"目录不存在，跳过：{base_folder}")
        continue
    log.info(f"开始扫描目录：{base_folder}")
    files = list_files(
        root=base_folder,
        pattern="*",
        absolute=False,
        skip_hidden=True,
    )
    log.info(f"  发现 {len(files)} 个文件")
    for f in files:
        if should_exclude_file(f):
            excluded_count += 1
            continue
        all_files_info.append((f, base_folder))

if excluded_count > 0:
    log.info(f"已过滤 {excluded_count} 个文件（来自排除的文件夹：{EXCLUDE_FOLDERS}）")

log.info(f"扫描完成，共发现 {len(all_files_info)} 个文件")

# 创建LingyanDataset和LingyanFile实例（每个线程会创建自己的实例）
def process_file(file_info):
    """
    处理单个文件的函数
    
    Args:
        file_info: 元组 (file_path, base_folder)
    """
    file_path, base_folder = file_info
    # 为每个线程创建独立的日志记录器，使用线程名称区分
    thread_name = current_thread().name
    thread_log = logging.getLogger(f"autoUploads-{thread_name}")
    # 确保线程日志记录器使用相同的配置
    thread_log.setLevel(logging.INFO)
    if not thread_log.handlers:
        # 为线程日志记录器添加文件和控制台处理器，并设置格式化器
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        thread_log.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        thread_log.addHandler(console_handler)
        # 避免日志向上传播到根记录器，防止重复输出
        thread_log.propagate = False

    # 每个线程创建自己的实例，避免线程安全问题
    lingyanDataset = LingyanDataset(api_key)
    lingyanFile = LingyanFile(api_key)

    with stats_lock:
        stats['total_files'] += 1

    # 检查是否已成功上传过（本地记录，无需API调用）
    full_file_path = os.path.join(base_folder, file_path)
    if success_manager.is_uploaded(full_file_path):
        thread_log.info(f"已上传过（本地记录），跳过：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return

    # 检查是否为需要跳过的文件类型
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # 需要跳过的文件扩展名分类
    excel_extensions = ['.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xltm']
    archive_extensions = ['.rar', '.zip']
    web_extensions = ['.htm', '.html', '.css', '.ico']
    video_extensions = ['.mov', '.mp4']
    image_extensions = ['.png', '.jpg', '.jpeg']
    cad_extensions = ['.dwg']
    other_skip_extensions = ['.wps', '.pptx', '.pdg', '.dat', '.xml']
    
    # 合并所有需要跳过的扩展名
    all_skip_extensions = (excel_extensions + archive_extensions + web_extensions + 
                           video_extensions + image_extensions + cad_extensions + 
                           other_skip_extensions)
    
    if file_ext in excel_extensions:
        thread_log.warning(f"检测到Excel文件，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    elif file_ext in archive_extensions:
        thread_log.warning(f"检测到压缩文件，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    elif file_ext in web_extensions:
        thread_log.warning(f"检测到网页/样式文件，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    elif file_ext in video_extensions:
        thread_log.warning(f"检测到视频文件，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    elif file_ext in image_extensions:
        thread_log.warning(f"检测到图片文件，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    elif file_ext in cad_extensions:
        thread_log.warning(f"检测到CAD文件，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    elif file_ext in other_skip_extensions:
        thread_log.warning(f"检测到不支持的文件类型，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return

    # file_classify是文件的分类,也是知识库的目录
    file_classify = get_file_relative_dir(file_path, base_folder)
    # 知识库名
    dataset_name = file_classify.split("/")[-1]

    thread_log.info(f"文件：{file_path}，分类目录：{file_classify}，知识库名：{dataset_name}")

    # 找文件夹id
    folder_map = FolderMap.get_or_none(FolderMap.folderPath == file_classify)
    folder_id = folder_map.id if folder_map else None
    if not folder_id:
        thread_log.warning(f"未找到目录映射，跳过文件上传：{file_path}，目录：{file_classify}")
        # 记录失败：目录映射未找到
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

    # 使用缓存获取或创建知识库ID（减少重复API调用）
    dataset_id = None
    
    # 先检查缓存（无锁快速路径）
    if folder_id in dataset_cache and dataset_name in dataset_cache[folder_id]:
        dataset_id = dataset_cache[folder_id][dataset_name]
        thread_log.info(f"从缓存获取知识库ID：{dataset_id}")
    
    # 缓存未命中，需要查询或创建
    if not dataset_id:
        with dataset_cache_lock:
            # 双重检查：可能其他线程刚刚更新了缓存
            if folder_id in dataset_cache and dataset_name in dataset_cache[folder_id]:
                dataset_id = dataset_cache[folder_id][dataset_name]
            else:
                # 确保folder_id的缓存字典存在
                if folder_id not in dataset_cache:
                    dataset_cache[folder_id] = {}
                    # 首次查询该folder_id，获取所有知识库并缓存
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
                    # 缓存所有知识库
                    for ds in datasets:
                        dataset_cache[folder_id][ds.get("name")] = ds.get("id")
                    thread_log.info(f"已缓存 {len(datasets)} 个知识库（folder_id={folder_id}）")
                
                # 从缓存中获取
                if dataset_name in dataset_cache[folder_id]:
                    dataset_id = dataset_cache[folder_id][dataset_name]
                    thread_log.info(f"使用已存在的知识库ID：{dataset_id}")
                else:
                    # 不存在则创建知识库
                    thread_log.info(f"知识库不存在，开始创建：{dataset_name}")
                    response_code, created_ds = lingyanDataset.create_dataset(
                        workspace_id=workspace_id,
                        name=dataset_name,
                        folder_id=folder_id,
                        description=f"自动上传文件生成的知识库，目录：{file_classify}",
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
                    # 添加到缓存
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
        # 记录失败：重名检测失败
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
        # 重名说明已上传过，记录到成功记录（下次直接跳过，不用调API）
        success_manager.add_record(
            file_path=full_file_path,
            file_name=file_name,
            dataset_id=dataset_id,
            document_id="",  # 重名跳过的没有document_id
        )
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
        # 记录失败：文件上传失败
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
        # 记录失败：创建文档失败
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

    # 是否有图片（可配置跳过检测以加速）
    is_pdf = is_pdf_file(file_path)
    if SKIP_IMAGE_CHECK:
        has_img = False  # 跳过图片检测，不开启图片索引
    else:
        try:
            has_img = pdf_has_images(file_path) if is_pdf else False
        except Exception as e:
            thread_log.warning(f"PDF图片检测失败，跳过图片索引：{e}")
            has_img = False
    thread_log.info("打开精准解析" if is_pdf else "关闭精准解析")
    thread_log.info("打开图片索引" if has_img else "关闭图片索引")

    # 新建任务
    thread_log.info(f"开始创建文档处理任务：文档ID={newDocId}，知识库ID={dataset_id}")
    response_code, task_response = lingyanDataset.create_task(
        dataset_id,
        newDocId,
        image_task=has_img,         # 如果是pdf，必须开启图片索引
        parse_enhance= is_pdf       # 如果是pdf，必须开启精准解析
    )
    if response_code != 200:
        error_msg = f"状态码：{response_code}，错误信息：{task_response}"
        thread_log.error(f"创建文档任务失败：{file_path}，{error_msg}")
        # 记录失败：创建任务失败
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
    
    thread_log.info(f"文档处理任务创建成功：文档ID={newDocId}，文件：{file_path}")
    
    # 成功后移除失败记录（如果之前有记录的话）
    failed_manager.remove_record(file_path)
    
    # 记录成功上传（用于下次跳过）
    success_manager.add_record(
        file_path=full_file_path,
        file_name=file_name,
        dataset_id=dataset_id,
        document_id=newDocId,
    )
    
    with stats_lock:
        stats['success_count'] += 1
    thread_log.info(f"文件处理完成：{file_path}")

# 包装函数，用于捕获所有异常
def process_file_safe(file_info):
    """
    安全包装函数，捕获所有异常
    
    Args:
        file_info: 元组 (file_path, base_folder)
    """
    file_path, base_folder = file_info
    try:
        process_file(file_info)
    except Exception as e:
        # 为异常处理也创建线程特定的日志记录器
        thread_name = current_thread().name
        thread_log = logging.getLogger(f"autoUploads-{thread_name}")
        thread_log.setLevel(logging.INFO)
        if not thread_log.handlers:
            # 为线程日志记录器添加文件和控制台处理器，并设置格式化器
            file_handler = logging.FileHandler(log_filename, encoding='utf-8')
            file_handler.setFormatter(log_formatter)
            thread_log.addHandler(file_handler)

            console_handler = logging.StreamHandler()
            console_handler.setFormatter(log_formatter)
            thread_log.addHandler(console_handler)
            thread_log.propagate = False
        error_msg = f"未捕获的异常：{str(e)}"
        thread_log.error(f"处理文件时发生未捕获的异常：{file_path}，错误：{str(e)}")
        # 记录失败：未知错误
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
log.info(f"已加载 {success_manager.get_count()} 条成功记录，将跳过已上传的文件")
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    # 使用map方法提交所有任务并等待完成
    list(executor.map(process_file_safe, all_files_info))

# 强制保存成功记录（确保所有记录都已写入文件）
success_manager.flush()

# 输出统计信息
log.info(f"文件处理完成！统计信息：")
log.info(f"总文件数：{stats['total_files']}")
log.info(f"成功处理：{stats['success_count']}")
log.info(f"跳过文件：{stats['skip_count']}（含已上传 + Excel/压缩包 + 重名文件）")
log.info(f"失败文件：{stats['error_count']}")
log.info(f"累计成功上传记录：{success_manager.get_count()} 条")

# 输出失败记录摘要
if stats['error_count'] > 0:
    failed_manager.print_summary()
    log.info(f"失败记录已保存到：{failed_manager.records_dir}")
    log.info(f"可运行 retry_failed_uploads.py 重新上传失败的文件")

# 输出每个文件夹下的文件数（去重，避免重复输出）
unique_folders = set()
for file_path, base_folder in all_files_info:
    file_classify = get_file_relative_dir(file_path, base_folder)
    unique_folders.add((file_classify, base_folder))

for folder_path, base_folder in sorted(unique_folders):
    full_path = os.path.join(base_folder, folder_path)
    if os.path.exists(full_path):
        log.info(f"文件夹：{folder_path}，文件数：{len(list_files(full_path))}")
