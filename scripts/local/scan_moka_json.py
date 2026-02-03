# -*- coding: utf-8 -*-
"""
Moka知识库JSON数据统计脚本

功能：
- 读取本地保存的moka API响应数据（aa.json）获取知识库ID列表
- 调用API获取每个知识库的文档详情
- 统计文件类型（PDF、文本等）
- 按文件夹分类统计
- 生成Excel格式的统计报告（CSV格式）

使用方法：
python scripts/local/scan_moka_json.py
"""
import sys
import os
import csv
import json
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from src.config import LOGS_DIR, API_KEY
from src.core import LingyanDataset

# JSON数据文件路径
JSON_FILE = os.path.join(project_root, "aa.json")

# 确保logs文件夹存在
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# 初始化API客户端
dataset_api = LingyanDataset(API_KEY)

# 记录开始时间
start_time = datetime.now()
print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)


def format_size(size_bytes):
    """格式化文件大小为人类可读格式"""
    if size_bytes is None:
        return "0 B"
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


def get_doc_size(doc):
    """获取文档大小（字节）"""
    size = doc.get("file_size")
    if size is not None and size > 0:
        return size
    size = doc.get("size")
    if size is not None and size > 0:
        return size
    return 0


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

# 存储统计数据
all_datasets = []  # 所有知识库
all_folders = []   # 所有文件夹
all_docs = []      # 所有文档
folder_stats = defaultdict(lambda: {"datasets": 0, "files_count": 0, "files_size": 0})


def traverse_tree(node, parent_path="", level=0, top_folder_name=""):
    """递归遍历树形结构，收集所有知识库ID"""
    node_type = node.get("type")
    node_name = node.get("name", "")
    node_id = node.get("id", "")
    current_path = node.get("path") or f"{parent_path}/{node_name}".lstrip("/")
    
    # 确定一级文件夹名称
    if level == 0:
        current_top_folder = node_name
    else:
        current_top_folder = top_folder_name
    
    if node_type == "folder":
        # 文件夹
        all_folders.append({
            "id": node_id,
            "name": node_name,
            "path": current_path,
            "level": level,
        })
    
    elif node_type == "dataset":
        # 知识库
        files_count = node.get("files_count") or 0
        files_size = node.get("files_size") or 0
        is_published = node.get("is_published", False)
        
        all_datasets.append({
            "id": node_id,
            "name": node_name,
            "path": current_path,
            "files_count": files_count,
            "files_size": files_size,
            "is_published": is_published,
            "level": level,
            "top_folder": current_top_folder,
        })
    
    # 递归处理子节点
    children = node.get("children", [])
    for child in children:
        traverse_tree(child, current_path, level + 1, current_top_folder)


# ============================================================================
# 加载数据
# ============================================================================

print(f"正在读取数据文件: {JSON_FILE}")

if not os.path.exists(JSON_FILE):
    print(f"错误: 文件不存在 - {JSON_FILE}")
    sys.exit(1)

