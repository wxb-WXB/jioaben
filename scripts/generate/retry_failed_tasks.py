# -*- coding: utf-8 -*-
"""
失败文档重试脚本

功能：
- 遍历知识库，检测失败/无任务的文档
- 支持两种模式：批次模式 和 轮询模式
- 批次模式：每次启动N个任务，等待一段时间，继续下一批
- 轮询模式：始终保持N个任务在运行，完成一个立即补充一个

使用方法：
python scripts/generate/retry_failed_tasks.py
"""
import sys
import time
import os
import requests

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
from src.config import API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACES

# ============================================================
# 配置参数 - 修改这里来控制脚本行为
# ============================================================

# workspace ID 配置
workspace_ids = [(ws["id"], ws["name"]) for ws in WORKSPACES]

# 只处理指定目录下的知识库（为空则处理所有目录）
TARGET_FOLDER_PATH = None

# ------------------------------
# 运行模式
# ------------------------------
# 'batch'   - 批次模式：启动N个任务，等待一段时间，继续下一批
# 'polling' - 轮询模式：始终保持N个任务在运行，完成一个立即补充一个
RUN_MODE = 'polling'

# ------------------------------
# 批次模式配置
# ------------------------------
BATCH_SIZE = 40          # 每批启动的任务数
BATCH_WAIT = 120         # 每批完成后等待时间（秒）
REQUEST_INTERVAL = 0.4   # 每次启动任务之间的间隔（秒）

# ------------------------------
# 轮询模式配置
# ------------------------------
WINDOW_SIZE = 30         # 同时运行的任务数量（滑动窗口大小）
POLL_INTERVAL = 5        # 检查任务状态的间隔（秒）
MAX_WAIT_TIME = 1800     # 单个任务最大等待时间（秒），超时则跳过

# ------------------------------
# 网络重试控制
# ------------------------------
MAX_RETRIES = 3          # 网络错误最大重试次数
RETRY_DELAY = 5          # 重试间隔（秒）

# ------------------------------
# 文件类型过滤（基于API返回的type字段）
# ------------------------------
# INCLUDE_FILE_TYPES = {'doc', 'docx', 'txt', 'md', 'wps'}
INCLUDE_FILE_TYPES = {'pdf'}
# INCLUDE_FILE_TYPES = None  # 处理所有类型

EXCLUDE_FILE_TYPES = None

# ------------------------------
# 文档状态过滤
# ------------------------------
RETRY_STATUS = ['error', 'failed', 'cancelled', 'no_task']

# ------------------------------
# 向量化任务配置
# ------------------------------
SPLIT_MODE = 'common'    # 'common'(普通切割) 或 'semantic'(语义切割)
PARSE_ENHANCE = True    # 是否开启精准解析
IMAGE_TASK = False       # 是否处理图片任务

# ============================================================
# 以下为脚本逻辑
# ============================================================

# 禁用 SSL 警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

dataset_api = LingyanDataset(API_KEY)

# 通用请求头（用于轮询模式检查任务状态）
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json",
    "X-Workspace-Id": WORKSPACE_ID,
    "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


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


def should_process_file(doc_type):
    """判断是否应该处理该文件类型"""
    if EXCLUDE_FILE_TYPES and doc_type in EXCLUDE_FILE_TYPES:
        return False
    if INCLUDE_FILE_TYPES:
        return doc_type in INCLUDE_FILE_TYPES
    return True


def list_documents_with_retry(dataset_id, workspace_id):
    """带重试的获取文档列表"""
    for attempt in range(MAX_RETRIES):
        try:
            status, documents = dataset_api.list_documents(dataset_id, workspace_id)
            if status == 200:
                return status, documents
            return status, documents
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f" - 网络错误，{wait_time}秒后重试({attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait_time)
            else:
                raise e
    return 500, "重试失败"


def start_task(doc, workspace_id):
    """启动单个文档的向量化任务"""
    for attempt in range(MAX_RETRIES):
        try:
            status, result = dataset_api.create_task(
                dataset_id=doc['dataset_id'],
                document_id=doc['document_id'],
                split_mode=SPLIT_MODE,
                task_type="normal",
                image_task=IMAGE_TASK,
                parse_enhance=PARSE_ENHANCE,
                workspace_id=workspace_id
            )
            return status == 200, result
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f"    网络错误，{wait_time}秒后重试({attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait_time)
            else:
                return False, str(e)
    return False, "重试失败"


