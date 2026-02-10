# -*- coding: utf-8 -*-
"""
远程知识库文档统计脚本

功能：
- 统计知识库的向量化状态
- 分类显示：成功、进行中、待处理、已取消、无任务
- 生成Excel格式的统计报告（CSV格式）
- 自动上传统计报告到远程服务器

使用方法：
python scripts/local/scan_remote.py
"""
import sys
import os
import csv
from datetime import datetime

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core import LingyanDataset
from src.core.models import FolderMap
from src.config import API_KEY, WORKSPACES, LOGS_DIR, REMOTE_SERVER

# 只统计第一个工作空间
TARGET_WORKSPACE = WORKSPACES[0]
WORKSPACE_ID = TARGET_WORKSPACE["id"]
WORKSPACE_NAME = TARGET_WORKSPACE["name"]

# 确保logs文件夹存在
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# 记录开始时间
start_time = datetime.now()
date_str = start_time.strftime('%Y-%m-%d')
print("=" * 70)
print(f"知识库向量化状态统计 - {date_str}")
print("=" * 70)
print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"统计工作空间: {WORKSPACE_NAME}")
print("=" * 70)

dataset = LingyanDataset(API_KEY)

# 获取文件夹树结构
print("正在获取文件夹树结构...")
status, folder_tree = dataset.get_folder_tree(WORKSPACE_ID)
if status != 200:
    print(f"获取文件夹树失败: {folder_tree}")
    folder_tree = {}
else:
    print(f"文件夹树获取成功")

# 构建 folder_id 到一级目录名称的映射
folder_id_to_first_level = {}
all_first_level_folders = {}  # 记录所有一级目录

def build_folder_mapping(nodes, first_level_name=None, level=0):
    """递归构建 folder_id 到一级目录名称的映射"""
    if not nodes:
        return
    
    for node in nodes:
        folder_id = node.get("id")
        folder_name = node.get("name", "")
        children = node.get("children", [])
        
        # 如果是一级节点（level=0），则使用当前节点名作为一级目录名
        if level == 0:
            current_first_level = folder_name
            # 记录所有一级目录
            if folder_id:
                all_first_level_folders[current_first_level] = {
                    "id": folder_id,
                    "name": folder_name,
                    "has_datasets": False
                }
        else:
            current_first_level = first_level_name
        
        if folder_id:
            folder_id_to_first_level[folder_id] = current_first_level
        
        # 递归处理子节点
        if children:
            build_folder_mapping(children, current_first_level, level + 1)

# 构建映射 - 从 tree 字段获取
if isinstance(folder_tree, dict):
    tree = folder_tree.get("tree", [])
    if tree:
        build_folder_mapping(tree)
        print(f"构建了 {len(folder_id_to_first_level)} 个文件夹的映射关系")
        print(f"发现 {len(all_first_level_folders)} 个一级目录:")
        for idx, name in enumerate(sorted(all_first_level_folders.keys()), 1):
            print(f"  {idx:2d}. {name}")
    else:
        print(f"警告: tree 字段为空")
else:
    print(f"警告: 返回数据不是字典类型")

# 获取知识库列表
status, datasets_list = dataset.list_datasets(WORKSPACE_ID)
if status != 200:
    print(f"获取知识库列表失败: {datasets_list}")
    sys.exit(1)

print(f"获取到 {len(datasets_list)} 个知识库")
datasets = [ds for ds in datasets_list if isinstance(ds, dict)]


def get_first_level_folder_name(folder_id):
    """根据 folder_id 获取一级目录名称"""
    if not folder_id:
        return "根目录"
    return folder_id_to_first_level.get(folder_id, f"未知目录(ID:{folder_id})")


def get_folder_path(folder_id):
    """根据 folder_id 获取文件夹路径（用于向后兼容）"""
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
    size = doc.get("file_size")
    if size is not None and size > 0:
        return size
    size = doc.get("size")
    if size is not None and size > 0:
        return size
    return 0


