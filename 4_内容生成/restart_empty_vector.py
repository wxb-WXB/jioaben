"""
重启向量化内容为空的文档
- 扫描知识库中向量化已完成但内容为空的文档（hit_count=0 或 completed_segments=0）
- 为这些文档重新启动向量化任务
- 详细日志输出
"""
import sys
import time
import os
import logging
from datetime import datetime

# 设置控制台编码
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset
from models import FolderMap

# ============== 配置区域 ==============

# API 配置
API_KEY = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 工作空间配置
WORKSPACE_ID = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"
WORKSPACE_NAME = "环北工程知识库"

# 处理配置
REQUEST_INTERVAL = 1      # 每个请求成功后等待的时间（秒）
MAX_RETRIES = 3           # 单个文档最大重试次数
RETRY_INTERVAL = 2        # 重试间隔（秒）

# 是否为测试模式（只扫描统计，不实际执行）
DRY_RUN = False

# ============== 配置结束 ==============

# 配置日志
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

log_filename = os.path.join(logs_dir, f"restart_empty_vector_{datetime.now().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

dataset_api = LingyanDataset(API_KEY)


def get_folder_path(folder_id):
    """根据 folder_id 获取文件夹路径"""
    if not folder_id:
        return "根目录"
    try:
        folder = FolderMap.get_or_none(FolderMap.id == folder_id)
        if folder:
            return folder.folderPath
    except:
        pass
    return f"未知路径(folder_id={folder_id})"


def get_doc_status(doc):
    """
    从文档的 tasks 字段获取向量化任务状态
    返回: (status, task_type)
    状态值：
    - no_task: 没有任务
    - completed/success: 成功
    - indexing/parsing/waiting/queuing: 进行中
    - error/failed: 失败
    - cancelled: 已取消
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


def is_vector_completed(doc):
    """
    判断文档向量化是否已完成
    """
    status, _ = get_doc_status(doc)
    return status in ["completed", "success"]


def is_empty_vector(doc):
    """
    判断文档的向量化内容是否为空（需要重新启动向量化）
    
    条件：向量化已完成，但 hit_count=0 或 completed_segments=0
    即：任务完成了，但实际没有切片/向量内容
    """
    # 首先检查是否向量化已完成
    if not is_vector_completed(doc):
        return False  # 未完成的不算"内容为空"
    
    # 检查切片/命中数量是否为0
    hit_count = doc.get("hit_count", 0)
    completed_segments = doc.get("completed_segments", 0)
    segment_count = doc.get("segment_count", 0)
    tokens = doc.get("tokens", 0)
    
    # 任何一个表示内容的字段为0，都算内容为空
    if hit_count == 0 and completed_segments == 0 and segment_count == 0 and tokens == 0:
        return True
    
    return False


def start_vector_task(dataset_id, document_id, document_name, is_pdf=False):
    """
    为文档启动向量化任务
    返回: (success: bool, message: str)
    """
    try:
        # 调用创建任务API
        status_code, response = dataset_api.create_task(
            dataset_id=dataset_id,
            document_id=document_id,
            image_task=False,          # 不开启图片索引
            parse_enhance=is_pdf       # PDF开启精准解析
        )
        
        if status_code == 200:
            return True, "向量化任务启动成功"
        else:
            return False, f"API返回错误: status={status_code}, response={response}"
            
    except Exception as e:
        return False, f"请求异常: {str(e)}"


def scan_and_restart(workspace_id, workspace_name):
    """
    扫描知识库，为没有向量化内容的文档重新启动向量化
    """
    log.info(f"正在扫描 [{workspace_name}] 的知识库...")
    status, datasets = dataset_api.list_datasets(workspace_id)
    
    if status != 200:
        log.error(f"获取知识库列表失败: {datasets}")
        return 0, 0, 0
    
    log.info(f"找到 {len(datasets)} 个知识库")
    log.info("=" * 60)
    
    total_success = 0
    total_fail = 0
    total_skip = 0  # 已有向量化内容的文档
    total_empty = 0  # 发现的空向量文档数
    
    for i, ds in enumerate(datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        log.info(f"\n[{i+1}/{len(datasets)}] 扫描知识库: {dataset_name}")
        log.info(f"  目录路径: {folder_path}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id)
            if status != 200:
                log.error(f"  获取文档失败: {documents}")
                continue
            
            # 收集该知识库中向量化内容为空的文档
            docs_to_process = []
            ds_skip = 0
            ds_not_completed = 0
            
            for doc in documents:
                if is_empty_vector(doc):
                    doc_name = doc.get("name", "")
                    docs_to_process.append({
                        "dataset_id": dataset_id,
                        "dataset_name": dataset_name,
                        "document_id": doc.get("id"),
                        "document_name": doc_name,
                        "folder_path": folder_path,
                        "is_pdf": doc_name.lower().endswith('.pdf') if doc_name else False,
                        "hit_count": doc.get("hit_count", 0),
                        "segment_count": doc.get("segment_count", 0),
                        "tokens": doc.get("tokens", 0),
                    })
                elif is_vector_completed(doc):
                    ds_skip += 1  # 向量化完成且有内容
                else:
                    ds_not_completed += 1  # 未完成向量化
            
            total_skip += ds_skip
            total_empty += len(docs_to_process)
            
            if len(docs_to_process) == 0:
                if ds_skip > 0 or ds_not_completed > 0:
                    log.info(f"  已完成且有内容: {ds_skip} 个，未完成: {ds_not_completed} 个，无需处理")
                else:
                    log.info(f"  无文档")
                continue
            
            log.info(f"  发现 {len(docs_to_process)} 个向量化内容为空的文档")
            log.info(f"  已完成且有内容: {ds_skip} 个，未完成: {ds_not_completed} 个")
            
            if DRY_RUN:
                log.info(f"  [测试模式] 跳过实际执行")
                for doc_info in docs_to_process:
                    log.info(f"    - {doc_info['document_name']}")
                continue
            
            log.info("-" * 50)
            
            # 立即处理这个知识库的文档
            for idx, doc_info in enumerate(docs_to_process, 1):
                log.info(f"  [{idx}/{len(docs_to_process)}] 重启向量化: {doc_info['document_name']}")
                log.info(f"    文档ID: {doc_info['document_id']}")
                log.info(f"    当前状态: hit_count={doc_info['hit_count']}, segment_count={doc_info['segment_count']}, tokens={doc_info['tokens']}")
                
                # 调用 API 启动向量化任务
                for attempt in range(1, MAX_RETRIES + 1):
                    success, message = start_vector_task(
                        doc_info['dataset_id'],
                        doc_info['document_id'],
                        doc_info['document_name'],
                        doc_info['is_pdf']
                    )
                    
                    if success:
                        log.info(f"    [成功] {message}")
                        total_success += 1
                        break
                    else:
                        log.warning(f"    [失败] 第{attempt}次尝试: {message}")
                        if attempt < MAX_RETRIES:
                            log.info(f"    等待 {RETRY_INTERVAL} 秒后重试...")
                            time.sleep(RETRY_INTERVAL)
                        else:
                            log.error(f"    [最终失败] 已达最大重试次数({MAX_RETRIES})")
                            log.error(f"    ├─ 目录路径: {folder_path}")
                            log.error(f"    ├─ 知识库: {dataset_name}")
                            log.error(f"    ├─ 文档名: {doc_info['document_name']}")
                            log.error(f"    └─ 文档ID: {doc_info['document_id']}")
                            total_fail += 1
                
                # 成功后等待再处理下一个
                if idx < len(docs_to_process):
                    time.sleep(REQUEST_INTERVAL)
            
            log.info("-" * 50)
            log.info(f"  知识库 [{dataset_name}] 处理完成")
            log.info(f"  当前总计: 成功 {total_success}, 失败 {total_fail}")
                
        except Exception as e:
            log.error(f"  出错: {e}")
    
    return total_success, total_fail, total_skip, total_empty


def main():
    log.info("=" * 60)
    log.info("重启向量化内容为空的文档")
    log.info(f"工作空间: {WORKSPACE_NAME}")
    log.info(f"检测条件: 向量化已完成但 hit_count/segment_count/tokens 全为0")
    log.info(f"模式: {'测试模式（不实际执行）' if DRY_RUN else '正常模式'}")
    log.info(f"每个成功后间隔: {REQUEST_INTERVAL} 秒")
    log.info(f"失败重试次数: {MAX_RETRIES}, 重试间隔: {RETRY_INTERVAL} 秒")
    log.info("=" * 60)
    
    start_time = datetime.now()
    
    success, fail, skip, empty = scan_and_restart(WORKSPACE_ID, WORKSPACE_NAME)
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    log.info("")
    log.info("=" * 60)
    log.info("全部完成！")
    log.info(f"发现向量化内容为空: {empty} 个")
    log.info(f"重启成功: {success}, 重启失败: {fail}")
    log.info(f"向量化完成且有内容(跳过): {skip} 个")
    log.info(f"总耗时: {duration}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