def get_document_info(dataset_id, document_id):
    """获取单个文档的最新信息（用于轮询模式）"""
    url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                return True, result.get("data", {})
    except:
        pass
    return False, None


def print_config():
    """打印当前配置"""
    print("="*60)
    print("当前配置:")
    print("="*60)
    
    if RUN_MODE == 'batch':
        print(f"  运行模式: 批次模式 (batch)")
        print(f"  批次大小: {BATCH_SIZE}")
        print(f"  批次等待: {BATCH_WAIT} 秒")
        print(f"  请求间隔: {REQUEST_INTERVAL} 秒")
    else:
        print(f"  运行模式: 轮询模式 (polling)")
        print(f"  窗口大小: {WINDOW_SIZE}")
        print(f"  轮询间隔: {POLL_INTERVAL} 秒")
        print(f"  最大等待: {MAX_WAIT_TIME} 秒")
    
    print(f"  切割模式: {SPLIT_MODE}")
    print(f"  精准解析: {'开启' if PARSE_ENHANCE else '关闭'}")
    
    if INCLUDE_FILE_TYPES:
        print(f"  处理文件类型: {', '.join(sorted(INCLUDE_FILE_TYPES))}")
    else:
        print(f"  处理文件类型: 全部")
    
    print(f"  重试状态: {', '.join(RETRY_STATUS)}")
    print("="*60)


def collect_all_docs():
    """收集所有需要处理的文档"""
    all_docs = []
    
    for ws_id, ws_name in workspace_ids:
        print(f"\n正在扫描 [{ws_name}] 的知识库...")
        
        try:
            status, datasets = dataset_api.list_datasets(ws_id)
        except Exception as e:
            print(f"获取知识库列表失败: {e}")
            continue
        
        if status != 200:
            print(f"获取知识库列表失败: {datasets}")
            continue
        
        print(f"找到 {len(datasets)} 个知识库")
        
        for i, ds in enumerate(datasets):
            dataset_id = ds.get("id")
            dataset_name = ds.get("name")
            folder_id = ds.get("folder_id")
            folder_path = get_folder_path(folder_id)
            
            if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                continue
            
            print(f"[{i+1}/{len(datasets)}] 扫描: {dataset_name}", end=" ")
            
            try:
                status, documents = list_documents_with_retry(dataset_id, ws_id)
                if status != 200:
                    print("- 获取文档失败")
                    continue
                
                found_count = 0
                for doc in documents:
                    doc_status, _ = get_doc_status(doc)
                    
                    if doc_status not in RETRY_STATUS:
                        continue
                    
                    doc_name = doc.get("name", "")
                    doc_type = doc.get("type", "")
                    
                    if not should_process_file(doc_type):
                        continue
                    
                    # 构建路径
                    if folder_path and folder_path != "根目录":
                        full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                    else:
                        full_path = f"{dataset_name}/{doc_name}"
                    
                    all_docs.append({
                        'dataset_id': dataset_id,
                        'document_id': doc.get("id"),
                        'name': doc_name,
                        'type': doc_type,
                        'path': full_path,
                        'workspace_id': ws_id,
                    })
                    found_count += 1
                
                if found_count > 0:
                    print(f"- 发现 {found_count} 个")
                else:
                    print("- 无需处理")
                    
            except Exception as e:
                print(f"- 出错: {e}")
                time.sleep(RETRY_DELAY)
    
    return all_docs


