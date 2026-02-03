# -*- coding: utf-8 -*-
"""
本地上传记录统计脚本

功能：
- 基于 success_records.json 和 failed_records 统计文件上传情况
- 按文件类型分类统计
- 按知识库（dataset）分类统计
- 生成Excel格式的统计报告（CSV格式）

使用方法：
python scripts/local/scan_local_records.py
"""
import sys
import os
import csv
import json
import glob
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from src.config import DATA_DIR, LOGS_DIR

# 数据文件路径
SUCCESS_RECORDS_FILE = os.path.join(DATA_DIR, "success_records", "success_records.json")
FAILED_RECORDS_DIR = os.path.join(DATA_DIR, "failed_records")

# 确保logs文件夹存在
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# 记录开始时间
start_time = datetime.now()
print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)


def get_file_extension(filename):
    """获取文件扩展名（小写，不含点）"""
    if '.' in filename:
        return filename.rsplit('.', 1)[-1].lower()
    return "无后缀"


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


def get_file_size(file_path):
    """获取文件大小"""
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
    except:
        pass
    return 0


# 文件类型分类
FILE_CATEGORIES = {
    '文本': {'doc', 'docx', 'txt', 'md', 'rtf', 'odt', 'wps'},
    'PDF': {'pdf'},
    '表格': {'xls', 'xlsx', 'xlsm', 'csv', 'et', 'ods'},
    'PPT': {'ppt', 'pptx', 'pptm', 'dps', 'odp'},
    '图片': {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'tif', 'svg'},
    '视频': {'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm'},
    '音频': {'mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a'},
    '压缩包': {'zip', 'rar', '7z', 'tar', 'gz'},
}


def get_file_category(ext):
    """根据扩展名获取文件分类"""
    for category, exts in FILE_CATEGORIES.items():
        if ext in exts:
            return category
    return "其他"


# ============================================================================
# 加载数据
# ============================================================================

print("正在加载上传记录...")

