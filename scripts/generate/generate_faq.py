# -*- coding: utf-8 -*-
"""
FAQ问答生成脚本

功能：
- 扫描知识库中向量化成功的文档
- 检查文档是否已有FAQ任务
- 滑动窗口模式：始终保持N个任务在运行，完成一个立即补充一个

使用方法：
python scripts/generate/generate_faq.py
"""
import sys
import time
import os
import requests
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 设置控制台编码
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core import LingyanDataset
from src.core.models import FolderMap
from src.config import API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACE_NAME

# ============== 配置区域 ==============
# 处理配置
CONCURRENT_TASKS = 5      # 同时运行的任务数量（滑动窗口大小）
CHECK_INTERVAL = 5        # 检查任务状态的间隔（秒）
MAX_WAIT_TIME = 2400      # 单个任务最大等待时间（秒），超时则跳过
REQUEST_INTERVAL = 0.5    # 启动任务时每个请求之间的间隔（秒）
MAX_RETRIES = 3           # 单个文档最大重试次数
RETRY_INTERVAL = 5        # 重试间隔（秒）
# ============== 配置结束 ==============

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
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
    """从文档的 tasks 字段获取向量化任务状态"""
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task", None
    
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


def is_vector_success(doc):
    """判断文档是否向量化成功"""
    doc_status, _ = get_doc_status(doc)
    return doc_status in ["completed", "success"]


def get_faq_task_status(doc):
    """获取文档的FAQ任务状态"""
    tasks = doc.get("tasks", [])
    for task in tasks:
        if task.get("type") == "faq":
            status = task.get("status", "unknown")
            return True, status
    return False, None


def start_faq_task(dataset_id, document_id):
    """启动FAQ问答生成任务"""
    url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/tasks"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
        "X-Workspace-Id": WORKSPACE_ID,
        "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "dataset_id": dataset_id,
        "document_id": document_id,
        "type": "faq"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                return True, "FAQ任务启动成功"
            else:
                return False, f"API返回错误: code={result.get('code')}, msg={result.get('msg')}"
        else:
            return False, f"HTTP状态码: {response.status_code}"
            
    except requests.exceptions.Timeout:
        return False, "请求超时"
    except requests.exceptions.RequestException as e:
        return False, f"请求异常: {str(e)}"
    except Exception as e:
        return False, f"未知错误: {str(e)}"


def get_document_info(dataset_id, document_id):
    """获取单个文档的最新信息"""
    url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "X-Workspace-Id": WORKSPACE_ID,
        "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                return True, result.get("data", {})
            else:
                return False, None
        else:
            return False, None
            
    except Exception as e:
        return False, None


def start_single_task(dataset_id, doc_info):
    """启动单个文档的FAQ任务（不等待完成）"""
    document_id = doc_info['document_id']
    
    for attempt in range(1, MAX_RETRIES + 1):
        success, message = start_faq_task(dataset_id, document_id)
        
        if success:
            return True, message
        else:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_INTERVAL)
            else:
                return False, f"启动失败: {message}"
    
    return False, "启动失败"


def process_sliding_window(dataset_id, dataset_name, folder_path, docs_to_process):
    """滑动窗口模式处理文档"""
    total_docs = len(docs_to_process)
    if total_docs == 0:
        return 0, 0
    
    running_tasks = {}
    pending_docs = list(docs_to_process)
    
    success_count = 0
    fail_count = 0
    processed_count = 0
    
    log.info(f"  滑动窗口模式: 同时运行 {CONCURRENT_TASKS} 个任务")
    log.info(f"  总共需要处理: {total_docs} 个文档")
    log.info(f"  当前知识库: {dataset_name}")
    log.info(f"  文件夹路径: {folder_path}")
    log.info("-" * 50)
    
    while pending_docs or running_tasks:
        while len(running_tasks) < CONCURRENT_TASKS and pending_docs:
            doc_info = pending_docs.pop(0)
            document_id = doc_info['document_id']
            document_name = doc_info['document_name']
            
            success, message = start_single_task(dataset_id, doc_info)
            
            if success:
                running_tasks[document_id] = {
                    'doc': doc_info,
                    'start_time': time.time()
                }
                processed_count += 1
                log.info(f"    [{processed_count}/{total_docs}] 已启动: [{folder_path}] {document_name[:40]}...")
            else:
                fail_count += 1
                processed_count += 1
                log.warning(f"    [{processed_count}/{total_docs}] 启动失败: [{folder_path}] {document_name[:40]}...")
            
            time.sleep(REQUEST_INTERVAL)
        
        if not running_tasks:
            break
        
        completed_ids = []
        timeout_ids = []
        
        for doc_id, task_info in running_tasks.items():
            doc = task_info['doc']
            start_time = task_info['start_time']
            elapsed = time.time() - start_time
            
            if elapsed > MAX_WAIT_TIME:
                timeout_ids.append(doc_id)
                log.warning(f"      ⏱ 超时: [{folder_path}] {doc['document_name'][:40]}... ({int(elapsed)}秒)")
                continue
            
            success, doc_info = get_document_info(dataset_id, doc_id)
            if not success:
                continue
            
            has_faq, faq_status = get_faq_task_status(doc_info)
            if not has_faq:
                continue
            
            if faq_status in ["completed", "success"]:
                completed_ids.append((doc_id, True))
                log.info(f"      ✓ 完成: [{folder_path}] {doc['document_name'][:40]}... ({int(elapsed)}秒)")
            elif faq_status in ["failed", "error"]:
                completed_ids.append((doc_id, False))
                log.warning(f"      ✗ 失败: [{folder_path}] {doc['document_name'][:40]}...")
        
        for doc_id, is_success in completed_ids:
            del running_tasks[doc_id]
            if is_success:
                success_count += 1
            else:
                fail_count += 1
        
        for doc_id in timeout_ids:
            del running_tasks[doc_id]
            fail_count += 1
        
        if running_tasks:
            remaining = len(pending_docs)
            running = len(running_tasks)
            log.info(f"      运行中: {running}, 待处理: {remaining}, 成功: {success_count}, 失败: {fail_count}")
            time.sleep(CHECK_INTERVAL)
    
    return success_count, fail_count


