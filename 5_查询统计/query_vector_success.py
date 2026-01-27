"""
查询向量解析成功的文档

判断依据：
- 文档的 tasks 字段包含任务列表，每个任务有 status 字段
- 取最新的任务（最后一个）的状态作为文档的向量化状态
- completed: 向量化成功
- indexing: 正在向量化
- parsing: 正在解析
- error: 向量化失败
- waiting: 等待处理
- cancelled: 已取消
"""
import json
import sys
import os

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset
from models import FolderMap

api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 两个 workspace ID
workspace_ids = [
    ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库"),
    ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "第二个知识库"),
]

dataset = LingyanDataset(api_key)

# 获取所有工作空间的知识库列表
all_datasets = []
for ws_id, ws_name in workspace_ids:
    status, datasets_list = dataset.list_datasets(ws_id)
    if status != 200:
        print(f"[{ws_name}] 获取知识库列表失败: {datasets_list}")
        continue
    print(f"[{ws_name}] 获取到 {len(datasets_list)} 个知识库")
    # 给每个 dataset 添加 workspace 信息
    for ds in datasets_list:
        # 跳过非字典类型的数据
        if not isinstance(ds, dict):
            print(f"[{ws_name}] 跳过非字典数据: {type(ds)} - {ds}")
            continue
        ds["_workspace_id"] = ws_id
        ds["_workspace_name"] = ws_name
        all_datasets.append(ds)

