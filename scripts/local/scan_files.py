# -*- coding: utf-8 -*-
"""
本地目录文件统计脚本

功能：
- 递归扫描指定本地目录的所有层级
- 按文件类型（后缀名）分类统计
- 按一级目录分类统计
- 支持所有文件类型：文档、图片、视频、压缩包等

使用方法：
1. 修改下方 SCAN_DIRS 配置要扫描的目录
2. 运行脚本: python scripts/local/scan_files.py
"""
import os
import sys
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 尝试从配置文件加载，如果失败则使用默认值
try:
    from src.config import LOCAL_SCAN
    DEFAULT_SCAN_DIRS = LOCAL_SCAN.get("scan_dirs", [])
except ImportError:
    DEFAULT_SCAN_DIRS = []

# ============================================================
# 配置参数 - 修改这里指定要扫描的目录
# ============================================================

# 方式1：扫描多个目录（可以是不同盘符下的多个文件夹）
SCAN_DIRS = DEFAULT_SCAN_DIRS or [
    r"E:\环北部湾广东水资源配置工程",
    r"F:\0-智能体资料汇总收集",
    r"F:\最终分类",
    r"F:\办公室档案知识库资料",
]

# 方式2：扫描整个盘符（取消注释需要扫描的盘）
# SCAN_DIRS = [
#     r"C:\\",
#     r"D:\\",
#     r"E:\\",
#     r"F:\\",
# ]

# ============================================================

# 文件类型分类
FILE_CATEGORIES = {
    '文本': {
        'doc', 'docx', 'txt', 'md', 'rtf', 'odt', 'wps', 'wpd', 'tex', 'log',
        'pages', 'note', 'rst', 'text', 'readme'
    },
    'PDF': {'pdf'},
    '表格': {
        'xls', 'xlsx', 'xlsm', 'xlsb', 'csv', 'et', 'ods', 'numbers', 'tsv',
        'xlt', 'xltx', 'xlw'
    },
    'PPT': {
        'ppt', 'pptx', 'pptm', 'dps', 'odp', 'key', 'ppsx', 'pps', 'pot', 'potx'
    },
    '图片': {
        'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'tif', 'ico', 'svg',
        'raw', 'cr2', 'nef', 'arw', 'dng', 'psd', 'ai', 'eps', 'heic', 'heif',
        'jfif', 'exif', 'pcx', 'tga', 'wmf', 'emf', 'cdr', 'sketch'
    },
    '视频': {
        'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v', 'mpg', 'mpeg',
        'rm', 'rmvb', '3gp', '3g2', 'vob', 'ts', 'mts', 'm2ts', 'divx', 'xvid',
        'f4v', 'swf', 'asf', 'ogv'
    },
    '音频': {
        'mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'ape', 'alac', 'aiff',
        'mid', 'midi', 'amr', 'opus', 'ac3', 'dts', 'ra', 'au', 'cda'
    },
    '压缩包': {
        'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'lz', 'lzma', 'cab',
        'iso', 'dmg', 'pkg', 'deb', 'rpm', 'apk', 'ipa', 'jar', 'war', 'ear',
        'tgz', 'tbz2', 'zipx', 'z', 'arj', 'lzh', 'ace'
    },
    '代码': {
        'py', 'js', 'ts', 'java', 'c', 'cpp', 'h', 'hpp', 'cs', 'go', 'rs',
        'php', 'rb', 'swift', 'kt', 'scala', 'lua', 'pl', 'pm', 'sh', 'bash',
        'bat', 'cmd', 'ps1', 'vbs', 'r', 'sql', 'vue', 'jsx', 'tsx', 'dart',
        'groovy', 'asm', 's', 'f', 'f90', 'pas', 'bas', 'vb', 'cls', 'frm'
    },
    '网页': {
        'html', 'htm', 'css', 'xml', 'json', 'yaml', 'yml', 'xhtml', 'mhtml',
        'asp', 'aspx', 'jsp', 'php', 'erb', 'ejs', 'hbs', 'twig', 'blade'
    },
    '数据库': {
        'db', 'sqlite', 'sqlite3', 'mdb', 'accdb', 'dbf', 'sql', 'bak', 'mdf', 'ldf'
    },
    '字体': {
        'ttf', 'otf', 'woff', 'woff2', 'eot', 'fon', 'fnt'
    },
    '电子书': {
        'epub', 'mobi', 'azw', 'azw3', 'fb2', 'djvu', 'chm', 'lit'
    },
    '设计': {
        'psd', 'ai', 'sketch', 'fig', 'xd', 'indd', 'cdr', 'dwg', 'dxf'
    },
    '可执行': {
        'exe', 'msi', 'dll', 'sys', 'com', 'app', 'dmg', 'bin', 'run', 'so', 'dylib'
    },
    '配置': {
        'ini', 'cfg', 'conf', 'config', 'properties', 'env', 'htaccess', 'gitignore'
    },
}