def format_size(size_bytes):
    """格式化文件大小为人类可读格式"""
    if size_bytes >= 1024 ** 4:
        return f"{size_bytes / (1024 ** 4):.2f} TB"
    elif size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
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


# 文本文件类型
TEXT_FILE_TYPES = {'doc', 'docx', 'txt', 'md', 'wps'}

# 存储所有数据
all_docs = []  # 所有文档数据
dataset_info = []  # 知识库信息（包含一级目录）

# 遍历知识库获取文档
for i, ds in enumerate(datasets):
    dataset_id = ds.get("id")
    dataset_name = ds.get("name")
    folder_id = ds.get("folder_id")
    folder_path = get_folder_path(folder_id)
    first_level_folder = get_first_level_folder_name(folder_id)  # 获取一级目录名称
    
    print(f"[{i+1}/{len(datasets)}] 正在处理: {dataset_name}", end="")
    
    # 记录知识库信息
    dataset_record = {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "first_level_folder": first_level_folder,
        "folder_path": folder_path,
        "doc_count": 0,
        "total_size": 0,
        "文本": 0, "PDF": 0, "其他": 0,
        "成功": 0, "进行中": 0, "待处理": 0, "已取消": 0, "无任务": 0,
    }
    
    try:
        status, documents = dataset.list_documents(dataset_id)
        if status != 200:
            print(f" - 获取文档失败: {documents}")
            dataset_info.append(dataset_record)
            continue
        
        dataset_record["doc_count"] = len(documents)
        
        for doc in documents:
            doc_name = doc.get("name", "未知")
            doc_size = get_doc_size(doc)
            doc_type = doc.get("type", "")
            doc_status, _ = get_doc_status(doc)
            
            # 确定文件类别
            if doc_type in TEXT_FILE_TYPES:
                file_category = "文本"
            elif doc_type == "pdf":
                file_category = "PDF"
            else:
                file_category = "其他"
            
            # 标准化状态
            if doc_status in ["completed", "success"]:
                status_label = "成功"
            elif doc_status in ["indexing", "parsing", "waiting", "queuing"]:
                status_label = "进行中"
            elif doc_status in ["error", "failed"]:
                status_label = "待处理"
            elif doc_status == "cancelled":
                status_label = "已取消"
            elif doc_status == "no_task":
                status_label = "无任务"
            else:
                status_label = doc_status
            
            # 更新知识库统计
            dataset_record["total_size"] += doc_size
            dataset_record[file_category] += 1
            dataset_record[status_label] += 1
            
            # 记录文档详情
            all_docs.append({
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "folder_path": folder_path,
                "first_level_folder": first_level_folder,
                "doc_name": doc_name,
                "doc_type": doc_type,
                "file_category": file_category,
                "status": status_label,
                "size": doc_size,
            })
        
        print(f" - 文档数: {len(documents)}")
        dataset_info.append(dataset_record)
            
    except Exception as e:
        print(f" - 处理出错: {e}")
        dataset_info.append(dataset_record)

# ============================================================================
# 统计计算
# ============================================================================

total_docs = len(all_docs)
total_size = sum(d["size"] for d in all_docs)

# 按状态统计
status_stats = {}
for doc in all_docs:
    s = doc["status"]
    if s not in status_stats:
        status_stats[s] = {"count": 0, "size": 0}
    status_stats[s]["count"] += 1
    status_stats[s]["size"] += doc["size"]

# 按文件类别统计
category_stats = {"文本": {}, "PDF": {}, "其他": {}}
for cat in category_stats:
    category_stats[cat] = {
        "总数": 0, "总大小": 0,
        "成功": 0, "成功大小": 0,
        "进行中": 0, "进行中大小": 0,
        "待处理": 0, "待处理大小": 0,
        "已取消": 0, "已取消大小": 0,
        "无任务": 0, "无任务大小": 0,
    }

