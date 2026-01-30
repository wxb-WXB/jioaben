# -*- coding: utf-8 -*-
"""
按文件大小分批开始向量化任务

优先处理小文件，按照以下顺序：
1. 0-10M 的文件先开始向量（跳过0K空文件）
2. 10-20M 的文件
3. 20-30M 的文件
4. 30-40M 的文件
5. 40-50M 的文件
6. 50M以上的文件最后向量

注意：0K（小于1KB）的空文件不会被处理

这样可以让小文件先完成，避免大文件阻塞队列

使用方法：
python scripts/vector/start_vector_by_size.py
"""
import sys
import os
import time
import logging
from datetime import datetime
from threading import Lock

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core import LingyanDataset
from src.config import API_KEY, WORKSPACE_IDS, LOGS_DIR

# ============ 配置区域 ============
# 文件大小分段（单位：MB）
# 格式：[(最小MB, 最大MB, 描述), ...]
SIZE_RANGES = [
    (0.001, 10, "0-10M"),      # 0.001MB ≈ 1KB，跳过0K空文件
    (10, 20, "10-20M"),
    (20, 30, "20-30M"),
    (30, 40, "30-40M"),
    (40, 50, "40-50M"),
    (50, float('inf'), "50M+"),
]

# 最小文件大小（字节），小于此值的文件不处理（0K文件）
MIN_FILE_SIZE_BYTES = 1024  # 1KB

# 允许处理的文件类型（扩展名，不带点，小写）
# 只有在此列表中的文件类型才会被向量化
# 设为空列表 [] 表示不限制文件类型，处理所有文件
ALLOWED_EXTENSIONS = [
    "doc",
    "docx",
    # "pdf",
    "txt",
    # "md",
    # "xlsx",
    # "xls",
    # "ppt",
    # "pptx",
]

# 批量配置
MAX_RUNNING_TASKS = 20   # 保持同时运行的任务数量
CHECK_INTERVAL = 30      # 检查任务状态的间隔（秒）
REQUEST_INTERVAL = 0.3   # 每个请求之间的间隔（秒）

# 是否为测试模式（只统计不执行）
DRY_RUN = False
# ==================================

# 配置日志
log_filename = os.path.join(LOGS_DIR, f"start_vector_by_size_{datetime.now().strftime('%Y-%m-%d')}.log")

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
log = logging.getLogger("start_vector_by_size")

# 统计信息
stats = {
    'total_docs': 0,
    'need_vector_docs': 0,
    'started_count': 0,
    'skipped_count': 0,
    'error_count': 0,
}
stats_lock = Lock()


def bytes_to_mb(size_bytes):
    """将字节转换为MB"""
    if size_bytes is None:
        return 0
    try:
        return float(size_bytes) / (1024 * 1024)
    except (ValueError, TypeError):
        return 0


def get_doc_size_bytes(doc):
    """
    获取文档的文件大小（字节）
    尝试多个可能的字段名：word_count, size, file_size
    """
    # 尝试获取文件大小，优先使用 word_count（灵燕API通常用这个字段表示文件大小）
    size = doc.get("word_count")
    if size is not None and size > 0:
        return size
    
    size = doc.get("size")
    if size is not None and size > 0:
        return size
    
    size = doc.get("file_size")
    if size is not None and size > 0:
        return size
    
    # 如果都没有，返回0
    return 0


def get_size_range_label(size_mb):
    """根据文件大小返回所属区间标签"""
    for min_mb, max_mb, label in SIZE_RANGES:
        if min_mb <= size_mb < max_mb:
            return label
    return "未知"


def is_allowed_extension(doc_name):
    """
    检查文件扩展名是否在允许列表中
    如果 ALLOWED_EXTENSIONS 为空列表，则允许所有文件
    """
    if not ALLOWED_EXTENSIONS:
        return True
    
    if not doc_name:
        return False
    
    # 获取文件扩展名（小写，不带点）
    ext = doc_name.lower().rsplit('.', 1)[-1] if '.' in doc_name else ''
    return ext in ALLOWED_EXTENSIONS


def get_file_type_priority(doc_name):
    """
    获取文件类型优先级（数字越小优先级越高）
    文本文件（非PDF）优先，PDF最后处理
    """
    if not doc_name:
        return 99
    
    name_lower = doc_name.lower()
    
    # PDF 最后处理
    if name_lower.endswith('.pdf'):
        return 2
    # 其他文本文件优先
    else:
        return 1


def get_doc_status(doc):
    """
    从文档的 tasks 字段获取向量化任务状态
    返回: (status, task_type)
    """
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task", None
    
    # 优先查找 type=normal 的任务（这是向量化任务）
    normal_task = None
    for task in tasks:
        if task.get("type") == "normal":
            normal_task = task
            break
    
    if normal_task:
        return normal_task.get("status", "unknown"), normal_task.get("type")
    else:
        latest_task = tasks[-1]
        return latest_task.get("status", "unknown"), latest_task.get("type")