def get_file_extension(filename):
    """获取文件扩展名（小写，不含点）"""
    if '.' in filename:
        return filename.rsplit('.', 1)[-1].lower()
    return "无后缀"


def get_file_category(ext):
    """根据扩展名获取文件分类"""
    for category, exts in FILE_CATEGORIES.items():
        if ext in exts:
            return category
    return "其他"


def scan_directory(root_dir):
    """递归扫描目录所有层级，返回统计数据"""
    total_files = 0
    total_size = 0
    dir_count = 0
    
    ext_stats = defaultdict(lambda: {'count': 0, 'size': 0})
    category_stats = defaultdict(lambda: {'count': 0, 'size': 0})
    folder_stats = defaultdict(lambda: {
        'count': 0,
        'size': 0,
        'categories': defaultdict(int)
    })
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dir_count += 1
        
        # 显示扫描进度
        if dir_count % 100 == 0:
            print(f"\r    已扫描 {dir_count} 个目录, {total_files} 个文件...", end="", flush=True)
        
        rel_path = os.path.relpath(dirpath, root_dir)
        
        if rel_path == '.':
            top_folder = "根目录文件"
        else:
            top_folder = rel_path.split(os.sep)[0]
        
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            
            try:
                file_size = os.path.getsize(filepath)
            except:
                file_size = 0
            
            ext = get_file_extension(filename)
            category = get_file_category(ext)
            
            total_files += 1
            total_size += file_size
            
            ext_stats[ext]['count'] += 1
            ext_stats[ext]['size'] += file_size
            
            category_stats[category]['count'] += 1
            category_stats[category]['size'] += file_size
            
            folder_stats[top_folder]['count'] += 1
            folder_stats[top_folder]['size'] += file_size
            folder_stats[top_folder]['categories'][category] += 1
    
    print(f"\r    完成! 共扫描 {dir_count} 个目录, {total_files} 个文件" + " " * 20)
    
    return {
        'total_files': total_files,
        'total_size': total_size,
        'ext_stats': ext_stats,
        'category_stats': category_stats,
        'folder_stats': folder_stats,
    }


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