for doc in all_docs:
    cat = doc["file_category"]
    s = doc["status"]
    size = doc["size"]
    
    category_stats[cat]["总数"] += 1
    category_stats[cat]["总大小"] += size
    
    if s in category_stats[cat]:
        category_stats[cat][s] += 1
        category_stats[cat][f"{s}大小"] += size

# 按一级目录统计（改为基于知识库的统计）
first_level_stats = {}

# 首先初始化所有一级目录（即使没有知识库）
for dir_name in all_first_level_folders.keys():
    first_level_stats[dir_name] = {
        "知识库数": 0,
        "知识库列表": [],
        "总文档数": 0, 
        "总大小": 0,
        "文本": 0, "文本大小": 0,
        "PDF": 0, "PDF大小": 0,
        "其他": 0, "其他大小": 0,
        "成功": 0, "进行中": 0, "待处理": 0, "已取消": 0, "无任务": 0,
    }

# 统计各知识库到一级目录
for ds_info in dataset_info:
    first_dir = ds_info["first_level_folder"]
    
    # 如果目录不在统计中，添加进去（处理根目录和未知目录的情况）
    if first_dir not in first_level_stats:
        first_level_stats[first_dir] = {
            "知识库数": 0,
            "知识库列表": [],
            "总文档数": 0, 
            "总大小": 0,
            "文本": 0, "文本大小": 0,
            "PDF": 0, "PDF大小": 0,
            "其他": 0, "其他大小": 0,
            "成功": 0, "进行中": 0, "待处理": 0, "已取消": 0, "无任务": 0,
        }
    
    stats = first_level_stats[first_dir]
    stats["知识库数"] += 1
    stats["知识库列表"].append({
        "name": ds_info["dataset_name"],
        "doc_count": ds_info["doc_count"],
        "size": ds_info["total_size"],
    })
    stats["总文档数"] += ds_info["doc_count"]
    stats["总大小"] += ds_info["total_size"]
    
    # 标记该一级目录有知识库
    if first_dir in all_first_level_folders:
        all_first_level_folders[first_dir]["has_datasets"] = True
    
    # 按文件类别统计
    for cat in ["文本", "PDF", "其他"]:
        stats[cat] += ds_info[cat]
    
    # 按状态统计
    for s in ["成功", "进行中", "待处理", "已取消", "无任务"]:
        stats[s] += ds_info[s]

# 计算每个类别的大小（需要从文档明细计算）
for doc in all_docs:
    first_dir = doc["first_level_folder"]
    if first_dir in first_level_stats:
        cat = doc["file_category"]
        first_level_stats[first_dir][f"{cat}大小"] += doc["size"]

# ============================================================================
# 生成报告
# ============================================================================

timestamp = start_time.strftime('%Y-%m-%d_%H%M%S')
csv_filename = os.path.join(LOGS_DIR, f"vector_stats_{timestamp}.csv")