def run_batch_mode():
    """批次模式：启动N个任务，等待一段时间，继续下一批"""
    from datetime import datetime
    
    start_time = datetime.now()
    
    print("="*60)
    print(f"失败/无任务文档重试工具（批次模式）")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print_config()
    
    # 统计
    total_success = 0
    total_fail = 0
    total_started = 0
    batch_num = 1
    batch_count = 0
    
    # 记录
    success_docs = []
    failed_docs = []
    
    # 遍历所有工作空间
    for ws_id, ws_name in workspace_ids:
        print(f"\n正在扫描 [{ws_name}] 的知识库...")
        
        try:
            status, datasets = dataset_api.list_datasets(ws_id)
        except Exception as e:
            print(f"获取知识库列表失败: {e}")
            continue
        
        if status != 200:
            print(f"获取知识库列表失败: {datasets}")
            continue
        
        print(f"找到 {len(datasets)} 个知识库")
        
        for i, ds in enumerate(datasets):
            dataset_id = ds.get("id")
            dataset_name = ds.get("name")
            folder_id = ds.get("folder_id")
            folder_path = get_folder_path(folder_id)
            
            if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                continue
            
            print(f"\n[{i+1}/{len(datasets)}] 扫描知识库: {dataset_name}")
            
            try:
                status, documents = list_documents_with_retry(dataset_id, ws_id)
                if status != 200:
                    print(f"  获取文档失败")
                    continue
                
                found_count = 0
                for doc in documents:
                    doc_status, _ = get_doc_status(doc)
                    
                    if doc_status not in RETRY_STATUS:
                        continue
                    
                    doc_name = doc.get("name", "")
                    doc_type = doc.get("type", "")
                    
                    if not should_process_file(doc_type):
                        continue
                    
                    found_count += 1
                    total_started += 1
                    batch_count += 1
                    
                    # 构建路径
                    if folder_path and folder_path != "根目录":
                        full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                    else:
                        full_path = f"{dataset_name}/{doc_name}"
                    
                    print(f"\n  [批次{batch_num}][{batch_count}/{BATCH_SIZE}] 启动: {doc_name} [type={doc_type}]")
                    print(f"    路径: {full_path}")
                    
                    # 启动任务
                    success, result = start_task({
                        'dataset_id': dataset_id,
                        'document_id': doc.get("id"),
                    }, ws_id)
                    
                    if success:
                        print(f"    ✓ 成功")
                        total_success += 1
                        success_docs.append({
                            'name': doc_name,
                            'path': full_path,
                            'type': doc_type,
                        })
                    else:
                        print(f"    ✗ 失败: {result}")
                        total_fail += 1
                        failed_docs.append({
                            'name': doc_name,
                            'path': full_path,
                            'type': doc_type,
                            'error': str(result),
                        })
                    
                    # 请求间隔
                    time.sleep(REQUEST_INTERVAL)
                    
                    # 批次满了，等待
                    if batch_count >= BATCH_SIZE:
                        print(f"\n{'='*60}")
                        print(f"第 {batch_num} 批完成！成功: {total_success}, 失败: {total_fail}")
                        print(f"等待 {BATCH_WAIT} 秒后继续...")
                        print(f"{'='*60}")
                        time.sleep(BATCH_WAIT)
                        batch_num += 1
                        batch_count = 0
                
                if found_count > 0:
                    print(f"\n  知识库 [{dataset_name}] 处理了 {found_count} 个文档")
                else:
                    print(f"  无需处理")
                    
            except Exception as e:
                print(f"  出错: {e}")
                time.sleep(RETRY_DELAY)
    
    end_time = datetime.now()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0]
    
    # 最终统计
    print(f"\n{'='*60}")
    print(f"全部完成！")
    print(f"{'='*60}")
    print(f"  开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  总耗时: {duration_str}")
    print(f"  启动任务数: {total_started}")
    print(f"  成功: {total_success}")
    print(f"  失败: {total_fail}")
    if total_started > 0:
        success_rate = total_success / total_started * 100
        print(f"  成功率: {success_rate:.1f}%")
    
    # 显示失败列表
    if failed_docs:
        print(f"\n{'='*60}")
        print(f"失败文档列表 ({len(failed_docs)} 个):")
        print(f"{'='*60}")
        for doc in failed_docs[:50]:
            print(f"  {doc['path']}")
            print(f"    错误: {doc['error']}")
        if len(failed_docs) > 50:
            print(f"  ... 还有 {len(failed_docs) - 50} 个")
    
    print(f"{'='*60}")