# 加载成功记录
success_records = []
if os.path.exists(SUCCESS_RECORDS_FILE):
    with open(SUCCESS_RECORDS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        success_records = data.get("records", [])
        print(f"  成功记录: {len(success_records)} 条")

# 加载失败记录
failed_records = []
failed_files = glob.glob(os.path.join(FAILED_RECORDS_DIR, "failed_*.json"))
for failed_file in failed_files:
    try:
        with open(failed_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            records = data.get("records", [])
            failed_records.extend(records)
    except Exception as e:
        print(f"  警告: 无法读取 {failed_file}: {e}")
print(f"  失败记录: {len(failed_records)} 条 (来自 {len(failed_files)} 个文件)")

total_records = len(success_records) + len(failed_records)
print(f"  总记录数: {total_records} 条")
print()

# ============================================================================
# 统计计算
# ============================================================================

print("正在统计分析...")

# 存储统计数据
all_docs = []

# 处理成功记录
for record in success_records:
    file_path = record.get("file_path", "")
    file_name = record.get("file_name", os.path.basename(file_path))
    dataset_id = record.get("dataset_id", "")
    
    ext = get_file_extension(file_name)
    category = get_file_category(ext)
    size = get_file_size(file_path)
    
    all_docs.append({
        "file_name": file_name,
        "file_path": file_path,
        "dataset_id": dataset_id,
        "ext": ext,
        "category": category,
        "status": "成功",
        "size": size,
    })

# 处理失败记录
for record in failed_records:
    file_path = record.get("file_path", "")
    file_name = record.get("file_name", os.path.basename(file_path))
    dataset_id = record.get("dataset_id", "")
    dataset_name = record.get("dataset_name", "")
    error_stage = record.get("error_stage", "unknown")
    
    ext = get_file_extension(file_name)
    category = get_file_category(ext)
    size = get_file_size(file_path)
    
    all_docs.append({
        "file_name": file_name,
        "file_path": file_path,
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "ext": ext,
        "category": category,
        "status": "失败",
        "error_stage": error_stage,
        "size": size,
    })

# 计算总大小
total_size = sum(d["size"] for d in all_docs)
success_docs = [d for d in all_docs if d["status"] == "成功"]
failed_docs = [d for d in all_docs if d["status"] == "失败"]
success_size = sum(d["size"] for d in success_docs)
failed_size = sum(d["size"] for d in failed_docs)

# 按状态统计
status_stats = {
    "成功": {"count": len(success_docs), "size": success_size},
    "失败": {"count": len(failed_docs), "size": failed_size},
}

# 按文件类别统计
category_stats = defaultdict(lambda: {
    "总数": 0, "总大小": 0,
    "成功": 0, "成功大小": 0,
    "失败": 0, "失败大小": 0,
})

for doc in all_docs:
    cat = doc["category"]
    s = doc["status"]
    size = doc["size"]
    
    category_stats[cat]["总数"] += 1
    category_stats[cat]["总大小"] += size
    category_stats[cat][s] += 1
    category_stats[cat][f"{s}大小"] += size

# 按扩展名统计
ext_stats = defaultdict(lambda: {
    "总数": 0, "总大小": 0,
    "成功": 0, "成功大小": 0,
    "失败": 0, "失败大小": 0,
})

for doc in all_docs:
    ext = doc["ext"]
    s = doc["status"]
    size = doc["size"]
    
    ext_stats[ext]["总数"] += 1
    ext_stats[ext]["总大小"] += size
    ext_stats[ext][s] += 1
    ext_stats[ext][f"{s}大小"] += size

# 按知识库统计
dataset_stats = defaultdict(lambda: {
    "总数": 0, "总大小": 0,
    "成功": 0, "成功大小": 0,
    "失败": 0, "失败大小": 0,
})

for doc in all_docs:
    dataset_id = doc.get("dataset_id", "未知")
    if not dataset_id:
        dataset_id = "未知"
    s = doc["status"]
    size = doc["size"]
    
    dataset_stats[dataset_id]["总数"] += 1
    dataset_stats[dataset_id]["总大小"] += size
    dataset_stats[dataset_id][s] += 1
    dataset_stats[dataset_id][f"{s}大小"] += size

# 文件大小分布
size_ranges = [
    ("0-100KB", 0, 100 * 1024),
    ("100KB-1MB", 100 * 1024, 1024 * 1024),
    ("1MB-10MB", 1024 * 1024, 10 * 1024 * 1024),
    ("10MB-50MB", 10 * 1024 * 1024, 50 * 1024 * 1024),
    ("50MB-100MB", 50 * 1024 * 1024, 100 * 1024 * 1024),
    (">100MB", 100 * 1024 * 1024, float('inf')),
]

size_distribution = {r[0]: {"count": 0, "size": 0, "success": 0, "failed": 0} for r in size_ranges}
for doc in all_docs:
    for range_name, min_size, max_size in size_ranges:
        if min_size <= doc["size"] < max_size:
            size_distribution[range_name]["count"] += 1
            size_distribution[range_name]["size"] += doc["size"]
            if doc["status"] == "成功":
                size_distribution[range_name]["success"] += 1
            else:
                size_distribution[range_name]["failed"] += 1
            break

# ============================================================================
# 生成报告
# ============================================================================

timestamp = start_time.strftime('%Y-%m-%d_%H%M%S')
csv_filename = os.path.join(LOGS_DIR, f"upload_stats_{timestamp}.csv")

# 写入CSV文件
with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    
    # ========== 表1: 汇总统计 ==========
    writer.writerow(["【汇总统计】"])
    writer.writerow(["统计时间", start_time.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(["文档总数", len(all_docs)])
    writer.writerow(["文件总大小", format_size(total_size)])
    writer.writerow([])
    
    # 状态汇总表
    writer.writerow(["状态", "数量", "大小", "占比"])
    for s in ["成功", "失败"]:
        if s in status_stats:
            count = status_stats[s]["count"]
            size = status_stats[s]["size"]
            pct = f"{count/len(all_docs)*100:.1f}%" if len(all_docs) > 0 else "0%"
            writer.writerow([s, count, format_size(size), pct])
    writer.writerow(["总计", len(all_docs), format_size(total_size), "100%"])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表2: 按文件类型统计 ==========
    writer.writerow(["【按文件类型统计】"])
    writer.writerow(["类型", "总数", "总大小", "成功", "成功大小", "失败", "失败大小", "成功率"])
    
    sorted_categories = sorted(category_stats.items(), key=lambda x: -x[1]["总数"])
    for cat, stats in sorted_categories:
        success_rate = f"{stats['成功']/stats['总数']*100:.1f}%" if stats["总数"] > 0 else "0%"
        writer.writerow([
            cat,
            stats["总数"],
            format_size(stats["总大小"]),
            stats["成功"],
            format_size(stats["成功大小"]),
            stats["失败"],
            format_size(stats["失败大小"]),
            success_rate,
        ])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表3: 按扩展名统计（前20） ==========
    writer.writerow(["【按扩展名统计（前20）】"])
    writer.writerow(["扩展名", "总数", "总大小", "成功", "失败", "成功率"])
    
    sorted_exts = sorted(ext_stats.items(), key=lambda x: -x[1]["总数"])[:20]
    for ext, stats in sorted_exts:
        success_rate = f"{stats['成功']/stats['总数']*100:.1f}%" if stats["总数"] > 0 else "0%"
        writer.writerow([
            f".{ext}",
            stats["总数"],
            format_size(stats["总大小"]),
            stats["成功"],
            stats["失败"],
            success_rate,
        ])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表4: 文件大小分布 ==========
    writer.writerow(["【文件大小分布】"])
    writer.writerow(["大小范围", "文件数量", "总大小", "成功", "失败", "占比"])
    for range_name, _, _ in size_ranges:
        count = size_distribution[range_name]["count"]
        size = size_distribution[range_name]["size"]
        success = size_distribution[range_name]["success"]
        failed = size_distribution[range_name]["failed"]
        pct = f"{count/len(all_docs)*100:.1f}%" if len(all_docs) > 0 else "0%"
        writer.writerow([range_name, count, format_size(size), success, failed, pct])
    writer.writerow([])
    writer.writerow([])
    
    # ========== 表5: 按知识库统计 ==========
    writer.writerow(["【按知识库统计】"])
    writer.writerow(["知识库ID", "总数", "总大小", "成功", "失败", "成功率"])
    
    sorted_datasets = sorted(dataset_stats.items(), key=lambda x: -x[1]["总数"])
    for dataset_id, stats in sorted_datasets:
        success_rate = f"{stats['成功']/stats['总数']*100:.1f}%" if stats["总数"] > 0 else "0%"
        display_id = dataset_id[:20] + "..." if len(dataset_id) > 20 else dataset_id
        writer.writerow([
            display_id,
            stats["总数"],
            format_size(stats["总大小"]),
            stats["成功"],
            stats["失败"],
            success_rate,
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
for s in ["成功", "失败"]:
    if s in status_stats:
        count = status_stats[s]["count"]
        size = format_size(status_stats[s]["size"])
        pct = f"{count/len(all_docs)*100:.1f}%" if len(all_docs) > 0 else "0%"
        print(f"│ {s:<10} │ {count:>8} │ {size:>12} │ {pct:>6} │")
print(f"├{'─'*12}┼{'─'*10}┼{'─'*14}┼{'─'*8}┤")
print(f"│ {'总计':<10} │ {len(all_docs):>8} │ {format_size(total_size):>12} │ {'100%':>6} │")
print(f"└{'─'*12}┴{'─'*10}┴{'─'*14}┴{'─'*8}┘")

# 按文件类型统计
print("\n【按文件类型统计】")
print(f"┌{'─'*10}┬{'─'*10}┬{'─'*14}┬{'─'*8}┬{'─'*8}┬{'─'*8}┐")
print(f"│ {'类型':<8} │ {'总数':>8} │ {'总大小':>12} │ {'成功':>6} │ {'失败':>6} │ {'成功率':>6} │")
print(f"├{'─'*10}┼{'─'*10}┼{'─'*14}┼{'─'*8}┼{'─'*8}┼{'─'*8}┤")
for cat, stats in sorted(category_stats.items(), key=lambda x: -x[1]["总数"]):
    success_rate = f"{stats['成功']/stats['总数']*100:.0f}%" if stats["总数"] > 0 else "0%"
    print(f"│ {cat:<8} │ {stats['总数']:>8} │ {format_size(stats['总大小']):>12} │ {stats['成功']:>6} │ {stats['失败']:>6} │ {success_rate:>6} │")
print(f"└{'─'*10}┴{'─'*10}┴{'─'*14}┴{'─'*8}┴{'─'*8}┴{'─'*8}┘")

# 按扩展名统计（前10）
print("\n【按扩展名统计（前10）】")
print(f"┌{'─'*12}┬{'─'*10}┬{'─'*14}┬{'─'*8}┬{'─'*8}┐")
print(f"│ {'扩展名':<10} │ {'总数':>8} │ {'总大小':>12} │ {'成功':>6} │ {'失败':>6} │")
print(f"├{'─'*12}┼{'─'*10}┼{'─'*14}┼{'─'*8}┼{'─'*8}┤")
for ext, stats in sorted(ext_stats.items(), key=lambda x: -x[1]["总数"])[:10]:
    print(f"│ .{ext:<9} │ {stats['总数']:>8} │ {format_size(stats['总大小']):>12} │ {stats['成功']:>6} │ {stats['失败']:>6} │")
print(f"└{'─'*12}┴{'─'*10}┴{'─'*14}┴{'─'*8}┴{'─'*8}┘")

# 文件大小分布
print("\n【文件大小分布】")
print(f"┌{'─'*14}┬{'─'*10}┬{'─'*14}┬{'─'*8}┬{'─'*8}┐")
print(f"│ {'大小范围':<12} │ {'数量':>8} │ {'总大小':>12} │ {'成功':>6} │ {'失败':>6} │")
print(f"├{'─'*14}┼{'─'*10}┼{'─'*14}┼{'─'*8}┼{'─'*8}┤")
for range_name, _, _ in size_ranges:
    count = size_distribution[range_name]["count"]
    size = format_size(size_distribution[range_name]["size"])
    success = size_distribution[range_name]["success"]
    failed = size_distribution[range_name]["failed"]
    print(f"│ {range_name:<12} │ {count:>8} │ {size:>12} │ {success:>6} │ {failed:>6} │")
print(f"└{'─'*14}┴{'─'*10}┴{'─'*14}┴{'─'*8}┴{'─'*8}┘")

# 知识库统计（前10）
print("\n【按知识库统计（前10）】")
sorted_datasets = sorted(dataset_stats.items(), key=lambda x: -x[1]["总数"])[:10]
print(f"┌{'─'*26}┬{'─'*10}┬{'─'*8}┬{'─'*8}┬{'─'*8}┐")
print(f"│ {'知识库ID':<24} │ {'总数':>8} │ {'成功':>6} │ {'失败':>6} │ {'成功率':>6} │")
print(f"├{'─'*26}┼{'─'*10}┼{'─'*8}┼{'─'*8}┼{'─'*8}┤")
for dataset_id, stats in sorted_datasets:
    display_id = dataset_id[:22] + ".." if len(dataset_id) > 22 else dataset_id
    success_rate = f"{stats['成功']/stats['总数']*100:.0f}%" if stats["总数"] > 0 else "0%"
    print(f"│ {display_id:<24} │ {stats['总数']:>8} │ {stats['成功']:>6} │ {stats['失败']:>6} │ {success_rate:>6} │")
print(f"└{'─'*26}┴{'─'*10}┴{'─'*8}┴{'─'*8}┴{'─'*8}┘")

print("\n" + "=" * 70)
print(f"文档总数: {len(all_docs)}")
print(f"  - 成功: {len(success_docs)} ({len(success_docs)/len(all_docs)*100:.1f}%)")
print(f"  - 失败: {len(failed_docs)} ({len(failed_docs)/len(all_docs)*100:.1f}%)")
print(f"文件总大小: {format_size(total_size)}")
print(f"统计耗时: {duration_str}")
print("=" * 70)

print(f"\n📊 统计报告已保存到: {csv_filename}")
print("   可直接用 Excel 打开此 CSV 文件")
