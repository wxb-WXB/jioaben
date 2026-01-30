# -*- coding: utf-8 -*-
"""
失败文档重试脚本 - 批次模式

功能：
- 遍历知识库，检测失败/无任务的文档
- 边扫边处理：扫描到失败文档后立即启动
- 批次模式：每次启动N个任务，等待一段时间，继续下一批

使用方法：
python scripts/generate/retry_failed_tasks.py
"""
import sys
import time
import os

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
from src.config import API_KEY, WORKSPACES

# ============================================================
# 配置参数 - 修改这里来控制脚本行为
# ============================================================

# workspace ID 配置
workspace_ids = [(ws["id"], ws["name"]) for ws in WORKSPACES]

# 只处理指定目录下的知识库
TARGET_FOLDER_PATH = None

# ------------------------------
# 批次控制
# ------------------------------
BATCH_SIZE = 50          # 每批启动的任务数
BATCH_WAIT = 30          # 每批完成后等待时间（秒）
REQUEST_INTERVAL = 0.3   # 每次启动任务之间的间隔（秒）

# ------------------------------
# 网络重试控制
# ------------------------------
MAX_RETRIES = 3          # 网络错误最大重试次数
RETRY_DELAY = 5          # 重试间隔（秒）

# ------------------------------
# 文件类型过滤
# ------------------------------
INCLUDE_FILE_TYPES = {'doc', 'docx', 'txt', 'md', 'wps'}
# INCLUDE_FILE_TYPES = {'pdf'}
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
PARSE_ENHANCE = False    # 是否开启精准解析
IMAGE_TASK = False       # 是否处理图片任务

# ============================================================
# 以下为脚本逻辑
# ============================================================

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


def print_config():
    """打印当前配置"""
    print("="*60)
    print("当前配置:")
    print("="*60)
    print(f"  批次大小: {BATCH_SIZE}")
    print(f"  批次等待: {BATCH_WAIT} 秒")
    print(f"  请求间隔: {REQUEST_INTERVAL} 秒")
    print(f"  切割模式: {SPLIT_MODE}")
    print(f"  精准解析: {'开启' if PARSE_ENHANCE else '关闭'}")
    
    if INCLUDE_FILE_TYPES:
        print(f"  处理文件类型: {', '.join(sorted(INCLUDE_FILE_TYPES))}")
    else:
        print(f"  处理文件类型: 全部")
    
    print(f"  重试状态: {', '.join(RETRY_STATUS)}")
    print("="*60)


def main():
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
    batch_count = 0  # 当前批次已启动数量
    
    # 记录成功和失败的文档
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


if __name__ == "__main__":
    main()
