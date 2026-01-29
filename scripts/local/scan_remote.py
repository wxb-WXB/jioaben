# -*- coding: utf-8 -*-
"""
远程知识库文档统计脚本

功能：
- 统计所有知识库的向量化状态
- 分类显示：成功、进行中、失败、已取消、无任务
- 生成详细统计报告并保存到日志文件

使用方法：
python scripts/local/scan_remote.py
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core import LingyanDataset
from src.core.models import FolderMap
from src.config import API_KEY, WORKSPACES, LOGS_DIR

# 构建 WORKSPACE_IDS 格式
WORKSPACE_IDS = [(ws["id"], ws["name"]) for ws in WORKSPACES]

# 确保logs文件夹存在（LOGS_DIR已经是完整路径）
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# 记录开始时间
start_time = datetime.now()
print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

dataset = LingyanDataset(API_KEY)

# 获取所有工作空间的知识库列表
all_datasets = []
for ws_id, ws_name in WORKSPACE_IDS:
    status, datasets_list = dataset.list_datasets(ws_id)
    if status != 200:
        print(f"[{ws_name}] 获取知识库列表失败: {datasets_list}")
        continue
    print(f"[{ws_name}] 获取到 {len(datasets_list)} 个知识库")
    for ds in datasets_list:
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


def get_doc_size(doc):
    """获取文档大小（字节）"""
    # 优先使用 file_size，其次 size
    size = doc.get("file_size")
    if size is not None and size > 0:
        return size
    size = doc.get("size")
    if size is not None and size > 0:
        return size
    return 0


def format_size(size_bytes):
    """格式化文件大小为人类可读格式"""
    if size_bytes >= 1024 ** 4:  # TB
        return f"{size_bytes / (1024 ** 4):.2f} TB"
    elif size_bytes >= 1024 ** 3:  # GB
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:  # MB
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:  # KB
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"


def get_doc_status(doc):
    """从文档的 tasks 字段获取向量化任务状态"""
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task", None
    
    normal_tasks = [t for t in tasks if t.get("type") == "normal"]
    
    if normal_tasks:
        latest_normal = normal_tasks[-1]
        return latest_normal.get("status", "unknown"), latest_normal.get("type")
    else:
        latest_task = tasks[-1]
        return latest_task.get("status", "unknown"), latest_task.get("type")


# 统计变量
success_docs = []
indexing_docs = []
error_docs = []
cancelled_docs = []
no_task_docs = []
total_docs = 0
total_size = 0  # 总文件大小（字节）
status_count = {}

# 按状态统计大小
size_by_status = {
    "success": 0,
    "indexing": 0,
    "error": 0,
    "cancelled": 0,
    "no_task": 0
}

# 按工作空间统计大小
size_by_workspace = {}

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
            doc_size = get_doc_size(doc)
            total_size += doc_size
            
            # 按工作空间统计大小
            if ws_name not in size_by_workspace:
                size_by_workspace[ws_name] = 0
            size_by_workspace[ws_name] += doc_size
            
            doc_status, task_type = get_doc_status(doc)
            
            status_count[doc_status] = status_count.get(doc_status, 0) + 1
            
            if doc_status in ["completed", "success"]:
                ds_success += 1
                size_by_status["success"] += doc_size
                success_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name, "size": doc_size})
            elif doc_status in ["indexing", "parsing", "waiting", "queuing"]:
                ds_indexing += 1
                size_by_status["indexing"] += doc_size
                indexing_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "status": doc_status, "folder_path": folder_path, "workspace": ws_name, "size": doc_size})
            elif doc_status in ["error", "failed"]:
                ds_error += 1
                size_by_status["error"] += doc_size
                error_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name, "size": doc_size})
            elif doc_status == "cancelled":
                size_by_status["cancelled"] += doc_size
                cancelled_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name, "size": doc_size})
            elif doc_status == "no_task":
                size_by_status["no_task"] += doc_size
                no_task_docs.append({"dataset_name": dataset_name, "doc_name": doc_name, "folder_path": folder_path, "workspace": ws_name, "size": doc_size})
        
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
print(f"总文件大小: {format_size(total_size)}")
print(f"")
print(f"向量解析成功的文档数: {len(success_docs)} ({format_size(size_by_status['success'])})")
print(f"正在向量化的文档数: {len(indexing_docs)} ({format_size(size_by_status['indexing'])})")
print(f"向量化失败的文档数: {len(error_docs)} ({format_size(size_by_status['error'])})")
print(f"已取消的文档数: {len(cancelled_docs)} ({format_size(size_by_status['cancelled'])})")
print(f"没有任务的文档数: {len(no_task_docs)} ({format_size(size_by_status['no_task'])})")

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
    
    print(f"\n正在向量化的文档详情:")
    for doc in indexing_docs[:50]:
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

# 最终汇总统计
ws1_name = WORKSPACE_IDS[0][1] if len(WORKSPACE_IDS) > 0 else "工作空间1"
ws2_name = WORKSPACE_IDS[1][1] if len(WORKSPACE_IDS) > 1 else "工作空间2"

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

ws1_total = ws1_success + ws1_indexing + ws1_error + ws1_cancelled + ws1_no_task
ws2_total = ws2_success + ws2_indexing + ws2_error + ws2_cancelled + ws2_no_task

# 计算各工作空间大小
ws1_size = size_by_workspace.get(ws1_name, 0)
ws2_size = size_by_workspace.get(ws2_name, 0)

print(f"\n{'='*80}")
print(f"最终汇总统计")
print(f"{'='*80}")
print(f"")
print(f"  工作空间            总数      成功    进行中      失败    已取消    无任务       大小")
print(f"  {'-'*90}")
print(f"  {ws1_name}      {ws1_total:>8}  {ws1_success:>8}  {ws1_indexing:>8}  {ws1_error:>8}  {ws1_cancelled:>8}  {ws1_no_task:>8}  {format_size(ws1_size):>10}")
if len(WORKSPACE_IDS) > 1:
    print(f"  {ws2_name}  {ws2_total:>8}  {ws2_success:>8}  {ws2_indexing:>8}  {ws2_error:>8}  {ws2_cancelled:>8}  {ws2_no_task:>8}  {format_size(ws2_size):>10}")
print(f"  {'-'*90}")
print(f"  【总计】          {total_docs:>8}  {total_success:>8}  {total_indexing:>8}  {total_error:>8}  {total_cancelled:>8}  {total_no_task:>8}  {format_size(total_size):>10}")
print(f"")
print(f"  📊 文件大小统计:")
print(f"     总大小: {format_size(total_size)}")
print(f"     成功: {format_size(size_by_status['success'])}")
print(f"     进行中: {format_size(size_by_status['indexing'])}")
print(f"     失败: {format_size(size_by_status['error'])}")
print(f"     已取消: {format_size(size_by_status['cancelled'])}")
print(f"     无任务: {format_size(size_by_status['no_task'])}")
print(f"")

# 计算耗时
end_time = datetime.now()
duration = end_time - start_time
duration_str = str(duration).split('.')[0]

print(f"{'='*60}")
print(f"统计时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')}")
print(f"总耗时: {duration_str}")
print(f"{'='*60}")

# 保存统计结果到日志文件
log_filename = os.path.join(LOGS_DIR, f"vector_stats_{start_time.strftime('%Y-%m-%d_%H%M%S')}.log")

log_lines = []
log_lines.append("=" * 80)
log_lines.append(f"向量化统计报告")
log_lines.append(f"统计时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')}")
log_lines.append(f"总耗时: {duration_str}")
log_lines.append("=" * 80)
log_lines.append("")
log_lines.append(f"总知识库数: {len(datasets)}")
log_lines.append(f"总文档数: {total_docs}")
log_lines.append(f"总文件大小: {format_size(total_size)}")
log_lines.append("")
log_lines.append("【汇总统计】")
log_lines.append(f"  工作空间            总数      成功    进行中      失败    已取消    无任务       大小")
log_lines.append(f"  {'-'*90}")
log_lines.append(f"  {ws1_name}      {ws1_total:>8}  {ws1_success:>8}  {ws1_indexing:>8}  {ws1_error:>8}  {ws1_cancelled:>8}  {ws1_no_task:>8}  {format_size(ws1_size):>10}")
if len(WORKSPACE_IDS) > 1:
    log_lines.append(f"  {ws2_name}  {ws2_total:>8}  {ws2_success:>8}  {ws2_indexing:>8}  {ws2_error:>8}  {ws2_cancelled:>8}  {ws2_no_task:>8}  {format_size(ws2_size):>10}")
log_lines.append(f"  {'-'*90}")
log_lines.append(f"  【总计】          {total_docs:>8}  {total_success:>8}  {total_indexing:>8}  {total_error:>8}  {total_cancelled:>8}  {total_no_task:>8}  {format_size(total_size):>10}")
log_lines.append("")
log_lines.append("【文件大小统计】")
log_lines.append(f"  总大小: {format_size(total_size)}")
log_lines.append(f"  成功: {format_size(size_by_status['success'])}")
log_lines.append(f"  进行中: {format_size(size_by_status['indexing'])}")
log_lines.append(f"  失败: {format_size(size_by_status['error'])}")
log_lines.append(f"  已取消: {format_size(size_by_status['cancelled'])}")
log_lines.append(f"  无任务: {format_size(size_by_status['no_task'])}")
log_lines.append("")

log_lines.append("【各状态文档数量】")
for s, count in sorted(status_count.items(), key=lambda x: -x[1]):
    log_lines.append(f"  {s}: {count}")
log_lines.append("")

if indexing_docs:
    log_lines.append(f"【正在向量化的文档】(共 {len(indexing_docs)} 个)")
    for doc in indexing_docs:
        log_lines.append(f"  [{doc['workspace']}] [{doc['folder_path']}] [{doc['dataset_name']}] {doc['doc_name']} ({doc['status']})")
    log_lines.append("")

if error_docs:
    log_lines.append(f"【向量化失败的文档】(共 {len(error_docs)} 个)")
    for doc in error_docs:
        log_lines.append(f"  [{doc['workspace']}] [{doc['folder_path']}] [{doc['dataset_name']}] {doc['doc_name']}")
    log_lines.append("")

with open(log_filename, 'w', encoding='utf-8') as f:
    f.write('\n'.join(log_lines))

print(f"\n📄 统计报告已保存到: {log_filename}")
