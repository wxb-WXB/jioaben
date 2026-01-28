"""
文档统计脚本 - 按一级目录分类
=============================

统计内容：
- 文件总数
- 向量化成功数量
- 向量化中数量
- 未向量化数量
- 剩余待处理数量

按一级目录（如：行政知识库、技术知识库等）分类统计
按文件类型（Word、PDF）分类统计
"""
import sys
import os
from datetime import datetime
from collections import defaultdict

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset
from models import FolderMap

# ============================================================
# 配置参数
# ============================================================
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

workspace_ids = [
    ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库"),
    ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "第二个知识库"),
]


def get_folder_path(folder_id):
    """根据 folder_id 获取文件夹路径"""
    if not folder_id:
        return ""
    try:
        folder = FolderMap.get_or_none(FolderMap.id == folder_id)
        if folder:
            return folder.folderPath
    except:
        pass
    return ""


def get_top_folder(folder_path):
    """从文件夹路径提取一级目录名"""
    if not folder_path:
        return "未分类"
    
    # 去掉开头的斜杠，分割路径
    path = folder_path.lstrip("/\\")
    parts = path.replace("\\", "/").split("/")
    
    if parts and parts[0]:
        return parts[0]
    return "未分类"


def get_file_type(doc):
    """获取文件类型：pdf/text（除PDF外都是文本）"""
    doc_type = doc.get("type", "").lower()
    if doc_type == "pdf":
        return "pdf"
    else:
        return "text"


def get_doc_status(doc):
    """获取文档向量化状态"""
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task"
    
    normal_tasks = [t for t in tasks if t.get("type") == "normal"]
    if normal_tasks:
        return normal_tasks[-1].get("status", "unknown")
    return tasks[-1].get("status", "unknown")


def main():
    print("=" * 70)
    print(f"文档统计（按一级目录分类） - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    dataset_service = LingyanDataset(api_key)
    
    # 总体统计
    total = 0
    success = 0
    indexing = 0
    not_indexed = 0
    
    # 按文件类型统计（总体）
    type_stats = {
        'text': {'total': 0, 'success': 0, 'indexing': 0, 'not_indexed': 0},
        'pdf': {'total': 0, 'success': 0, 'indexing': 0, 'not_indexed': 0},
    }
    
    # 按一级目录统计
    folder_stats = defaultdict(lambda: {
        'total': 0,
        'success': 0,
        'indexing': 0,
        'not_indexed': 0,
        # 按类型细分
        'text': {'total': 0, 'success': 0},
        'pdf': {'total': 0, 'success': 0},
    })
    
    # 获取所有知识库
    all_datasets = []
    for ws_id, ws_name in workspace_ids:
        print(f"获取 [{ws_name}]...", end="", flush=True)
        status, datasets_list = dataset_service.list_datasets(ws_id)
        if status == 200:
            for ds in datasets_list:
                if isinstance(ds, dict):
                    all_datasets.append(ds)
            print(f" {len(datasets_list)} 个知识库")
        else:
            print(" 失败")
    
    print(f"\n扫描文档中...")
    
    # 遍历知识库
    for i, ds in enumerate(all_datasets):
        dataset_id = ds.get("id")
        folder_id = ds.get("folder_id")
        
        # 获取一级目录
        folder_path = get_folder_path(folder_id)
        top_folder = get_top_folder(folder_path)
        
        print(f"\r  进度: {i+1}/{len(all_datasets)}", end="", flush=True)
        
        try:
            status, documents = dataset_service.list_documents(dataset_id)
            if status != 200:
                continue
            
            for doc in documents:
                file_type = get_file_type(doc)
                
                total += 1
                folder_stats[top_folder]['total'] += 1
                folder_stats[top_folder][file_type]['total'] += 1
                type_stats[file_type]['total'] += 1
                
                # 检查向量化状态
                doc_status = get_doc_status(doc)
                
                if doc_status in ["completed", "success"]:
                    success += 1
                    folder_stats[top_folder]['success'] += 1
                    folder_stats[top_folder][file_type]['success'] += 1
                    type_stats[file_type]['success'] += 1
                elif doc_status in ["indexing", "parsing", "waiting", "queuing"]:
                    indexing += 1
                    folder_stats[top_folder]['indexing'] += 1
                    type_stats[file_type]['indexing'] += 1
                else:
                    not_indexed += 1
                    folder_stats[top_folder]['not_indexed'] += 1
                    type_stats[file_type]['not_indexed'] += 1
                    
        except Exception as e:
            pass
    
    print("\r" + " " * 30)  # 清除进度行
    
    # 输出结果
    remaining = total - success
    
    print("\n" + "=" * 70)
    print("总体统计")
    print("=" * 70)
    print(f"  文件总数:       {total:>8} 个")
    print(f"  向量化成功:     {success:>8} 个")
    print(f"  向量化中:       {indexing:>8} 个")
    print(f"  未向量化:       {not_indexed:>8} 个")
    print("-" * 70)
    print(f"  剩余待处理:     {remaining:>8} 个")
    
    # 按文件类型统计
    print("\n" + "=" * 70)
    print("按文件类型统计")
    print("=" * 70)
    print(f"  {'类型':<10} {'总数':>8} {'成功':>8} {'进行中':>8} {'未处理':>8} {'剩余':>8}")
    print("-" * 70)
    for ftype, label in [('text', '文本'), ('pdf', 'PDF')]:
        ts = type_stats[ftype]
        remaining_type = ts['total'] - ts['success']
        print(f"  {label:<10} {ts['total']:>8} {ts['success']:>8} {ts['indexing']:>8} {ts['not_indexed']:>8} {remaining_type:>8}")
    
    # 按一级目录分类统计
    print("\n" + "=" * 70)
    print("按一级目录分类统计")
    print("=" * 70)
    
    # 按总数降序排列
    sorted_folders = sorted(folder_stats.items(), key=lambda x: -x[1]['total'])
    
    for folder_name, stats in sorted_folders:
        text_remaining = stats['text']['total'] - stats['text']['success']
        pdf_remaining = stats['pdf']['total'] - stats['pdf']['success']
        folder_remaining = stats['total'] - stats['success']
        
        print(f"\n  【{folder_name}】")
        print(f"      总数: {stats['total']}  成功: {stats['success']}  进行中: {stats['indexing']}  未处理: {stats['not_indexed']}  剩余: {folder_remaining}")
        print(f"      文本: {stats['text']['total']} (成功{stats['text']['success']}, 剩余{text_remaining})  PDF: {stats['pdf']['total']} (成功{stats['pdf']['success']}, 剩余{pdf_remaining})")
    
    # 汇总
    text_total = type_stats['text']['total']
    text_success = type_stats['text']['success']
    pdf_total = type_stats['pdf']['total']
    pdf_success = type_stats['pdf']['success']
    
    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)
    print(f"  文件总数:       {total}")
    print(f"  向量成功:       {success}")
    print(f"  未成功:         {total - success}")
    print(f"  文本总数:       {text_total}  (成功: {text_success}, 未成功: {text_total - text_success})")
    print(f"  PDF总数:        {pdf_total}  (成功: {pdf_success}, 未成功: {pdf_total - pdf_success})")
    print("=" * 70)


if __name__ == "__main__":
    main()
