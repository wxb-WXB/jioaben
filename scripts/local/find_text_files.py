# -*- coding: utf-8 -*-
"""
灵燕平台文本文件统计脚本

功能：
- 查询灵燕平台上所有已上传的文本文件（txt, doc, docx, md等）
- 显示每个文本文件的完整路径和所属知识库
- 按扩展名分类统计
- 支持导出结果到文件

使用方法：
python scripts/local/find_text_files.py
"""
import sys
import os
from datetime import datetime
from collections import defaultdict

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

# ============================================================
# 配置参数
# ============================================================

# 文本文件扩展名定义
TEXT_EXTENSIONS = {
    # 常见文本文档
    'txt', 'md', 'markdown', 'text', 'readme',
    # Office文档
    'doc', 'docx', 'rtf', 'odt', 'wps',
    # 其他文档格式
    'tex', 'log', 'rst', 'note', 'pages',
}

# 是否导出到文件
EXPORT_TO_FILE = True

# ============================================================


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


def get_file_extension(filename):
    """获取文件扩展名（小写，不含点）"""
    if '.' in filename:
        return filename.rsplit('.', 1)[-1].lower()
    return ""


def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_doc_size(doc):
    """获取文档大小（字节）"""
    size = doc.get("file_size")
    if size is not None and size > 0:
        return size
    size = doc.get("size")
    if size is not None and size > 0:
        return size
    return 0