def run_polling_mode():
    """轮询模式：始终保持N个任务在运行，完成一个立即补充一个"""
    from datetime import datetime
    
    start_time = datetime.now()
    
    print("="*60)
    print(f"失败/无任务文档重试工具（轮询模式）")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print_config()
    
    # 先收集所有需要处理的文档
    print("\n" + "="*60)
    print("第一阶段：收集需要处理的文档")
    print("="*60)
    
    all_docs = collect_all_docs()
    
    if not all_docs:
        print("\n没有需要处理的文档")
        return
    
    print(f"\n共收集到 {len(all_docs)} 个需要处理的文档")
    
    # 第二阶段：滑动窗口处理
    print("\n" + "="*60)
    print("第二阶段：滑动窗口处理")
    print(f"窗口大小: {WINDOW_SIZE}, 轮询间隔: {POLL_INTERVAL}秒")
    print("="*60)
    
    running_tasks = {}  # document_id -> {doc_info, start_time}
    pending_docs = list(all_docs)
    
    total_success = 0
    total_fail = 0
    processed_count = 0
    total_docs = len(all_docs)
    
    success_docs = []
    failed_docs = []
    
    while pending_docs or running_tasks:
        # 填充窗口
        while len(running_tasks) < WINDOW_SIZE and pending_docs:
            doc = pending_docs.pop(0)
            document_id = doc['document_id']
            
            processed_count += 1
            print(f"\n[{processed_count}/{total_docs}] 启动: {doc['name']} [type={doc['type']}]")
            print(f"  路径: {doc['path']}")
            
            success, result = start_task(doc, doc['workspace_id'])
            
            if success:
                running_tasks[document_id] = {
                    'doc': doc,
                    'start_time': time.time()
                }
                print(f"  ✓ 已启动，当前运行中: {len(running_tasks)}")
            else:
                print(f"  ✗ 启动失败: {result}")
                total_fail += 1
                failed_docs.append({
                    'name': doc['name'],
                    'path': doc['path'],
                    'type': doc['type'],
                    'error': str(result),
                })
            
            time.sleep(REQUEST_INTERVAL)
        
        if not running_tasks:
            break
        
        # 检查运行中的任务
        completed_ids = []
        timeout_ids = []
        
        for doc_id, task_info in running_tasks.items():
            doc = task_info['doc']
            start_time_task = task_info['start_time']
            elapsed = time.time() - start_time_task
            
            # 超时检查
            if elapsed > MAX_WAIT_TIME:
                timeout_ids.append(doc_id)
                print(f"  ⏱ 超时: {doc['name']} ({int(elapsed)}秒)")
                continue
            
            # 获取最新状态
            success, doc_info = get_document_info(doc['dataset_id'], doc_id)
            if not success:
                continue
            
            doc_status, _ = get_doc_status(doc_info)
            
            if doc_status in ["completed", "success"]:
                completed_ids.append((doc_id, True))
                print(f"  ✓ 完成: {doc['name']} ({int(elapsed)}秒)")
            elif doc_status in ["failed", "error"]:
                completed_ids.append((doc_id, False))
                print(f"  ✗ 失败: {doc['name']}")
        
        # 处理完成的任务
        for doc_id, is_success in completed_ids:
            doc = running_tasks[doc_id]['doc']
            del running_tasks[doc_id]
            if is_success:
                total_success += 1
                success_docs.append({
                    'name': doc['name'],
                    'path': doc['path'],
                    'type': doc['type'],
                })
            else:
                total_fail += 1
                failed_docs.append({
                    'name': doc['name'],
                    'path': doc['path'],
                    'type': doc['type'],
                    'error': '任务执行失败',
                })
        
        # 处理超时的任务
        for doc_id in timeout_ids:
            doc = running_tasks[doc_id]['doc']
            del running_tasks[doc_id]
            total_fail += 1
            failed_docs.append({
                'name': doc['name'],
                'path': doc['path'],
                'type': doc['type'],
                'error': f'超时({MAX_WAIT_TIME}秒)',
            })
        
        # 显示状态
        if running_tasks:
            remaining = len(pending_docs)
            running = len(running_tasks)
            print(f"\n  状态: 运行中 {running}, 待处理 {remaining}, 成功 {total_success}, 失败 {total_fail}")
            time.sleep(POLL_INTERVAL)
    
    end_time = datetime.now()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0]
    
    # 最终统计
    print(f"\n{'='*60}")
    print(f"全部完成！")
    print(f"{'='*60}")
    print(f"  开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  总耗时: {duration_str}")
    print(f"  处理文档数: {total_docs}")
    print(f"  成功: {total_success}")
    print(f"  失败: {total_fail}")
    if total_docs > 0:
        success_rate = total_success / total_docs * 100
        print(f"  成功率: {success_rate:.1f}%")
    
    # 显示失败列表
    if failed_docs:
        print(f"\n{'='*60}")
        print(f"失败文档列表 ({len(failed_docs)} 个):")
        print(f"{'='*60}")
        for doc in failed_docs[:50]:
            print(f"  {doc['path']}")
            print(f"    错误: {doc['error']}")
        if len(failed_docs) > 50:
            print(f"  ... 还有 {len(failed_docs) - 50} 个")
    
    print(f"{'='*60}")


def main():
    if RUN_MODE == 'polling':
        run_polling_mode()
    else:
        run_batch_mode()


if __name__ == "__main__":
    main()
