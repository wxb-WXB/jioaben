# -*- coding: utf-8 -*-
"""
远程知识库文档统计脚本

功能：
- 统计知识库的向量化状态
- 分类显示：成功、进行中、失败、已取消、无任务
- 生成Excel格式的统计报告（CSV格式）

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
from src.config import API_KEY, WORKSPACES, LOGS_DIR

# 只统计第一个工作空间
TARGET_WORKSPACE = WORKSPACES[0]
WORKSPACE_ID = TARGET_WORKSPACE["id"]
WORKSPACE_NAME = TARGET_WORKSPACE["name"]

# 确保logs文件夹存在
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# 记录开始时间
start_time = datetime.now()
print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"统计工作空间: {WORKSPACE_NAME}")
print("=" * 60)

dataset = LingyanDataset(API_KEY)

# 获取知识库列表
status, datasets_list = dataset.list_datasets(WORKSPACE_ID)
if status != 200:
    print(f"获取知识库列表失败: {datasets_list}")
    sys.exit(1)

print(f"获取到 {len(datasets_list)} 个知识库")
datasets = [ds for ds in datasets_list if isinstance(ds, dict)]


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

# 存储所有文档数据
all_docs = []

# 遍历知识库获取文档
for i, ds in enumerate(datasets):
    dataset_id = ds.get("id")
    dataset_name = ds.get("name")
    folder_id = ds.get("folder_id")
    folder_path = get_folder_path(folder_id)
    
    print(f"[{i+1}/{len(datasets)}] 正在处理: {dataset_name}", end="")
    
    try:
        status, documents = dataset.list_documents(dataset_id)
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
                "dataset_name": dataset_name,
                "folder_path": folder_path,
                "doc_name": doc_name,
                "doc_type": doc_type,
                "file_category": file_category,
                "status": status_label,
                "size": doc_size,
            })
        
        print(f" - 文档数: {len(documents)}")
            
    except Exception as e:
        print(f" - 处理出错: {e}")

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

# ============================================================================
# 生成报告
# ============================================================================

timestamp = start_time.strftime('%Y-%m-%d_%H%M%S')
csv_filename = os.path.join(LOGS_DIR, f"vector_stats_{timestamp}.csv")

# 写入CSV文件
with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    
    # ========== 表1: 汇总统计 ==========
    writer.writerow(["【汇总统计】"])
    writer.writerow(["工作空间", WORKSPACE_NAME])
    writer.writerow(["统计时间", start_time.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(["知识库数量", len(datasets)])
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

print("\n" + "=" * 70)
print(f"工作空间: {WORKSPACE_NAME}")
print(f"知识库数: {len(datasets)}")
print(f"文档总数: {total_docs}")
print(f"文件总大小: {format_size(total_size)}")
print(f"统计耗时: {duration_str}")
print("=" * 70)

print(f"\n📊 统计报告已保存到: {csv_filename}")
print("   可直接用 Excel 打开此 CSV 文件")