def main():
    # 确保logs文件夹存在
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    
    start_time = datetime.now()
    
    print("=" * 80)
    print(f"灵燕平台文本文件统计 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"文本扩展名: {', '.join(sorted(TEXT_EXTENSIONS))}")
    print("=" * 80)
    print()
    
    dataset_api = LingyanDataset(API_KEY)
    
    # 获取所有工作空间的知识库列表
    all_datasets = []
    for ws_id, ws_name in WORKSPACE_IDS:
        status, datasets_list = dataset_api.list_datasets(ws_id)
        if status != 200:
            print(f"[{ws_name}] 获取知识库列表失败: {datasets_list}")
            continue
        print(f"[{ws_name}] 获取到 {len(datasets_list)} 个知识库")
        for ds in datasets_list:
            if not isinstance(ds, dict):
                continue
            ds["_workspace_id"] = ws_id
            ds["_workspace_name"] = ws_name
            all_datasets.append(ds)
    
    print(f"\n总共获取到 {len(all_datasets)} 个知识库")
    print()
    
    # 统计变量
    text_files = []  # [(文件名, 大小, 扩展名, 知识库名, 文件夹路径, 工作空间)]
    ext_stats = defaultdict(lambda: {'count': 0, 'size': 0})
    ws_stats = defaultdict(lambda: {'count': 0, 'size': 0})
    dataset_stats = defaultdict(lambda: {'count': 0, 'size': 0, 'files': []})
    
    total_docs = 0
    total_text_docs = 0
    
    # 遍历所有知识库
    for i, ds in enumerate(all_datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        ws_name = ds.get("_workspace_name", "未知")
        
        print(f"[{i+1}/{len(all_datasets)}] [{ws_name}] 扫描知识库: {dataset_name}", end="")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id)
            if status != 200:
                print(f" - 获取文档失败: {documents}")
                continue
            
            text_count = 0
            for doc in documents:
                total_docs += 1
                doc_name = doc.get("name", "未知")
                doc_size = get_doc_size(doc)
                ext = get_file_extension(doc_name)
                
                # 检查是否为文本文件
                if ext in TEXT_EXTENSIONS:
                    total_text_docs += 1
                    text_count += 1
                    
                    text_files.append({
                        'name': doc_name,
                        'size': doc_size,
                        'ext': ext,
                        'dataset': dataset_name,
                        'folder_path': folder_path,
                        'workspace': ws_name,
                    })
                    
                    ext_stats[ext]['count'] += 1
                    ext_stats[ext]['size'] += doc_size
                    
                    ws_stats[ws_name]['count'] += 1
                    ws_stats[ws_name]['size'] += doc_size
                    
                    dataset_key = f"[{ws_name}] {dataset_name}"
                    dataset_stats[dataset_key]['count'] += 1
                    dataset_stats[dataset_key]['size'] += doc_size
                    dataset_stats[dataset_key]['folder_path'] = folder_path
                    dataset_stats[dataset_key]['files'].append(doc_name)
            
            if text_count > 0:
                print(f" - 找到 {text_count} 个文本文件")
            else:
                print(f" - 无文本文件 (共 {len(documents)} 个文档)")
                
        except Exception as e:
            print(f" - 处理出错: {e}")
    
    # 计算总大小
    total_size = sum(f['size'] for f in text_files)
    
    # 输出统计结果
    print()
    print("=" * 80)
    print("统计结果")
    print("=" * 80)
    print(f"扫描文档总数: {total_docs}")
    print(f"文本文件总数: {total_text_docs}")
    print(f"文本文件总大小: {format_size(total_size)}")
    print()
    
    # 按扩展名统计
    print("-" * 40)
    print("按扩展名统计:")
    print("-" * 40)
    sorted_exts = sorted(ext_stats.items(), key=lambda x: -x[1]['count'])
    for ext, stats in sorted_exts:
        print(f"  .{ext:<10} 数量: {stats['count']:>6}  大小: {format_size(stats['size']):>12}")
    print()
    
    # 按工作空间统计
    print("-" * 40)
    print("按工作空间统计:")
    print("-" * 40)
    for ws_name, stats in sorted(ws_stats.items(), key=lambda x: -x[1]['count']):
        print(f"  {ws_name:<20} 数量: {stats['count']:>6}  大小: {format_size(stats['size']):>12}")
    print()
    
    # 按知识库统计（只显示有文本文件的）
    print("-" * 40)
    print("按知识库统计（含文本文件的知识库）:")
    print("-" * 40)
    sorted_datasets = sorted(dataset_stats.items(), key=lambda x: -x[1]['count'])
    for ds_key, stats in sorted_datasets[:30]:
        print(f"  {ds_key}")
        print(f"    路径: {stats.get('folder_path', '未知')}")
        print(f"    文本文件数: {stats['count']}  大小: {format_size(stats['size'])}")
    if len(sorted_datasets) > 30:
        print(f"  ... 还有 {len(sorted_datasets) - 30} 个知识库")
    print()
    
    # 显示文件路径列表
    print("=" * 80)
    print("文本文件完整列表:")
    print("=" * 80)
    
    # 按工作空间和知识库分组显示
    files_by_dataset = defaultdict(list)
    for f in text_files:
        key = f"[{f['workspace']}] {f['dataset']}"
        files_by_dataset[key].append(f)
    
    file_index = 0
    for ds_key in sorted(files_by_dataset.keys()):
        files = files_by_dataset[ds_key]
        folder_path = files[0]['folder_path'] if files else "未知"
        print(f"\n📁 {ds_key}")
        print(f"   路径: {folder_path}")
        print(f"   文本文件数: {len(files)}")
        print()
        for f in sorted(files, key=lambda x: x['name']):
            file_index += 1
            print(f"   [{file_index:>4}] {f['name']}")
            print(f"         大小: {format_size(f['size'])}, 类型: .{f['ext']}")
    
    # 计算耗时
    end_time = datetime.now()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0]
    
    print()
    print("=" * 80)
    print(f"统计时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')}")
    print(f"总耗时: {duration_str}")
    print("=" * 80)
    
    # 导出到文件
    if EXPORT_TO_FILE:
        timestamp = start_time.strftime('%Y-%m-%d_%H%M%S')
        output_file = os.path.join(LOGS_DIR, f"text_files_{timestamp}.txt")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"灵燕平台文本文件统计 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n")
            f.write(f"文本扩展名: {', '.join(sorted(TEXT_EXTENSIONS))}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"扫描文档总数: {total_docs}\n")
            f.write(f"文本文件总数: {total_text_docs}\n")
            f.write(f"文本文件总大小: {format_size(total_size)}\n\n")
            
            f.write("-" * 40 + "\n")
            f.write("按扩展名统计:\n")
            f.write("-" * 40 + "\n")
            for ext, stats in sorted_exts:
                f.write(f"  .{ext:<10} 数量: {stats['count']:>6}  大小: {format_size(stats['size']):>12}\n")
            f.write("\n")
            
            f.write("-" * 40 + "\n")
            f.write("按工作空间统计:\n")
            f.write("-" * 40 + "\n")
            for ws_name, stats in sorted(ws_stats.items(), key=lambda x: -x[1]['count']):
                f.write(f"  {ws_name:<20} 数量: {stats['count']:>6}  大小: {format_size(stats['size']):>12}\n")
            f.write("\n")
            
            f.write("-" * 40 + "\n")
            f.write("按知识库统计:\n")
            f.write("-" * 40 + "\n")
            for ds_key, stats in sorted_datasets:
                f.write(f"  {ds_key}\n")
                f.write(f"    路径: {stats.get('folder_path', '未知')}\n")
                f.write(f"    文本文件数: {stats['count']}  大小: {format_size(stats['size'])}\n")
            f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write("文本文件完整列表:\n")
            f.write("=" * 80 + "\n")
            
            file_index = 0
            for ds_key in sorted(files_by_dataset.keys()):
                files = files_by_dataset[ds_key]
                folder_path = files[0]['folder_path'] if files else "未知"
                f.write(f"\n📁 {ds_key}\n")
                f.write(f"   路径: {folder_path}\n")
                f.write(f"   文本文件数: {len(files)}\n\n")
                for file in sorted(files, key=lambda x: x['name']):
                    file_index += 1
                    f.write(f"   [{file_index:>4}] {file['name']}\n")
                    f.write(f"         大小: {format_size(file['size'])}, 类型: .{file['ext']}\n")
            
            f.write("\n")
            f.write("=" * 80 + "\n")
            f.write(f"统计时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')}\n")
            f.write(f"总耗时: {duration_str}\n")
            f.write("=" * 80 + "\n")
        
        print(f"\n📄 结果已导出到: {output_file}")


if __name__ == "__main__":
    main()