def main():
    print("=" * 70)
    print(f"本地目录文件统计 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print(f"扫描目录: {len(SCAN_DIRS)} 个")
    for d in SCAN_DIRS:
        print(f"  - {d}")
    print("=" * 70)
    
    # 合并统计
    total_files = 0
    total_size = 0
    ext_stats = defaultdict(lambda: {'count': 0, 'size': 0})
    category_stats = defaultdict(lambda: {'count': 0, 'size': 0})
    folder_stats = defaultdict(lambda: {
        'count': 0,
        'size': 0,
        'categories': defaultdict(int)
    })
    
    for scan_dir in SCAN_DIRS:
        if not os.path.exists(scan_dir):
            print(f"警告: 目录不存在，跳过 - {scan_dir}")
            continue
        
        print(f"\n扫描中: {scan_dir} ...")
        result = scan_directory(scan_dir)
        
        total_files += result['total_files']
        total_size += result['total_size']
        
        for ext, stats in result['ext_stats'].items():
            ext_stats[ext]['count'] += stats['count']
            ext_stats[ext]['size'] += stats['size']
        
        for cat, stats in result['category_stats'].items():
            category_stats[cat]['count'] += stats['count']
            category_stats[cat]['size'] += stats['size']
        
        drive = os.path.splitdrive(scan_dir)[0]
        for folder, stats in result['folder_stats'].items():
            key = f"[{drive}] {folder}" if folder != "根目录文件" else f"[{drive}] {os.path.basename(scan_dir)}"
            folder_stats[key]['count'] += stats['count']
            folder_stats[key]['size'] += stats['size']
            for cat, cnt in stats['categories'].items():
                folder_stats[key]['categories'][cat] += cnt
    
    # 输出结果
    print("\n" + "=" * 70)
    print("总体统计")
    print("=" * 70)
    print(f"  文件总数:   {total_files}")
    print(f"  总大小:     {format_size(total_size)}")
    
    print("\n" + "=" * 70)
    print("按文件分类统计")
    print("=" * 70)
    print(f"  {'分类':<10} {'数量':>10} {'大小':>15}")
    print("-" * 70)
    
    sorted_categories = sorted(category_stats.items(), key=lambda x: -x[1]['count'])
    for cat, stats in sorted_categories:
        print(f"  {cat:<10} {stats['count']:>10} {format_size(stats['size']):>15}")
    
    print("\n" + "=" * 70)
    print("按文件扩展名统计（前20）")
    print("=" * 70)
    print(f"  {'扩展名':<12} {'数量':>10} {'大小':>15}")
    print("-" * 70)
    
    sorted_exts = sorted(ext_stats.items(), key=lambda x: -x[1]['count'])
    for ext, stats in sorted_exts[:20]:
        print(f"  .{ext:<11} {stats['count']:>10} {format_size(stats['size']):>15}")
    
    if len(sorted_exts) > 20:
        print(f"  ... 还有 {len(sorted_exts) - 20} 种其他类型")
    
    print("\n" + "=" * 70)
    print("按一级目录统计")
    print("=" * 70)
    
    sorted_folders = sorted(folder_stats.items(), key=lambda x: -x[1]['count'])
    
    for folder_name, stats in sorted_folders:
        cats = stats['categories']
        
        print(f"\n  【{folder_name}】")
        print(f"      文件数: {stats['count']}  大小: {format_size(stats['size'])}")
        
        cat_parts = []
        for cat in ['文本', 'PDF', '表格', 'PPT', '图片', '视频', '压缩包', '其他']:
            if cats.get(cat, 0) > 0:
                cat_parts.append(f"{cat}:{cats[cat]}")
        if cat_parts:
            print(f"      {', '.join(cat_parts)}")
    
    # 汇总
    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)
    print(f"  文件总数:   {total_files}")
    print(f"  文本:       {category_stats['文本']['count']}")
    print(f"  PDF:        {category_stats['PDF']['count']}")
    print(f"  表格:       {category_stats['表格']['count']}")
    print(f"  PPT:        {category_stats['PPT']['count']}")
    print(f"  图片:       {category_stats['图片']['count']}")
    print(f"  视频:       {category_stats['视频']['count']}")
    print(f"  音频:       {category_stats['音频']['count']}")
    print(f"  压缩包:     {category_stats['压缩包']['count']}")
    print(f"  电子书:     {category_stats['电子书']['count']}")
    print(f"  设计:       {category_stats['设计']['count']}")
    print(f"  代码:       {category_stats['代码']['count']}")
    print(f"  其他:       {category_stats['其他']['count']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
