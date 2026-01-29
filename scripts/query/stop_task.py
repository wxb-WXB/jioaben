# -*- coding: utf-8 -*-
"""
停止文档处理任务

功能：
- 遍历所有知识库，找到正在进行中的任务并停止它们
- 支持按文件夹或文件类型筛选

使用方法：
python scripts/query/stop_task.py
"""
import sys
import os
import requests

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core import LingyanDataset
from src.config import API_KEY, WORKSPACE_IDS, BASE_URL

# ============== 配置区域 ==============
# 只停止指定文件夹下的任务（设为 None 则停止所有）
TARGET_FOLDER = None

# 只停止PDF类型的任务
ONLY_STOP_PDF = False
# ============== 配置结束 ==============


def stop_task(dataset_id: str, document_id: str, task_id: str) -> tuple:
    """停止文档处理任务"""
    url = f"{BASE_URL}/service/datasets/{dataset_id}/documents/{document_id}/stop/{task_id}"
    
    headers = {
        "accept": "application/json",
        "X-API-Key": API_KEY,
    }
    
    try:
        response = requests.post(url, headers=headers, data="")
        if response.status_code == 200:
            return 200, response.json()
        else:
            return response.status_code, response.text
    except requests.exceptions.RequestException as e:
        return 500, f"请求失败: {str(e)}"


def get_running_tasks(doc):
    """从文档的 tasks 字段获取正在运行的任务"""
    tasks = doc.get("tasks", [])
    if not tasks:
        return None
    
    running_statuses = ["indexing", "parsing", "waiting", "queuing"]
    for task in tasks:
        status = task.get("status", "")
        if status in running_statuses:
            return task.get("id"), status
    return None


def main():
    dataset = LingyanDataset(API_KEY)
    
    # 获取所有工作空间的知识库列表
    all_datasets = []
    for ws_id, ws_name in WORKSPACE_IDS:
        status, datasets_list = dataset.list_datasets(ws_id)
        print(f"[{ws_name}] 获取到 {len(datasets_list)} 个知识库")
        for ds in datasets_list:
            ds["_workspace_id"] = ws_id
            ds["_workspace_name"] = ws_name
        all_datasets.extend(datasets_list)
    
    # 如果指定了目标文件夹，只保留该文件夹下的知识库
    if TARGET_FOLDER:
        filtered_datasets = []
        for ds in all_datasets:
            ds_name = ds.get("name", "")
            if TARGET_FOLDER in ds_name:
                filtered_datasets.append(ds)
        print(f"\n筛选 [{TARGET_FOLDER}] 相关知识库: {len(filtered_datasets)} 个")
        all_datasets = filtered_datasets
    
    print(f"\n总共获取到 {len(all_datasets)} 个知识库")
    print(f"\n{'='*60}")
    if TARGET_FOLDER:
        print(f"开始查找并停止 [{TARGET_FOLDER}] 文件夹下正在进行中的任务...")
    else:
        print("开始查找并停止正在进行中的任务...")
    print(f"{'='*60}\n")
    
    # 统计
    stopped_count = 0
    failed_count = 0
    stopped_tasks = []
    failed_tasks = []
    
    for i, ds in enumerate(all_datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        ws_name = ds.get("_workspace_name", "未知")
        
        # 显示扫描进度
        print(f"\r扫描进度: [{i+1}/{len(all_datasets)}] {dataset_name[:30]:<30}", end="", flush=True)
        
        try:
            status, documents = dataset.list_documents(dataset_id)
            if status != 200:
                continue
            
            for doc in documents:
                doc_id = doc.get("id")
                doc_name = doc.get("name", "未知")
                
                # 只停止PDF类型
                if ONLY_STOP_PDF:
                    if not doc_name.lower().endswith('.pdf'):
                        continue
                
                # 检查是否有正在运行的任务
                running_task = get_running_tasks(doc)
                if running_task:
                    task_id, task_status = running_task
                    print()
                    print(f"[{ws_name}] [{dataset_name}] 发现进行中任务:")
                    print(f"  文档: {doc_name}")
                    print(f"  状态: {task_status}")
                    print(f"  任务ID: {task_id}")
                    
                    # 停止任务
                    stop_status, stop_result = stop_task(dataset_id, doc_id, task_id)
                    
                    if stop_status == 200:
                        print(f"  ✓ 停止成功!")
                        stopped_count += 1
                        stopped_tasks.append({
                            "workspace": ws_name,
                            "dataset": dataset_name,
                            "document": doc_name,
                            "task_id": task_id,
                        })
                    else:
                        print(f"  ✗ 停止失败: {stop_result}")
                        failed_count += 1
                        failed_tasks.append({
                            "workspace": ws_name,
                            "dataset": dataset_name,
                            "document": doc_name,
                            "task_id": task_id,
                            "error": stop_result,
                        })
                    print()
                    
        except Exception as e:
            print(f"[{ws_name}] [{dataset_name}] 处理出错: {e}")
    
    # 输出统计结果
    print(f"\n{'='*60}")
    print("停止任务完成")
    print(f"{'='*60}")
    print(f"成功停止: {stopped_count} 个任务")
    print(f"停止失败: {failed_count} 个任务")
    
    if stopped_tasks:
        print(f"\n已停止的任务列表:")
        for t in stopped_tasks:
            print(f"  [{t['workspace']}] [{t['dataset']}] {t['document']}")
    
    if failed_tasks:
        print(f"\n停止失败的任务列表:")
        for t in failed_tasks:
            print(f"  [{t['workspace']}] [{t['dataset']}] {t['document']}")
            print(f"    错误: {t['error']}")


if __name__ == "__main__":
    main()