with open(JSON_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 检查数据结构
if data.get("code") != 200:
    print(f"错误: API返回错误 - {data.get('msg')}")
    sys.exit(1)

tree_data = data.get("data", {}).get("tree", [])
print(f"获取到 {len(tree_data)} 个顶级节点")

# 遍历树形结构
for root_node in tree_data:
    traverse_tree(root_node, "", 0, "")

print(f"解析完成: {len(all_folders)} 个文件夹, {len(all_datasets)} 个知识库")
print()

# ============================================================================
# 调用API获取每个知识库的文档详情
# ============================================================================

print("正在获取各知识库的文档详情...")
print("=" * 60)

for i, ds in enumerate(all_datasets):
    dataset_id = ds["id"]
    dataset_name = ds["name"]
    top_folder = ds.get("top_folder", "")
    
    print(f"[{i+1}/{len(all_datasets)}] 正在处理: {dataset_name}", end="")
    
    try:
        status, documents = dataset_api.list_documents(dataset_id)
        if status != 200:
            print(f" - 获取文档失败: {documents}")
            continue
        
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
                status_label = "失败"
            elif doc_status == "cancelled":
                status_label = "已取消"
            elif doc_status == "no_task":
                status_label = "无任务"
            else:
                status_label = doc_status
            
            all_docs.append({
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "top_folder": top_folder,
                "doc_name": doc_name,
                "doc_type": doc_type,
                "file_category": file_category,
                "status": status_label,
                "size": doc_size,
            })
        
        print(f" - 文档数: {len(documents)}")
            
    except Exception as e:
        print(f" - 处理出错: {e}")

print()
print(f"共获取 {len(all_docs)} 个文档详情")

# ============================================================================
# 统计计算
# ============================================================================

total_datasets = len(all_datasets)
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
        "失败": 0, "失败大小": 0,
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

# 按一级文件夹统计
for doc in all_docs:
    top_folder = doc.get("top_folder", "未分类")
    if not top_folder:
        top_folder = "未分类"
    size = doc["size"]
    
    if top_folder not in folder_stats:
        folder_stats[top_folder] = {"datasets": 0, "files_count": 0, "files_size": 0}
    folder_stats[top_folder]["files_count"] += 1
    folder_stats[top_folder]["files_size"] += size

# 统计每个文件夹的知识库数
for ds in all_datasets:
    top_folder = ds.get("top_folder", "未分类")
    if not top_folder:
        top_folder = "未分类"
    if top_folder not in folder_stats:
        folder_stats[top_folder] = {"datasets": 0, "files_count": 0, "files_size": 0}
    folder_stats[top_folder]["datasets"] += 1

# 文件大小分布
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

# ============================================================================
# 生成报告
# ============================================================================

timestamp = start_time.strftime('%Y-%m-%d_%H%M%S')
csv_filename = os.path.join(LOGS_DIR, f"moka_stats_{timestamp}.csv")

# 写入CSV文件
with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    
    # ========== 表1: 汇总统计 ==========
    writer.writerow(["【汇总统计】"])
    writer.writerow(["统计时间", start_time.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(["知识库总数", total_datasets])
    writer.writerow(["文档总数", total_docs])
    writer.writerow(["文件总大小", format_size(total_size)])
    writer.writerow([])
    
    # 状态汇总表
    writer.writerow(["状态", "数量", "大小", "占比"])
    status_order = ["成功", "进行中", "失败", "已取消", "无任务"]
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
    writer.writerow(["【文本文件统计】(doc/docx/txt/md/wps)"])
    text_stats = category_stats["文本"]
    writer.writerow(["状态", "数量", "大小"])
    writer.writerow(["总数", text_stats["总数"], format_size(text_stats["总大小"])])
    writer.writerow(["成功", text_stats["成功"], format_size(text_stats["成功大小"])])
    writer.writerow(["进行中", text_stats["进行中"], format_size(text_stats["进行中大小"])])
    writer.writerow(["失败", text_stats["失败"], format_size(text_stats["失败大小"])])
    writer.writerow(["已取消", text_stats["已取消"], format_size(text_stats["已取消大小"])])
    writer.writerow(["无任务", text_stats["无任务"], format_size(text_stats["无任务大小"])])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表3: PDF文件统计 ==========
    writer.writerow(["【PDF文件统计】"])
    pdf_stats = category_stats["PDF"]
    writer.writerow(["状态", "数量", "大小"])
    writer.writerow(["总数", pdf_stats["总数"], format_size(pdf_stats["总大小"])])
    writer.writerow(["成功", pdf_stats["成功"], format_size(pdf_stats["成功大小"])])
    writer.writerow(["进行中", pdf_stats["进行中"], format_size(pdf_stats["进行中大小"])])
    writer.writerow(["失败", pdf_stats["失败"], format_size(pdf_stats["失败大小"])])
    writer.writerow(["已取消", pdf_stats["已取消"], format_size(pdf_stats["已取消大小"])])
    writer.writerow(["无任务", pdf_stats["无任务"], format_size(pdf_stats["无任务大小"])])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表4: 其他文件统计 ==========
    writer.writerow(["【其他文件统计】"])
    other_stats = category_stats["其他"]
    writer.writerow(["状态", "数量", "大小"])
    writer.writerow(["总数", other_stats["总数"], format_size(other_stats["总大小"])])
    writer.writerow(["成功", other_stats["成功"], format_size(other_stats["成功大小"])])
    writer.writerow(["进行中", other_stats["进行中"], format_size(other_stats["进行中大小"])])
    writer.writerow(["失败", other_stats["失败"], format_size(other_stats["失败大小"])])
    writer.writerow(["已取消", other_stats["已取消"], format_size(other_stats["已取消大小"])])
    writer.writerow(["无任务", other_stats["无任务"], format_size(other_stats["无任务大小"])])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表5: 文件大小分布统计 ==========
    writer.writerow(["【文件大小分布统计】"])
    writer.writerow(["大小范围", "文件数量", "总大小", "占比"])
    for range_name, _, _ in size_ranges:
        count = size_distribution[range_name]["count"]
        size = size_distribution[range_name]["size"]
        pct = f"{count/total_docs*100:.1f}%" if total_docs > 0 else "0%"
        writer.writerow([range_name, count, format_size(size), pct])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表6: 按文件类型和状态的完整统计表 ==========
    writer.writerow(["【按文件类型和状态的完整统计】"])
    writer.writerow(["文件类型", "总数", "总大小", "成功", "进行中", "失败", "已取消", "无任务"])
    for cat in ["文本", "PDF", "其他"]:
        stats = category_stats[cat]
        writer.writerow([
            cat,
            stats["总数"],
            format_size(stats["总大小"]),
            stats["成功"],
            stats["进行中"],
            stats["失败"],
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
        status_stats.get("失败", {}).get("count", 0),
        status_stats.get("已取消", {}).get("count", 0),
        status_stats.get("无任务", {}).get("count", 0),
    ])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表7: 按一级文件夹统计 ==========
    writer.writerow(["【按一级文件夹统计】"])
    writer.writerow(["文件夹", "知识库数", "文件数", "文件大小", "占比"])
    
    sorted_folders = sorted(folder_stats.items(), key=lambda x: -x[1]["files_count"])
    for folder_name, stats in sorted_folders:
        pct = f"{stats['files_count']/total_docs*100:.1f}%" if total_docs > 0 else "0%"
        writer.writerow([
            folder_name,
            stats["datasets"],
            stats["files_count"],
            format_size(stats["files_size"]),
            pct,
        ])
    writer.writerow(["总计", total_datasets, total_docs, format_size(total_size), "100%"])

# ============================================================================
# 控制台输出
# ============================================================================

end_time = datetime.now()
duration = end_time - start_time
duration_str = str(duration).split('.')[0]

print("\n" + "=" * 70)
print("统计结果")
print("=" * 70)

# 汇总统计表格
print("\n【汇总统计】")
print(f"┌{'─'*12}┬{'─'*10}┬{'─'*14}┬{'─'*8}┐")
print(f"│ {'状态':<10} │ {'数量':>8} │ {'大小':>12} │ {'占比':>6} │")
print(f"├{'─'*12}┼{'─'*10}┼{'─'*14}┼{'─'*8}┤")
status_order = ["成功", "进行中", "失败", "已取消", "无任务"]
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
print(f"  成功: {text_stats['成功']} | 进行中: {text_stats['进行中']} | 失败: {text_stats['失败']} | 已取消: {text_stats['已取消']} | 无任务: {text_stats['无任务']}")

# PDF文件统计
print("\n【PDF文件统计】")
pdf_stats = category_stats["PDF"]
print(f"  总数: {pdf_stats['总数']} 个 ({format_size(pdf_stats['总大小'])})")
print(f"  成功: {pdf_stats['成功']} | 进行中: {pdf_stats['进行中']} | 失败: {pdf_stats['失败']} | 已取消: {pdf_stats['已取消']} | 无任务: {pdf_stats['无任务']}")

# 其他文件统计
print("\n【其他文件统计】")
other_stats = category_stats["其他"]
print(f"  总数: {other_stats['总数']} 个 ({format_size(other_stats['总大小'])})")
print(f"  成功: {other_stats['成功']} | 进行中: {other_stats['进行中']} | 失败: {other_stats['失败']} | 已取消: {other_stats['已取消']} | 无任务: {other_stats['无任务']}")

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

# 按一级文件夹统计
print("\n【按一级文件夹统计】")
print(f"┌{'─'*20}┬{'─'*10}┬{'─'*10}┬{'─'*14}┬{'─'*8}┐")
print(f"│ {'文件夹':<18} │ {'知识库':>8} │ {'文件数':>8} │ {'大小':>12} │ {'占比':>6} │")
print(f"├{'─'*20}┼{'─'*10}┼{'─'*10}┼{'─'*14}┼{'─'*8}┤")
for folder_name, stats in sorted(folder_stats.items(), key=lambda x: -x[1]["files_count"]):
    pct = f"{stats['files_count']/total_docs*100:.1f}%" if total_docs > 0 else "0%"
    display_name = folder_name[:16] + ".." if len(folder_name) > 16 else folder_name
    print(f"│ {display_name:<18} │ {stats['datasets']:>8} │ {stats['files_count']:>8} │ {format_size(stats['files_size']):>12} │ {pct:>6} │")
print(f"├{'─'*20}┼{'─'*10}┼{'─'*10}┼{'─'*14}┼{'─'*8}┤")
print(f"│ {'总计':<18} │ {total_datasets:>8} │ {total_docs:>8} │ {format_size(total_size):>12} │ {'100%':>6} │")
print(f"└{'─'*20}┴{'─'*10}┴{'─'*10}┴{'─'*14}┴{'─'*8}┘")

print("\n" + "=" * 70)
print(f"知识库数: {total_datasets}")
print(f"文档总数: {total_docs}")
print(f"文件总大小: {format_size(total_size)}")
print(f"统计耗时: {duration_str}")
print("=" * 70)

print(f"\n📊 统计报告已保存到: {csv_filename}")
print("   可直接用 Excel 打开此 CSV 文件")
