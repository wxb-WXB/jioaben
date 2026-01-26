"""
停止文档处理任务

遍历所有知识库，找到正在进行中的任务并停止它们
"""
import sys
import os
import requests

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset

# API 配置
API_BASE = "http://10.4.49.66:18080/api/v1/service"
API_KEY = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 两个 workspace ID
workspace_ids = [
    ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库"),
    ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "第二个知识库"),
]


def stop_task(dataset_id: str, document_id: str, task_id: str) -> tuple[int, dict | str]:
    """
    停止文档处理任务
    
    Args:
        dataset_id: 知识库ID
        document_id: 文档ID
        task_id: 任务ID
        
    Returns:
        tuple[int, dict | str]: (状态码, 响应数据或错误信息)
    """
    url = f"{API_BASE}/datasets/{dataset_id}/documents/{document_id}/stop/{task_id}"
    
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
    """
    从文档的 tasks 字段获取正在运行的任务
    返回: (task_id, status) 或 None
    """
    tasks = doc.get("tasks", [])
    if not tasks:
        return None
    
    # 查找正在进行中的任务
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
    for ws_id, ws_name in workspace_ids:
        status, datasets_list = dataset.list_datasets(ws_id)
        print(f"[{ws_name}] 获取到 {len(datasets_list)} 个知识库")
        for ds in datasets_list:
            ds["_workspace_id"] = ws_id
            ds["_workspace_name"] = ws_name
        all_datasets.extend(datasets_list)
    
    print(f"\n总共获取到 {len(all_datasets)} 个知识库")
    print(f"\n{'='*60}")
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
        
        try:
            status, documents = dataset.list_documents(dataset_id)
            if status != 200:
                continue
            
            for doc in documents:
                doc_id = doc.get("id")
                doc_name = doc.get("name", "未知")
                
                # 检查是否有正在运行的任务
                running_task = get_running_tasks(doc)
                if running_task:
                    task_id, task_status = running_task
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
