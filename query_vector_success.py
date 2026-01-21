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
from LingyanAi import LingyanDataset
from models import FolderMap

api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"

dataset = LingyanDataset(api_key)

# 获取知识库列表
status, datasets = dataset.list_datasets(workspace_id)
print(f"获取到 {len(datasets)} 个知识库")

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
    优先查找 type=normal 的任务（向量化任务）
    状态值：success/completed=成功, failed/error=失败, indexing/parsing/waiting=进行中
    """
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task", None  # 没有任务
    
    # 优先查找 type=normal 的任务（这是向量化任务）
    normal_task = None
    for task in tasks:
        if task.get("type") == "normal":
            normal_task = task
            break
    
    # 如果没有 normal 任务，取最新的任务
    if normal_task:
        return normal_task.get("status", "unknown"), normal_task.get("type")
    else:
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
    
    print(f"[{i+1}/{len(datasets)}] 正在处理知识库: {dataset_name}", end="")
    
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
                success_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path})
            elif doc_status in ["indexing", "parsing", "waiting", "queuing"]:
                ds_indexing += 1
                indexing_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "status": doc_status, "folder_path": folder_path})
            elif doc_status in ["error", "failed"]:
                ds_error += 1
                error_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path})
            elif doc_status == "cancelled":
                cancelled_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path})
            elif doc_status == "no_task":
                no_task_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path})
        
        result_parts = []
        if ds_success > 0:
            dataset_success_count[dataset_name] = {"count": ds_success, "folder_path": folder_path}
            result_parts.append(f"✓成功:{ds_success}")
        if ds_indexing > 0:
            dataset_indexing_count[dataset_name] = {"count": ds_indexing, "folder_path": folder_path}
            result_parts.append(f"⏳进行中:{ds_indexing}")
        if ds_error > 0:
            dataset_error_count[dataset_name] = {"count": ds_error, "folder_path": folder_path}
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
        print(f"  路径: {info['folder_path']}")
        print(f"  知识库: {name}")
        print(f"  成功文档数: {info['count']} 个")
        print()

if dataset_indexing_count:
    print(f"\n{'='*60}")
    print(f"正在向量化的知识库列表 (共 {len(dataset_indexing_count)} 个):")
    print(f"{'='*60}")
    for name, info in sorted(dataset_indexing_count.items(), key=lambda x: -x[1]["count"]):
        print(f"  路径: {info['folder_path']}")
        print(f"  知识库: {name}")
        print(f"  进行中文档数: {info['count']} 个")
        print()
    
    # 列出正在向量化的文档详情
    print(f"\n正在向量化的文档详情:")
    for doc in indexing_docs[:50]:  # 最多显示50个
        print(f"  [{doc['folder_path']}] [{doc['dataset_name']}] {doc['doc_name']} ({doc['status']})")
    if len(indexing_docs) > 50:
        print(f"  ... 还有 {len(indexing_docs) - 50} 个文档")

if dataset_error_count:
    print(f"\n{'='*60}")
    print(f"向量化失败的知识库列表 (共 {len(dataset_error_count)} 个):")
    print(f"{'='*60}")
    for name, info in sorted(dataset_error_count.items(), key=lambda x: -x[1]["count"]):
        print(f"  路径: {info['folder_path']}")
        print(f"  知识库: {name}")
        print(f"  失败文档数: {info['count']} 个")
        print()