def scan_and_process(workspace_id, workspace_name):
    """扫描知识库，逐个处理文档的FAQ任务"""
    log.info(f"正在扫描 [{workspace_name}] 的知识库...")
    status, datasets = dataset_api.list_datasets(workspace_id)
    
    if status != 200:
        log.error(f"获取知识库列表失败: {datasets}")
        return 0, 0, 0
    
    log.info(f"找到 {len(datasets)} 个知识库")
    log.info("=" * 60)
    
    total_success = 0
    total_fail = 0
    total_skip = 0
    
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
                log.error(f"  获取文档失败")
                continue
            
            docs_to_process = []
            ds_skip_completed = 0
            ds_skip_running = 0
            
            for doc in documents:
                if not is_vector_success(doc):
                    continue
                
                has_faq, faq_status = get_faq_task_status(doc)
                
                if has_faq:
                    if faq_status in ["completed", "success"]:
                        ds_skip_completed += 1
                        continue
                    elif faq_status in ["queuing", "running", "processing"]:
                        ds_skip_running += 1
                        continue
                
                docs_to_process.append({
                    "document_id": doc.get("id"),
                    "document_name": doc.get("name"),
                })
            
            total_skip += ds_skip_completed
            
            if ds_skip_completed > 0:
                log.info(f"  已完成FAQ: {ds_skip_completed} 个(跳过)")
            if ds_skip_running > 0:
                log.info(f"  进行中FAQ: {ds_skip_running} 个(跳过)")
            
            if len(docs_to_process) == 0:
                if ds_skip_completed == 0 and ds_skip_running == 0:
                    log.info(f"  无向量化成功的文档")
                continue
            
            log.info(f"  需要启动FAQ: {len(docs_to_process)} 个")
            
            success_count, fail_count = process_sliding_window(dataset_id, dataset_name, folder_path, docs_to_process)
            
            total_success += success_count
            total_fail += fail_count
            
            log.info("-" * 50)
            log.info(f"  知识库 [{dataset_name}] 处理完成")
            log.info(f"  当前总计: 成功 {total_success}, 失败 {total_fail}, 跳过 {total_skip}")
                
        except Exception as e:
            log.error(f"  出错: {e}")
    
    return total_success, total_fail, total_skip


def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    log.info("=" * 60)
    log.info("FAQ问答生成任务工具")
    log.info(f"模式: 滑动窗口（始终保持 {CONCURRENT_TASKS} 个任务运行，完成一个补充一个）")
    log.info(f"检查间隔: {CHECK_INTERVAL} 秒")
    log.info(f"单任务最大等待: {MAX_WAIT_TIME} 秒")
    log.info(f"失败重试次数: {MAX_RETRIES}")
    log.info("=" * 60)
    
    start_time = datetime.now()
    
    success, fail, skip = scan_and_process(WORKSPACE_ID, WORKSPACE_NAME)
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    log.info("")
    log.info("=" * 60)
    log.info("全部完成！")
    log.info(f"成功: {success}, 失败: {fail}, 跳过(已完成): {skip}")
    log.info(f"总耗时: {duration}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