def needs_vector_task(doc):
    """
    判断文档是否需要开始向量化任务
    
    需要向量化的情况：
    - 没有任务（no_task）
    - 任务已取消（cancelled）
    - 任务失败（error/failed）
    
    不需要向量化的情况：
    - 已完成（completed/success）
    - 正在进行中（indexing/parsing/waiting/queuing）
    """
    status, _ = get_doc_status(doc)
    
    # 已完成或进行中，不需要重新开始
    if status in ["completed", "success", "indexing", "parsing", "waiting", "queuing"]:
        return False
    
    # 没有任务、已取消、失败，需要开始向量化
    if status in ["no_task", "cancelled", "error", "failed"]:
        return True
    
    # 其他未知状态，默认需要开始
    return True


def start_vector_task(lingyan_dataset, dataset_id, document_id, doc_name, size_mb):
    """
    启动单个文档的向量化任务
    """
    try:
        time.sleep(REQUEST_INTERVAL)  # 限流
        
        if DRY_RUN:
            log.info(f"[DRY_RUN] 将启动向量任务: {doc_name} ({size_mb:.2f}MB)")
            return True
        
        response_code, response = lingyan_dataset.create_task(
            dataset_id=dataset_id,
            document_id=document_id,
            parse_enhance=False,  # 关闭精准解析
            image_task=False,     # 默认不开启图片索引
        )
        
        if response_code == 200:
            log.info(f"✓ 向量任务启动成功: {doc_name} ({size_mb:.2f}MB)")
            return True
        else:
            log.error(f"✗ 向量任务启动失败: {doc_name}, 错误: {response}")
            return False
            
    except Exception as e:
        log.error(f"✗ 向量任务启动异常: {doc_name}, 错误: {str(e)}")
        return False


