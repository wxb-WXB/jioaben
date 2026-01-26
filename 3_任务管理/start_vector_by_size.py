"""
按文件大小分批开始向量化任务

优先处理小文件，按照以下顺序：
1. 0-10M 的文件先开始向量
2. 10-20M 的文件
3. 20-30M 的文件
4. 30-40M 的文件
5. 40-50M 的文件
6. 50M以上的文件最后向量

这样可以让小文件先完成，避免大文件阻塞队列
"""
import sys
import os
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset

# ============ 配置区域 ============
API_KEY = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 工作空间配置
WORKSPACE_IDS = [
    ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库"),
    ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "第二个知识库"),
]

# 文件大小分段（单位：MB）
# 格式：[(最小MB, 最大MB, 描述), ...]
SIZE_RANGES = [
    (0, 10, "0-10M"),
    (10, 20, "10-20M"),
    (20, 30, "20-30M"),
    (30, 40, "30-40M"),
    (40, 50, "40-50M"),
    (50, float('inf'), "50M+"),
]

# 并发配置
MAX_WORKERS = 5          # 并发线程数
REQUEST_INTERVAL = 0.5   # 请求间隔（秒）

# 是否为测试模式（只统计不执行）
DRY_RUN = True
# ==================================

# 配置日志
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

log_filename = os.path.join(logs_dir, f"start_vector_by_size_{datetime.now().strftime('%Y-%m-%d')}.log")

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
            parse_enhance=True,  # 精准解析
            image_task=False,    # 默认不开启图片索引
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


def process_size_range(lingyan_dataset, docs_by_size, size_label):
    """
    处理某个大小区间的所有文档
    """
    docs = docs_by_size.get(size_label, [])
    if not docs:
        log.info(f"[{size_label}] 没有需要向量化的文档")
        return
    
    log.info(f"\n{'='*60}")
    log.info(f"开始处理 [{size_label}] 区间的文档，共 {len(docs)} 个")
    log.info(f"{'='*60}")
    
    # 按文件大小从小到大排序
    docs.sort(key=lambda x: x['size_mb'])
    
    for doc_info in docs:
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
            else:
                stats['error_count'] += 1
    
    log.info(f"[{size_label}] 处理完成")


def main():
    log.info("="*60)
    log.info("按文件大小分批开始向量化任务")
    log.info("="*60)
    
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
                
                # 检查是否需要向量化
                if needs_vector_task(doc):
                    stats['need_vector_docs'] += 1
                    
                    size_label = get_size_range_label(size_mb)
                    docs_by_size[size_label].append({
                        'dataset_id': dataset_id,
                        'dataset_name': dataset_name,
                        'doc_id': doc_id,
                        'doc_name': doc_name,
                        'size_bytes': size_bytes,
                        'size_mb': size_mb,
                        'workspace': ws_name,
                    })
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
        log.info(f"\n即将按顺序开始 {stats['need_vector_docs']} 个文档的向量化任务...")
        log.info("按 Ctrl+C 取消，3秒后开始...")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            log.info("已取消")
            return
    
    # 按大小区间顺序处理
    for min_mb, max_mb, label in SIZE_RANGES:
        process_size_range(lingyan_dataset, docs_by_size, label)
    
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
