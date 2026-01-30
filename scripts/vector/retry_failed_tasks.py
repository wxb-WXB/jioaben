# -*- coding: utf-8 -*-
"""
失败文档重试脚本 - 定时启动向量化任务

功能：
- 遍历知识库，检测失败/无任务的文档
- 优先处理文本文件（txt, doc, docx, md等）
- 使用普通切割模式（关闭语义切割）
- 扫描到失败文档后立即启动处理
- 每次启动指定数量的任务后暂停等待，避免服务器压力过大

使用方法：
python scripts/vector/retry_failed_tasks.py
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
# 配置参数
# ============================================================

# workspace ID 配置 (workspace_id, workspace_name)
workspace_ids = [(ws["id"], ws["name"]) for ws in WORKSPACES]
# 或者手动指定：
# workspace_ids = [
#     ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库"),
#     ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "第二个知识库"),
# ]

# 只处理指定目录下的知识库（为空则处理所有目录）
TARGET_FOLDER_PATH = None  # 设置为 None 或 "" 则处理所有目录

# 每批处理的文档数量
BATCH_SIZE = 20

# 每批处理完后等待的时间（秒）
WAIT_TIME = 90

# API返回的文本文件类型（type字段）
TEXT_FILE_TYPES = {'doc', 'docx', 'txt', 'md', 'wps'}

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
    """
    从文档的 tasks 字段获取向量化任务状态
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


def retry_single_doc(doc, batch_num, batch_pos, workspace_id):
    """重试单个文档"""
    doc_name = doc['document_name']
    doc_type = doc.get('doc_type', '')
    folder_path = doc['folder_path']
    
    # 构建完整文件路径
    if folder_path and folder_path != "根目录":
        full_path = f"{folder_path}/{doc['dataset_name']}/{doc_name}"
    else:
        full_path = f"{doc['dataset_name']}/{doc_name}"
    
    print(f"\n[批次{batch_num}][{batch_pos}/{BATCH_SIZE}] 重试文档: {doc_name} [type={doc_type}]")
    print(f"  文件路径: {full_path}")
    print(f"  知识库: {doc['dataset_name']}")
    print(f"  文档ID: {doc['document_id']}")
    
    try:
        # 使用普通切割模式（common），关闭语义切割（semantic）
        # parse_enhance=False 关闭增强解析
        status, result = dataset_api.create_task(
            dataset_id=doc['dataset_id'],
            document_id=doc['document_id'],
            split_mode="common",  # 普通切割，不使用语义切割
            task_type="normal",
            image_task=False,
            parse_enhance=False,  # 关闭增强解析
            workspace_id=workspace_id
        )
        
        if status == 200:
            print(f"  ✓ 任务创建成功")
            return True
        else:
            print(f"  ✗ 任务创建失败: {result}")
            return False
            
    except Exception as e:
        print(f"  ✗ 出错: {e}")
        return False


def scan_and_retry(workspace_id, workspace_name):
    """
    扫描知识库，发现失败文档后立即处理
    优先处理文本文件，每处理完指定数量文档后暂停等待
    """
    print(f"\n正在扫描 [{workspace_name}] 的知识库...")
    status, datasets = dataset_api.list_datasets(workspace_id)
    
    if status != 200:
        print(f"获取知识库列表失败: {datasets}")
        return 0, 0
    
    print(f"找到 {len(datasets)} 个知识库")
    
    total_success = 0
    total_fail = 0
    batch_count = 0  # 当前批次已处理数量
    batch_num = 1
    
    for i, ds in enumerate(datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        # 如果设置了目录过滤，则跳过不匹配的目录
        if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
            continue
        
        print(f"\n[{i+1}/{len(datasets)}] 检查知识库: {dataset_name}")
        print(f"  目录路径: {folder_path}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id, workspace_id)
            if status != 200:
                print(f"  获取文档失败")
                continue
            
            # 收集该知识库中的失败文档，按文本优先排序
            failed_in_ds = []
            for doc in documents:
                doc_status, _ = get_doc_status(doc)
                
                # 检测失败、错误、取消、或者没有任务的文档
                if doc_status in ["error", "failed", "cancelled", "no_task"]:
                    doc_name = doc.get("name", "")
                    doc_type = doc.get("type", "")  # API返回的文件类型
                    
                    # 只处理文本文件，使用API返回的type字段判断
                    if doc_type not in TEXT_FILE_TYPES:
                        continue
                    
                    failed_in_ds.append({
                        "dataset_id": dataset_id,
                        "dataset_name": dataset_name,
                        "document_id": doc.get("id"),
                        "document_name": doc_name,
                        "doc_type": doc_type,
                        "workspace": workspace_name,
                        "folder_path": folder_path,
                    })
            
            if len(failed_in_ds) == 0:
                print(f"  无需处理的文档，继续扫描...")
                continue
            
            # 按文件名排序
            failed_in_ds.sort(key=lambda x: x['document_name'])
            
            print(f"  发现 {len(failed_in_ds)} 个待处理文本文件（失败/取消/无任务），立即处理...")
            
            # 立即处理这些失败文档
            for doc in failed_in_ds:
                batch_count += 1
                
                # 处理文档
                if retry_single_doc(doc, batch_num, batch_count, workspace_id):
                    total_success += 1
                else:
                    total_fail += 1
                
                # 如果当前批次满了，暂停等待
                if batch_count >= BATCH_SIZE:
                    print(f"\n{'='*60}")
                    print(f"第 {batch_num} 批完成（成功: {total_success}, 失败: {total_fail}）")
                    print(f"等待 {WAIT_TIME} 秒后继续...")
                    print(f"{'='*60}")
                    time.sleep(WAIT_TIME)
                    
                    batch_num += 1
                    batch_count = 0
            
            print(f"\n  知识库 [{dataset_name}] 处理完成")
                
        except Exception as e:
            print(f"  出错: {e}")
    
    return total_success, total_fail


def main():
    from datetime import datetime
    
    start_time = datetime.now()
    
    print("="*60)
    print(f"失败/无任务文档重试工具 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("  - 只处理文本文件（txt, doc, docx, md等）")
    print("  - 扫描到失败文档后立即处理")
    print("  - 使用普通切割模式（关闭语义切割）")
    print(f"  - 每批处理 {BATCH_SIZE} 个文档，每批间隔 {WAIT_TIME} 秒")
    if TARGET_FOLDER_PATH:
        print(f"  - 目标目录过滤: {TARGET_FOLDER_PATH}")
    print("="*60)
    
    total_success = 0
    total_fail = 0
    
    for ws_id, ws_name in workspace_ids:
        success, fail = scan_and_retry(ws_id, ws_name)
        total_success += success
        total_fail += fail
    
    end_time = datetime.now()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0]
    
    print(f"\n{'='*60}")
    print(f"全部完成！")
    print(f"{'='*60}")
    print(f"  开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  总耗时: {duration_str}")
    print(f"  处理总数: {total_success + total_fail}")
    print(f"  成功: {total_success}")
    print(f"  失败: {total_fail}")
    if total_success + total_fail > 0:
        success_rate = total_success / (total_success + total_fail) * 100
        print(f"  成功率: {success_rate:.1f}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