def process_all_docs_with_pool(lingyan_dataset, all_docs, all_datasets):
    """
    保持固定数量的任务同时运行：
    - 先启动 MAX_RUNNING_TASKS 个任务
    - 然后每隔 CHECK_INTERVAL 秒补充新任务，保持总数为 MAX_RUNNING_TASKS
    - 使用本地计数器跟踪已启动的任务，避免频繁查询API
    """
    total = len(all_docs)
    if total == 0:
        log.info("没有需要向量化的文档")
        return
    
    log.info(f"\n{'='*60}")
    log.info(f"开始处理，共 {total} 个文档")
    log.info(f"保持 {MAX_RUNNING_TASKS} 个任务同时运行")
    log.info(f"{'='*60}")
    
    # 排序：先按文件类型（文本优先，PDF最后），再按大小区间，再按文件大小
    all_docs.sort(key=lambda x: (
        get_file_type_priority(x['doc_name']),
        SIZE_RANGES.index(next((r for r in SIZE_RANGES if r[2] == x['size_label']), SIZE_RANGES[0])),
        x['size_mb']
    ))
    
    idx = 0  # 待启动文档的索引
    active_tasks = 0  # 当前活跃的任务数（本地计数）
    
    while idx < total:
        # 计算本次要启动的数量
        available_slots = MAX_RUNNING_TASKS - active_tasks
        to_start = min(available_slots, total - idx)
        
        if to_start > 0:
            log.info(f"\n{'='*60}")
            log.info(f"当前活跃任务: {active_tasks} 个，可启动: {available_slots} 个")
            log.info(f"准备启动第 {idx+1} ~ {idx+to_start} 个文档（共 {to_start} 个）")
            log.info(f"剩余待处理: {total - idx - to_start} 个")
            log.info(f"{'='*60}")
            
            # 启动任务
            for i in range(to_start):
                doc_info = all_docs[idx]
                success = start_vector_task(
                    lingyan_dataset,
                    doc_info['dataset_id'],
                    doc_info['doc_id'],
                    doc_info['doc_name'],
                    doc_info['size_mb']
                )
                
                with stats_lock:
                    if success:
                        stats['started_count'] += 1
                        active_tasks += 1
                    else:
                        stats['error_count'] += 1
                
                idx += 1
        
        # 如果还有更多文档，等待一段时间，假设部分任务已完成
        if idx < total:
            log.info(f"\n本轮启动完成，等待 {CHECK_INTERVAL} 秒...")
            log.info(f"已启动: {stats['started_count']} / {total}")
            time.sleep(CHECK_INTERVAL)
            
            # 假设每轮有一定比例的任务完成（估计值）
            # 这里假设每轮完成约 1/3 的活跃任务
            completed_estimate = max(1, active_tasks // 3)
            active_tasks = max(0, active_tasks - completed_estimate)
            log.info(f"估计已完成 {completed_estimate} 个任务，当前活跃任务约 {active_tasks} 个")
    
    log.info(f"\n{'='*60}")
    log.info(f"所有 {total} 个文档的任务已启动完成")
    log.info(f"{'='*60}")


def main():
    log.info("="*60)
    log.info("按文件大小分批开始向量化任务")
    log.info("="*60)
    
    if ALLOWED_EXTENSIONS:
        log.info(f"只处理以下文件类型: {', '.join(ALLOWED_EXTENSIONS)}")
    else:
        log.info("处理所有文件类型（无限制）")
    
    if DRY_RUN:
        log.info("【测试模式】只统计不执行")
    
    lingyan_dataset = LingyanDataset(API_KEY)
    
    # 收集所有需要向量化的文档，按大小分组
    docs_by_size = {label: [] for _, _, label in SIZE_RANGES}
    size_stats = {label: 0 for _, _, label in SIZE_RANGES}
    
    # 获取所有工作空间的知识库
    all_datasets = []
    for ws_id, ws_name in WORKSPACE_IDS:
        log.info(f"正在获取 [{ws_name}] 的知识库列表...")
        status, datasets_list = lingyan_dataset.list_datasets(ws_id)
        if status == 200:
            log.info(f"[{ws_name}] 获取到 {len(datasets_list)} 个知识库")
            for ds in datasets_list:
                ds["_workspace_id"] = ws_id
                ds["_workspace_name"] = ws_name
            all_datasets.extend(datasets_list)
        else:
            log.error(f"[{ws_name}] 获取知识库列表失败: {datasets_list}")
    
    log.info(f"\n总共获取到 {len(all_datasets)} 个知识库")
    
    # 遍历所有知识库，收集需要向量化的文档
    log.info("\n正在扫描文档...")
    for i, ds in enumerate(all_datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        ws_name = ds.get("_workspace_name", "未知")
        
        try:
            status, documents = lingyan_dataset.list_documents(dataset_id)
            if status != 200:
                continue
            
            for doc in documents:
                stats['total_docs'] += 1
                
                doc_id = doc.get("id")
                doc_name = doc.get("name", "未知")
                # 获取文件大小
                size_bytes = get_doc_size_bytes(doc)
                size_mb = bytes_to_mb(size_bytes)
                
                # 跳过 0K 空文件（小于 MIN_FILE_SIZE_BYTES）
                if size_bytes < MIN_FILE_SIZE_BYTES:
                    stats['skipped_count'] += 1
                    log.debug(f"跳过0K文件: {doc_name} ({size_bytes} bytes)")
                    continue
                
                # 检查文件类型是否在允许列表中
                if not is_allowed_extension(doc_name):
                    stats['skipped_count'] += 1
                    log.debug(f"跳过非指定类型文件: {doc_name}")
                    continue
                
                # 检查是否需要向量化
                if needs_vector_task(doc):
                    stats['need_vector_docs'] += 1
                    
                    size_label = get_size_range_label(size_mb)
                    doc_info = {
                        'dataset_id': dataset_id,
                        'dataset_name': dataset_name,
                        'doc_id': doc_id,
                        'doc_name': doc_name,
                        'size_bytes': size_bytes,
                        'size_mb': size_mb,
                        'size_label': size_label,
                        'workspace': ws_name,
                    }
                    docs_by_size[size_label].append(doc_info)
                    size_stats[size_label] += 1
                else:
                    stats['skipped_count'] += 1
                    
        except Exception as e:
            log.error(f"[{ws_name}] [{dataset_name}] 扫描出错: {e}")
    
    # 输出统计信息
    log.info(f"\n{'='*60}")
    log.info("扫描完成，统计信息：")
    log.info(f"{'='*60}")
    log.info(f"总文档数: {stats['total_docs']}")
    log.info(f"需要向量化的文档数: {stats['need_vector_docs']}")
    log.info(f"跳过的文档数（已完成/进行中）: {stats['skipped_count']}")
    
    log.info(f"\n按文件大小分布：")
    for _, _, label in SIZE_RANGES:
        count = size_stats[label]
        log.info(f"  {label}: {count} 个文档")
    
    if stats['need_vector_docs'] == 0:
        log.info("\n没有需要向量化的文档，退出")
        return
    
    # 确认是否继续
    if not DRY_RUN:
        log.info(f"\n即将启动 {stats['need_vector_docs']} 个文档的向量化任务...")
        log.info(f"保持 {MAX_RUNNING_TASKS} 个任务同时运行，完成一个补充一个")
        log.info("按 Ctrl+C 取消，3秒后开始...")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            log.info("已取消")
            return
    
    # 合并所有文档到一个列表
    all_docs = []
    for _, _, label in SIZE_RANGES:
        all_docs.extend(docs_by_size[label])
    
    # 保持固定数量任务运行
    process_all_docs_with_pool(lingyan_dataset, all_docs, all_datasets)
    
    # 最终统计
    log.info(f"\n{'='*60}")
    log.info("任务完成，最终统计：")
    log.info(f"{'='*60}")
    log.info(f"总文档数: {stats['total_docs']}")
    log.info(f"需要向量化: {stats['need_vector_docs']}")
    log.info(f"成功启动: {stats['started_count']}")
    log.info(f"启动失败: {stats['error_count']}")
    log.info(f"跳过: {stats['skipped_count']}")


if __name__ == "__main__":
    main()