# 写入CSV文件
with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    
    # ========== 表1: 汇总统计 ==========
    writer.writerow([f"【汇总统计 - {start_time.strftime('%Y年%m月%d日')}】"])
    writer.writerow(["工作空间", WORKSPACE_NAME])
    writer.writerow(["统计日期", start_time.strftime('%Y-%m-%d')])
    writer.writerow(["统计时间", start_time.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(["知识库数量", len(datasets)])
    writer.writerow(["文档总数", total_docs])
    writer.writerow(["文件总大小", format_size(total_size)])
    writer.writerow([])
    
    # 状态汇总表
    writer.writerow(["状态", "数量", "大小", "占比"])
    status_order = ["成功", "进行中", "待处理", "已取消", "无任务"]
    for s in status_order:
        if s in status_stats:
            count = status_stats[s]["count"]
            size = status_stats[s]["size"]
            pct = f"{count/total_docs*100:.1f}%" if total_docs > 0 else "0%"
            writer.writerow([s, count, format_size(size), pct])
    writer.writerow(["总计", total_docs, format_size(total_size), "100%"])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表2: 文本文件统计 ==========
    writer.writerow([f"【文本文件统计 - {start_time.strftime('%Y-%m-%d')}】(doc/docx/txt/md/wps)"])
    text_stats = category_stats["文本"]
    writer.writerow(["状态", "数量", "大小"])
    writer.writerow(["总数", text_stats["总数"], format_size(text_stats["总大小"])])
    writer.writerow(["成功", text_stats["成功"], format_size(text_stats["成功大小"])])
    writer.writerow(["进行中", text_stats["进行中"], format_size(text_stats["进行中大小"])])
    writer.writerow(["待处理", text_stats["待处理"], format_size(text_stats["待处理大小"])])
    writer.writerow(["已取消", text_stats["已取消"], format_size(text_stats["已取消大小"])])
    writer.writerow(["无任务", text_stats["无任务"], format_size(text_stats["无任务大小"])])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表3: PDF文件统计 ==========
    writer.writerow([f"【PDF文件统计 - {start_time.strftime('%Y-%m-%d')}】"])
    pdf_stats = category_stats["PDF"]
    writer.writerow(["状态", "数量", "大小"])
    writer.writerow(["总数", pdf_stats["总数"], format_size(pdf_stats["总大小"])])
    writer.writerow(["成功", pdf_stats["成功"], format_size(pdf_stats["成功大小"])])
    writer.writerow(["进行中", pdf_stats["进行中"], format_size(pdf_stats["进行中大小"])])
    writer.writerow(["待处理", pdf_stats["待处理"], format_size(pdf_stats["待处理大小"])])
    writer.writerow(["已取消", pdf_stats["已取消"], format_size(pdf_stats["已取消大小"])])
    writer.writerow(["无任务", pdf_stats["无任务"], format_size(pdf_stats["无任务大小"])])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表4: 其他文件统计 ==========
    writer.writerow([f"【其他文件统计 - {start_time.strftime('%Y-%m-%d')}】"])
    other_stats = category_stats["其他"]
    writer.writerow(["状态", "数量", "大小"])
    writer.writerow(["总数", other_stats["总数"], format_size(other_stats["总大小"])])
    writer.writerow(["成功", other_stats["成功"], format_size(other_stats["成功大小"])])
    writer.writerow(["进行中", other_stats["进行中"], format_size(other_stats["进行中大小"])])
    writer.writerow(["待处理", other_stats["待处理"], format_size(other_stats["待处理大小"])])
    writer.writerow(["已取消", other_stats["已取消"], format_size(other_stats["已取消大小"])])
    writer.writerow(["无任务", other_stats["无任务"], format_size(other_stats["无任务大小"])])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表5: 文件大小分布统计 ==========
    writer.writerow([f"【文件大小分布统计 - {start_time.strftime('%Y-%m-%d')}】"])
    
    # 按大小分段
    size_ranges = [
        ("0-100KB", 0, 100 * 1024),
        ("100KB-1MB", 100 * 1024, 1024 * 1024),
        ("1MB-10MB", 1024 * 1024, 10 * 1024 * 1024),
        ("10MB-50MB", 10 * 1024 * 1024, 50 * 1024 * 1024),
        ("50MB-100MB", 50 * 1024 * 1024, 100 * 1024 * 1024),
        (">100MB", 100 * 1024 * 1024, float('inf')),
    ]
    
    size_distribution = {r[0]: {"count": 0, "size": 0} for r in size_ranges}
    for doc in all_docs:
        for range_name, min_size, max_size in size_ranges:
            if min_size <= doc["size"] < max_size:
                size_distribution[range_name]["count"] += 1
                size_distribution[range_name]["size"] += doc["size"]
                break
    
    writer.writerow(["大小范围", "文件数量", "总大小", "占比"])
    for range_name, _, _ in size_ranges:
        count = size_distribution[range_name]["count"]
        size = size_distribution[range_name]["size"]
        pct = f"{count/total_docs*100:.1f}%" if total_docs > 0 else "0%"
        writer.writerow([range_name, count, format_size(size), pct])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表6: 按类型和状态的完整统计表 ==========
    writer.writerow([f"【按文件类型和状态的完整统计 - {start_time.strftime('%Y-%m-%d')}】"])
    writer.writerow(["文件类型", "总数", "总大小", "成功", "进行中", "待处理", "已取消", "无任务"])
    for cat in ["文本", "PDF", "其他"]:
        stats = category_stats[cat]
        writer.writerow([
            cat,
            stats["总数"],
            format_size(stats["总大小"]),
            stats["成功"],
            stats["进行中"],
            stats["待处理"],
            stats["已取消"],
            stats["无任务"],
        ])
    # 总计行
    writer.writerow([
        "总计",
        total_docs,
        format_size(total_size),
        status_stats.get("成功", {}).get("count", 0),
        status_stats.get("进行中", {}).get("count", 0),
        status_stats.get("待处理", {}).get("count", 0),
        status_stats.get("已取消", {}).get("count", 0),
        status_stats.get("无任务", {}).get("count", 0),
    ])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表7: 按一级目录统计（知识库维度）==========
    writer.writerow([f"【按一级目录统计（知识库维度）- {start_time.strftime('%Y-%m-%d')}】"])
    writer.writerow([])
    
    # 按知识库数量排序（根目录优先，然后按知识库数量降序，空目录放最后）
    sorted_dirs = sorted(
        first_level_stats.items(), 
        key=lambda x: (
            x[0] == "根目录" and -1,  # 根目录排第一
            x[1]["知识库数"] == 0,     # 空目录排最后
            -x[1]["知识库数"]          # 其他按知识库数量降序
        )
    )
    
    # 写入汇总统计表
    writer.writerow(["一级目录名称", "知识库数", "文档总数", "总大小", "文本", "PDF", "其他", "成功", "进行中", "待处理", "已取消", "无任务"])
    
    for dir_name, stats in sorted_dirs:
        writer.writerow([
            dir_name,
            stats["知识库数"],
            stats["总文档数"],
            format_size(stats["总大小"]),
            stats["文本"],
            stats["PDF"],
            stats["其他"],
            stats["成功"],
            stats["进行中"],
            stats["待处理"],
            stats["已取消"],
            stats["无任务"],
        ])
    
    # 总计行
    total_datasets = sum(s["知识库数"] for s in first_level_stats.values())
    writer.writerow([
        "【总计】",
        total_datasets,
        total_docs,
        format_size(total_size),
        category_stats["文本"]["总数"],
        category_stats["PDF"]["总数"],
        category_stats["其他"]["总数"],
        status_stats.get("成功", {}).get("count", 0),
        status_stats.get("进行中", {}).get("count", 0),
        status_stats.get("待处理", {}).get("count", 0),
        status_stats.get("已取消", {}).get("count", 0),
        status_stats.get("无任务", {}).get("count", 0),
    ])
    writer.writerow([])
    
    # 写入统计摘要
    non_empty_dirs = sum(1 for s in first_level_stats.values() if s["知识库数"] > 0)
    empty_dirs = len(first_level_stats) - non_empty_dirs
    writer.writerow([f"说明: 共 {len(first_level_stats)} 个一级目录，其中 {non_empty_dirs} 个有知识库，{empty_dirs} 个为空"])
    writer.writerow([])
    
    # ========== 表8: 按一级目录展开知识库明细 ==========
    writer.writerow([f"【一级目录-知识库明细 - {start_time.strftime('%Y-%m-%d')}】"])
    writer.writerow([])
    
    # 只显示有知识库的目录
    dirs_with_datasets = [(name, stats) for name, stats in sorted_dirs if stats["知识库数"] > 0]
    
    for dir_name, stats in dirs_with_datasets:
        # 写入目录标题
        writer.writerow([f"【{dir_name}】", f"知识库数: {stats['知识库数']}", f"文档数: {stats['总文档数']}", f"大小: {format_size(stats['总大小'])}"])
        writer.writerow(["序号", "知识库名称", "文档数", "文件大小"])
        
        # 写入该目录下的知识库列表
        for idx, kb in enumerate(sorted(stats["知识库列表"], key=lambda x: -x["doc_count"]), 1):
            writer.writerow([
                idx,
                kb["name"],
                kb["doc_count"],
                format_size(kb["size"]),
            ])
        
        writer.writerow([])  # 空行分隔
    
    # ========== 表9: 所有文档明细列表 ==========
    writer.writerow([f"【所有文档明细列表 - {start_time.strftime('%Y-%m-%d')}】"])
    writer.writerow(["序号", "一级目录", "知识库名称", "文档名称", "文件类型", "文件大小", "状态"])
    
    # 按一级目录和知识库排序
    sorted_docs = sorted(all_docs, key=lambda x: (x["first_level_folder"] != "根目录", x["first_level_folder"], x["dataset_name"], x["doc_name"]))
    
    for idx, doc in enumerate(sorted_docs, 1):
        writer.writerow([
            idx,
            doc["first_level_folder"],
            doc["dataset_name"],
            doc["doc_name"],
            doc["doc_type"],
            format_size(doc["size"]),
            doc["status"],
        ])

# ============================================================================
# 控制台输出
# ============================================================================

end_time = datetime.now()
duration = end_time - start_time
duration_str = str(duration).split('.')[0]

print("\n" + "=" * 70)
print(f"统计结果 - {start_time.strftime('%Y年%m月%d日')}")
print("=" * 70)

# 汇总统计表格
print(f"\n【汇总统计 - {start_time.strftime('%Y-%m-%d')}】")
print(f"┌{'─'*12}┬{'─'*10}┬{'─'*14}┬{'─'*8}┐")
print(f"│ {'状态':<10} │ {'数量':>8} │ {'大小':>12} │ {'占比':>6} │")
print(f"├{'─'*12}┼{'─'*10}┼{'─'*14}┼{'─'*8}┤")
for s in status_order:
    if s in status_stats:
        count = status_stats[s]["count"]
        size = format_size(status_stats[s]["size"])
        pct = f"{count/total_docs*100:.1f}%" if total_docs > 0 else "0%"
        print(f"│ {s:<10} │ {count:>8} │ {size:>12} │ {pct:>6} │")
print(f"├{'─'*12}┼{'─'*10}┼{'─'*14}┼{'─'*8}┤")
print(f"│ {'总计':<10} │ {total_docs:>8} │ {format_size(total_size):>12} │ {'100%':>6} │")
print(f"└{'─'*12}┴{'─'*10}┴{'─'*14}┴{'─'*8}┘")

# 文本文件统计
print("\n【文本文件统计】(doc/docx/txt/md/wps)")
text_stats = category_stats["文本"]
print(f"  总数: {text_stats['总数']} 个 ({format_size(text_stats['总大小'])})")
print(f"  成功: {text_stats['成功']} | 进行中: {text_stats['进行中']} | 待处理: {text_stats['待处理']} | 已取消: {text_stats['已取消']} | 无任务: {text_stats['无任务']}")

# PDF文件统计
print("\n【PDF文件统计】")
pdf_stats = category_stats["PDF"]
print(f"  总数: {pdf_stats['总数']} 个 ({format_size(pdf_stats['总大小'])})")
print(f"  成功: {pdf_stats['成功']} | 进行中: {pdf_stats['进行中']} | 待处理: {pdf_stats['待处理']} | 已取消: {pdf_stats['已取消']} | 无任务: {pdf_stats['无任务']}")

# 其他文件统计
print("\n【其他文件统计】")
other_stats = category_stats["其他"]
print(f"  总数: {other_stats['总数']} 个 ({format_size(other_stats['总大小'])})")
print(f"  成功: {other_stats['成功']} | 进行中: {other_stats['进行中']} | 待处理: {other_stats['待处理']} | 已取消: {other_stats['已取消']} | 无任务: {other_stats['无任务']}")

# 文件大小分布
print("\n【文件大小分布】")
print(f"┌{'─'*14}┬{'─'*10}┬{'─'*14}┬{'─'*8}┐")
print(f"│ {'大小范围':<12} │ {'数量':>8} │ {'总大小':>12} │ {'占比':>6} │")
print(f"├{'─'*14}┼{'─'*10}┼{'─'*14}┼{'─'*8}┤")
for range_name, _, _ in size_ranges:
    count = size_distribution[range_name]["count"]
    size = format_size(size_distribution[range_name]["size"])
    pct = f"{count/total_docs*100:.1f}%" if total_docs > 0 else "0%"
    print(f"│ {range_name:<12} │ {count:>8} │ {size:>12} │ {pct:>6} │")
print(f"└{'─'*14}┴{'─'*10}┴{'─'*14}┴{'─'*8}┘")

# 按一级目录统计
print("\n【按一级目录统计（知识库维度）】")

# 按知识库数量排序（根目录优先，空目录放最后）
sorted_dirs = sorted(
    first_level_stats.items(), 
    key=lambda x: (
        x[0] == "根目录" and -1,
        x[1]["知识库数"] == 0,
        -x[1]["知识库数"]
    )
)

non_empty_dirs = sum(1 for s in first_level_stats.values() if s["知识库数"] > 0)
empty_dirs = len(first_level_stats) - non_empty_dirs
print(f"共有 {len(first_level_stats)} 个一级目录（{non_empty_dirs} 个有知识库，{empty_dirs} 个为空）")
print()

# 只显示有知识库的目录
dirs_with_datasets = [(name, stats) for name, stats in sorted_dirs if stats["知识库数"] > 0]

for idx, (dir_name, stats) in enumerate(dirs_with_datasets, 1):
    print(f"{idx:2d}. 【{dir_name}】")
    print(f"    知识库: {stats['知识库数']:>3} 个 | 文档: {stats['总文档数']:>5} 个 | 大小: {format_size(stats['总大小']):>10}")
    print(f"    文本:{stats['文本']:>4} PDF:{stats['PDF']:>4} 其他:{stats['其他']:>4} | "
          f"成功:{stats['成功']:>4} 进行中:{stats['进行中']:>4} 待处理:{stats['待处理']:>4}")
    
    # 显示该目录下的知识库（最多显示前3个）
    kb_list = sorted(stats["知识库列表"], key=lambda x: -x["doc_count"])
    display_kb_count = min(3, len(kb_list))
    if kb_list:
        for kb in kb_list[:display_kb_count]:
            print(f"      - {kb['name']}: {kb['doc_count']} 个文档")
        if len(kb_list) > display_kb_count:
            print(f"      ... 还有 {len(kb_list) - display_kb_count} 个知识库")
    print()

if empty_dirs > 0:
    print(f"另有 {empty_dirs} 个一级目录为空（无知识库），详见CSV报告")

# 文档明细统计
print("\n【文档明细统计】")
print(f"文档总数: {total_docs} 个")
print(f"文件总大小: {format_size(total_size)}")
print()
print("按一级目录分布（文档数）:")
sorted_dirs_by_docs = sorted(first_level_stats.items(), key=lambda x: (x[0] != "根目录", -x[1]["总文档数"]))
for idx, (dir_name, stats) in enumerate(sorted_dirs_by_docs[:10], 1):
    pct = stats["总文档数"] / total_docs * 100 if total_docs > 0 else 0
    print(f"  {idx:2d}. {dir_name}: {stats['总文档数']:>5} 个 ({pct:>5.1f}%) - {format_size(stats['总大小']):>10}")

if len(sorted_dirs_by_docs) > 10:
    print(f"  ... 还有 {len(sorted_dirs_by_docs) - 10} 个目录")

print("\n详细的文档列表请查看CSV报告中的【所有文档明细列表】表")

print("\n" + "=" * 70)
print(f"统计完成 - {start_time.strftime('%Y-%m-%d')}")
print("=" * 70)
print(f"工作空间: {WORKSPACE_NAME}")
print(f"统计日期: {start_time.strftime('%Y年%m月%d日')}")
print(f"知识库数: {len(datasets)}")
print(f"文档总数: {total_docs}")
print(f"文件总大小: {format_size(total_size)}")
print(f"统计耗时: {duration_str}")
print("=" * 70)

print(f"\n📊 统计报告已保存到: {csv_filename}")
print("   可直接用 Excel 打开此 CSV 文件")

# ============================================================================
# 上传到远程服务器
# ============================================================================

def upload_to_server(local_file, remote_dir):
    """
    使用 SFTP 上传文件到远程服务器
    
    Args:
        local_file: 本地文件路径
        remote_dir: 远程服务器目录
    
    Returns:
        bool: 上传是否成功
    """
    try:
        import paramiko
    except ImportError:
        print("\n⚠️  警告: 未安装 paramiko 库，无法上传到服务器")
        print("   请运行: pip install paramiko")
        return False
    
    host = REMOTE_SERVER["host"]
    port = REMOTE_SERVER.get("port", 22)
    username = REMOTE_SERVER["username"]
    password = REMOTE_SERVER["password"]
    
    filename = os.path.basename(local_file)
    remote_path = f"{remote_dir}/{filename}"
    
    print(f"\n📤 正在上传到服务器 {host}...")
    print(f"   本地文件: {local_file}")
    print(f"   远程路径: {remote_path}")
    
    try:
        # 创建 SSH 客户端
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # 连接服务器
        ssh.connect(host, port=port, username=username, password=password, timeout=30)
        
        # 确保远程目录存在
        stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_dir}")
        stdout.read()  # 等待命令完成
        
        # 创建 SFTP 会话
        sftp = ssh.open_sftp()
        
        # 上传文件
        sftp.put(local_file, remote_path)
        
        # 获取远程文件大小验证上传
        remote_stat = sftp.stat(remote_path)
        local_size = os.path.getsize(local_file)
        
        sftp.close()
        ssh.close()
        
        if remote_stat.st_size == local_size:
            print(f"   ✅ 上传成功! 文件大小: {format_size(local_size)}")
            return True
        else:
            print(f"   ⚠️  上传可能不完整，本地: {local_size} 字节，远程: {remote_stat.st_size} 字节")
            return False
            
    except Exception as e:
        print(f"   ❌ 上传失败: {e}")
        return False


# 执行上传
print("\n" + "=" * 70)
print("上传统计报告到远程服务器")
print("=" * 70)

upload_success = upload_to_server(csv_filename, REMOTE_SERVER["upload_dir"])

if upload_success:
    remote_path = f"{REMOTE_SERVER['upload_dir']}/{os.path.basename(csv_filename)}"
    print(f"\n📁 文件已上传到服务器:")
    print(f"   服务器: {REMOTE_SERVER['host']}")
    print(f"   路径: {remote_path}")
    print(f"\n💡 获取文件方式:")
    print(f"   1. 使用 SCP: scp root@{REMOTE_SERVER['host']}:{remote_path} ./")
    print(f"   2. 使用 SFTP 客户端连接服务器下载")
else:
    print("\n⚠️  文件未能上传到服务器，请检查网络或服务器配置")