print(f"\n总共获取到 {len(all_datasets)} 个知识库")
datasets = all_datasets

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
    优先查找 type=normal 的任务（向量化任务），取最新的一个
    状态值：success/completed=成功, failed/error=失败, indexing/parsing/waiting=进行中
    """
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task", None  # 没有任务
    
    # 查找所有 type=normal 的任务（向量化任务），取最新的一个（最后一个）
    normal_tasks = [t for t in tasks if t.get("type") == "normal"]
    
    if normal_tasks:
        # 取最后一个 normal 任务（最新的）
        latest_normal = normal_tasks[-1]
        return latest_normal.get("status", "unknown"), latest_normal.get("type")
    else:
        # 如果没有 normal 任务，取最后一个任务
        latest_task = tasks[-1]
        return latest_task.get("status", "unknown"), latest_task.get("type")


# 统计向量解析成功的文档
success_docs = []
indexing_docs = []  # 正在向量化的文档
error_docs = []     # 向量化失败的文档
cancelled_docs = [] # 已取消的文档
no_task_docs = []   # 没有任务的文档
total_docs = 0
status_count = {}  # 统计各状态的数量

# 按知识库统计
dataset_success_count = {}
dataset_indexing_count = {}
dataset_error_count = {}

for i, ds in enumerate(datasets):
    dataset_id = ds.get("id")
    dataset_name = ds.get("name")
    folder_id = ds.get("folder_id")
    folder_path = get_folder_path(folder_id)
    ws_name = ds.get("_workspace_name", "未知")
    
    print(f"[{i+1}/{len(datasets)}] [{ws_name}] 正在处理知识库: {dataset_name}", end="")
    
    try:
        status, documents = dataset.list_documents(dataset_id)
        if status != 200:
            print(f" - 获取文档失败: {documents}")
            continue
        
        ds_success = 0
        ds_indexing = 0
        ds_error = 0
        
        for doc in documents:
            total_docs += 1
            doc_name = doc.get("name", "未知")
            
            # 从 tasks 字段获取状态
            doc_status, task_type = get_doc_status(doc)
            
            # 统计各状态数量
            status_count[doc_status] = status_count.get(doc_status, 0) + 1
            
            
            # 检查向量解析状态
            # success 和 completed 都表示成功
            if doc_status in ["completed", "success"]:
                ds_success += 1
                success_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name})
            elif doc_status in ["indexing", "parsing", "waiting", "queuing"]:
                ds_indexing += 1
                indexing_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "status": doc_status, "folder_path": folder_path, "workspace": ws_name})
            elif doc_status in ["error", "failed"]:
                ds_error += 1
                error_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name})
            elif doc_status == "cancelled":
                cancelled_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name})
            elif doc_status == "no_task":
                no_task_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name})
        
        result_parts = []
        if ds_success > 0:
            dataset_success_count[dataset_name] = {"count": ds_success, "folder_path": folder_path, "workspace": ws_name}
            result_parts.append(f"✓成功:{ds_success}")
        if ds_indexing > 0:
            dataset_indexing_count[dataset_name] = {"count": ds_indexing, "folder_path": folder_path, "workspace": ws_name}
            result_parts.append(f"⏳进行中:{ds_indexing}")
        if ds_error > 0:
            dataset_error_count[dataset_name] = {"count": ds_error, "folder_path": folder_path, "workspace": ws_name}
            result_parts.append(f"✗失败:{ds_error}")
        
        if result_parts:
            print(f" - {', '.join(result_parts)}")
        else:
            print(f" - 文档数:{len(documents)}")
            
    except Exception as e:
        print(f" - 处理出错: {e}")

print(f"\n{'='*60}")
print(f"统计结果")
print(f"{'='*60}")
print(f"总知识库数: {len(datasets)}")
print(f"总文档数: {total_docs}")
print(f"向量解析成功的文档数: {len(success_docs)}")
print(f"正在向量化的文档数: {len(indexing_docs)}")
print(f"向量化失败的文档数: {len(error_docs)}")
print(f"已取消的文档数: {len(cancelled_docs)}")
print(f"没有任务的文档数: {len(no_task_docs)}")

print(f"\n各状态文档数量统计:")
for s, count in sorted(status_count.items(), key=lambda x: -x[1]):
    print(f"  {s}: {count}")


if dataset_success_count:
    print(f"\n{'='*60}")
    print(f"向量化成功的知识库列表 (共 {len(dataset_success_count)} 个):")
    print(f"{'='*60}")
    for name, info in sorted(dataset_success_count.items(), key=lambda x: -x[1]["count"]):
        print(f"  [{info['workspace']}] 路径: {info['folder_path']}")
        print(f"  知识库: {name}")
        print(f"  成功文档数: {info['count']} 个")
        print()

if dataset_indexing_count:
    print(f"\n{'='*60}")
    print(f"正在向量化的知识库列表 (共 {len(dataset_indexing_count)} 个):")
    print(f"{'='*60}")
    for name, info in sorted(dataset_indexing_count.items(), key=lambda x: -x[1]["count"]):
        print(f"  [{info['workspace']}] 路径: {info['folder_path']}")
        print(f"  知识库: {name}")
        print(f"  进行中文档数: {info['count']} 个")
        print()
    
    # 列出正在向量化的文档详情
    print(f"\n正在向量化的文档详情:")
    for doc in indexing_docs[:50]:  # 最多显示50个
        print(f"  [{doc['workspace']}] [{doc['folder_path']}] [{doc['dataset_name']}] {doc['doc_name']} ({doc['status']})")
    if len(indexing_docs) > 50:
        print(f"  ... 还有 {len(indexing_docs) - 50} 个文档")

if dataset_error_count:
    print(f"\n{'='*60}")
    print(f"向量化失败的知识库列表 (共 {len(dataset_error_count)} 个):")
    print(f"{'='*60}")
    for name, info in sorted(dataset_error_count.items(), key=lambda x: -x[1]["count"]):
        print(f"  [{info['workspace']}] 路径: {info['folder_path']}")
        print(f"  知识库: {name}")
        print(f"  失败文档数: {info['count']} 个")
        print()

# ============================================================
# 最终汇总统计 (放在最后方便查看)
# ============================================================
# 使用与 workspace_ids 中定义一致的名称
ws1_name = "环北知识库"
ws2_name = "第二个知识库"

ws1_success = sum(1 for doc in success_docs if doc["workspace"] == ws1_name)
ws2_success = sum(1 for doc in success_docs if doc["workspace"] == ws2_name)
ws1_indexing = sum(1 for doc in indexing_docs if doc["workspace"] == ws1_name)
ws2_indexing = sum(1 for doc in indexing_docs if doc["workspace"] == ws2_name)
ws1_error = sum(1 for doc in error_docs if doc["workspace"] == ws1_name)
ws2_error = sum(1 for doc in error_docs if doc["workspace"] == ws2_name)
ws1_cancelled = sum(1 for doc in cancelled_docs if doc["workspace"] == ws1_name)
ws2_cancelled = sum(1 for doc in cancelled_docs if doc["workspace"] == ws2_name)
ws1_no_task = sum(1 for doc in no_task_docs if doc["workspace"] == ws1_name)
ws2_no_task = sum(1 for doc in no_task_docs if doc["workspace"] == ws2_name)

total_success = ws1_success + ws2_success
total_indexing = ws1_indexing + ws2_indexing
total_error = ws1_error + ws2_error
total_cancelled = ws1_cancelled + ws2_cancelled
total_no_task = ws1_no_task + ws2_no_task

# 计算每个工作空间的总文档数
ws1_total = ws1_success + ws1_indexing + ws1_error + ws1_cancelled + ws1_no_task
ws2_total = ws2_success + ws2_indexing + ws2_error + ws2_cancelled + ws2_no_task

print(f"\n{'='*60}")
print(f"最终汇总统计")
print(f"{'='*60}")
print(f"")
print(f"  工作空间            总数      成功    进行中      失败    已取消    无任务")
print(f"  {'-'*75}")
print(f"  {ws1_name}      {ws1_total:>8}  {ws1_success:>8}  {ws1_indexing:>8}  {ws1_error:>8}  {ws1_cancelled:>8}  {ws1_no_task:>8}")
print(f"  {ws2_name}  {ws2_total:>8}  {ws2_success:>8}  {ws2_indexing:>8}  {ws2_error:>8}  {ws2_cancelled:>8}  {ws2_no_task:>8}")
print(f"  {'-'*75}")
print(f"  【总计】          {total_docs:>8}  {total_success:>8}  {total_indexing:>8}  {total_error:>8}  {total_cancelled:>8}  {total_no_task:>8}")
print(f"")
