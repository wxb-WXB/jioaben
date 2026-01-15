import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, current_thread
from LingyanAi import LingyanDataset, LingyanFile
from models import FolderMap
from utils import get_file_relative_dir, is_pdf_file, list_files, pdf_has_images
import logging
from pyfiglet import figlet_format
print(figlet_format("Auto Upload", font="slant"))

# 确保logs文件夹存在
logs_dir = "logs"
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

# TODO: 修改这里的配置
base_folder = r'D:\02-飞速资料\07-环北项目\01-环北工程知识库\3.三会管理（敏感）\2021'
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"       # 工作区id
api_key = "sk-mZaD8UalsAxMa9E87rn2zmptaeu0XW2wH7LkcKxS"       # 灵燕平台 api key
log.info(f"开始扫描目录：{base_folder}，准备上传文件到灵燕AI知识库")

# 统计信息（使用线程安全的字典）
stats = {
    'total_files': 0,
    'success_count': 0,
    'skip_count': 0,
    'error_count': 0
}
stats_lock = Lock()

dataset_lock = Lock()

all_files_paths = list_files(
    root=base_folder,
    pattern="*",
    absolute=False,
    skip_hidden=True,
)

log.info(f"扫描完成，共发现 {len(all_files_paths)} 个文件")

# 创建LingyanDataset和LingyanFile实例（每个线程会创建自己的实例）
def process_file(file_path):
    """处理单个文件的函数"""
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

    # 检查是否为Excel文件，如果是则跳过上传
    file_ext = os.path.splitext(file_path)[1].lower()
    excel_extensions = ['.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xltm']
    if file_ext in excel_extensions:
        thread_log.warning(f"检测到Excel文件，跳过上传：{file_path}")
        with stats_lock:
            stats['skip_count'] += 1
        return
    elif file_ext in ['.rar', '.zip']:
        thread_log.warning(f"检测到压缩文件，跳过上传：{file_path}")
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
        with stats_lock:
            stats['skip_count'] += 1
        return
    thread_log.info(f"准备上传文件：{file_path}，目录：{file_classify}，目录ID：{folder_id}")

    # 查folder_id下的知识库 从此开始需要线程安全
    with dataset_lock:
        response_code, datasets = lingyanDataset.list_datasets(workspace_id, folder_id)
        if response_code != 200:
            thread_log.error(f"获取知识库列表失败，跳过文件上传：{file_path}，目录：{file_classify}，状态码：{response_code}，错误信息：{datasets}")
            with stats_lock:
                stats['error_count'] += 1
            return
        dataset_names = [ds.get("name") for ds in datasets]
        dataset_id = ""

        # 查看知识库是否存在
        if dataset_name in dataset_names:
            thread_log.info(f"知识库已存在，跳过创建：{dataset_name}，目录ID：{folder_id}")
            target_dataset = datasets[dataset_names.index(dataset_name)]
            dataset_id = target_dataset.get("id")
            thread_log.info(f"使用已存在的知识库ID：{dataset_id}")
        else:
            # 不存在则创建知识库
            thread_log.info(f"知识库不存在，开始创建：{dataset_name}，目录ID：{folder_id}")
            response_code, created_ds = lingyanDataset.create_dataset(
                workspace_id=workspace_id,
                name=dataset_name,
                folder_id=folder_id,
                description=f"自动上传文件生成的知识库，目录：{file_classify}",
            )
            if response_code != 200:
                thread_log.error(f"创建知识库失败，跳过文件上传：{file_path}，目录：{file_classify}，状态码：{response_code}，错误信息：{created_ds}")
                with stats_lock:
                    stats['error_count'] += 1
                return
            thread_log.info(f"已创建知识库：{created_ds.get('name')}，ID：{created_ds.get('id')}，目录ID：{folder_id}")
            dataset_id = created_ds.get("id")

    # 重名检测
    file_name = os.path.basename(file_path)
    file_name_without_ext = os.path.splitext(file_name)[0]
    thread_log.debug(f"开始重名检测：文件名={file_name_without_ext}，知识库ID={dataset_id}")
    response_code, response, duplicate_count = lingyanDataset.check_file(
        file_name=file_name_without_ext,
        dataset_id=dataset_id
    )
    if response_code != 200:
        thread_log.error(f"重名检测请求失败，跳过文件上传：{file_path}，状态码：{response_code}，错误信息：{response}")
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
        thread_log.error(f"文件上传失败，跳过创建文档：{file_path}，状态码：{response_code}，错误信息：{upload_response}")
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
        thread_log.error(f"创建文档失败：{file_path}，状态码：{response_code}，错误信息：{newDoc}")
        with stats_lock:
            stats['error_count'] += 1
        return
    newDocId = newDoc[0].get("id")
    thread_log.info(f"文档创建成功：文档ID={newDocId}，文件：{file_path}")

    # 是否有图片
    has_img = pdf_has_images(file_path)
    is_pdf = is_pdf_file(file_path)
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
        thread_log.error(f"创建文档任务失败：{file_path}，状态码：{response_code}，错误信息：{task_response}")
        with stats_lock:
            stats['error_count'] += 1
        return
    thread_log.info(f"文档处理任务创建成功：文档ID={newDocId}，文件：{file_path}")
    with stats_lock:
        stats['success_count'] += 1
    thread_log.info(f"文件处理完成：{file_path}")

# 包装函数，用于捕获所有异常
def process_file_safe(file_path):
    """安全包装函数，捕获所有异常"""
    try:
        process_file(file_path)
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
        thread_log.error(f"处理文件时发生未捕获的异常：{file_path}，错误：{str(e)}")
        with stats_lock:
            stats['error_count'] += 1

# 使用线程池并发处理文件
log.info(f"开始使用线程池并发处理文件，线程数：12")
with ThreadPoolExecutor(max_workers=12) as executor:
    # 使用map方法提交所有任务并等待完成
    list(executor.map(process_file_safe, all_files_paths))

# 输出统计信息
log.info(f"文件处理完成！统计信息：")
log.info(f"总文件数：{stats['total_files']}")
log.info(f"成功处理：{stats['success_count']}")
log.info(f"跳过文件：{stats['skip_count']}")
log.info(f"失败文件：{stats['error_count']}")

# 输出每个文件夹下的文件数（去重，避免重复输出）
unique_folders = set()
for file_path in all_files_paths:
    file_classify = get_file_relative_dir(file_path, base_folder)
    unique_folders.add(file_classify)

for folder_path in sorted(unique_folders):
    log.info(f"文件夹：{folder_path}，文件数：{len(list_files(os.path.join(base_folder, folder_path)))}")
