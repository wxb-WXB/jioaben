# -*- coding: utf-8 -*-
"""
本地目录文件统计脚本

功能：
- 递归扫描指定本地目录的所有层级
- 解压压缩文件并统计其中的内容
- 按文件类型（后缀名）分类统计（数量和大小）
- 按一级目录分类统计
- 支持所有文件类型：文档、图片、视频、压缩包等
- 输出详细日志文件

使用方法：
1. 修改下方 SCAN_DIRS 配置要扫描的目录
2. 运行脚本: python scripts/local/scan_files.py
"""
import os
import sys
import zipfile
import tarfile
import tempfile
import shutil
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

# 方式2：使用配置文件中的目录（取消上面的注释后，下面这行生效）
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

# 是否解压压缩文件进行统计（可能会比较慢）
EXTRACT_ARCHIVES = True

# 日志输出目录
LOG_DIR = os.path.join(project_root, "logs")

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

# 支持解压的格式
SUPPORTED_ARCHIVES = {'zip', 'tar', 'gz', 'tgz', 'bz2', 'tbz2', 'xz'}


class Logger:
    """日志记录器，同时输出到控制台和文件"""
    
    def __init__(self, log_file):
        self.log_file = log_file
        self.lines = []
        
    def log(self, message="", end="\n", console_only=False):
        """记录日志"""
        print(message, end=end, flush=True)
        if not console_only:
            self.lines.append(message + (end if end != "\r" else "\n"))
    
    def save(self):
        """保存日志到文件"""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.writelines(self.lines)
        print(f"\n日志已保存到: {self.log_file}")


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


def extract_and_scan_archive(archive_path, ext_stats, category_stats, logger):
    """
    解压压缩文件并统计其中的内容
    返回: (文件数, 总大小)
    """
    total_files = 0
    total_size = 0
    ext = get_file_extension(archive_path)
    
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="scan_archive_")
        
        # 根据格式解压
        if ext == 'zip':
            try:
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    # 直接从zip信息中获取，不需要实际解压
                    for info in zf.infolist():
                        if not info.is_dir():
                            filename = os.path.basename(info.filename)
                            file_ext = get_file_extension(filename)
                            file_category = get_file_category(file_ext)
                            file_size = info.file_size
                            
                            total_files += 1
                            total_size += file_size
                            
                            ext_stats[file_ext]['count'] += 1
                            ext_stats[file_ext]['size'] += file_size
                            ext_stats[file_ext]['archive_count'] += 1
                            ext_stats[file_ext]['archive_size'] += file_size
                            
                            category_stats[file_category]['count'] += 1
                            category_stats[file_category]['size'] += file_size
                            category_stats[file_category]['archive_count'] += 1
                            category_stats[file_category]['archive_size'] += file_size
            except (zipfile.BadZipFile, Exception) as e:
                logger.log(f"      [警告] 无法读取zip文件: {archive_path} - {e}", console_only=True)
                
        elif ext in ('tar', 'gz', 'tgz', 'bz2', 'tbz2', 'xz'):
            try:
                mode = 'r'
                if ext in ('gz', 'tgz'):
                    mode = 'r:gz'
                elif ext in ('bz2', 'tbz2'):
                    mode = 'r:bz2'
                elif ext == 'xz':
                    mode = 'r:xz'
                
                with tarfile.open(archive_path, mode) as tf:
                    for member in tf.getmembers():
                        if member.isfile():
                            filename = os.path.basename(member.name)
                            file_ext = get_file_extension(filename)
                            file_category = get_file_category(file_ext)
                            file_size = member.size
                            
                            total_files += 1
                            total_size += file_size
                            
                            ext_stats[file_ext]['count'] += 1
                            ext_stats[file_ext]['size'] += file_size
                            ext_stats[file_ext]['archive_count'] += 1
                            ext_stats[file_ext]['archive_size'] += file_size
                            
                            category_stats[file_category]['count'] += 1
                            category_stats[file_category]['size'] += file_size
                            category_stats[file_category]['archive_count'] += 1
                            category_stats[file_category]['archive_size'] += file_size
            except (tarfile.TarError, Exception) as e:
                logger.log(f"      [警告] 无法读取tar文件: {archive_path} - {e}", console_only=True)
    
    except Exception as e:
        logger.log(f"      [警告] 解压失败: {archive_path} - {e}", console_only=True)
    
    finally:
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    return total_files, total_size


def scan_directory(root_dir, logger, extract_archives=True):
    """递归扫描目录所有层级，返回统计数据"""
    total_files = 0
    total_size = 0
    dir_count = 0
    archive_count = 0
    archive_files_count = 0
    archive_files_size = 0
    
    ext_stats = defaultdict(lambda: {'count': 0, 'size': 0, 'archive_count': 0, 'archive_size': 0})
    category_stats = defaultdict(lambda: {'count': 0, 'size': 0, 'archive_count': 0, 'archive_size': 0})
    folder_stats = defaultdict(lambda: {
        'count': 0,
        'size': 0,
        'categories': defaultdict(int),
        'archive_files': 0
    })
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dir_count += 1
        
        # 显示扫描进度
        if dir_count % 100 == 0:
            logger.log(f"\r    已扫描 {dir_count} 个目录, {total_files} 个文件...", end="", console_only=True)
        
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
            
            # 如果是压缩文件且开启了解压统计
            if extract_archives and ext in SUPPORTED_ARCHIVES:
                archive_count += 1
                files_in_archive, size_in_archive = extract_and_scan_archive(
                    filepath, ext_stats, category_stats, logger
                )
                archive_files_count += files_in_archive
                archive_files_size += size_in_archive
                folder_stats[top_folder]['archive_files'] += files_in_archive
    
    logger.log(f"\r    完成! 共扫描 {dir_count} 个目录, {total_files} 个文件" + " " * 20, console_only=True)
    
    return {
        'total_files': total_files,
        'total_size': total_size,
        'ext_stats': ext_stats,
        'category_stats': category_stats,
        'folder_stats': folder_stats,
        'archive_count': archive_count,
        'archive_files_count': archive_files_count,
        'archive_files_size': archive_files_size,
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
    # 初始化日志
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    log_file = os.path.join(LOG_DIR, f"scan_files_{timestamp}.log")
    logger = Logger(log_file)
    
    logger.log("=" * 80)
    logger.log(f"本地目录文件统计 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.log("=" * 80)
    logger.log(f"扫描目录: {len(SCAN_DIRS)} 个")
    for d in SCAN_DIRS:
        logger.log(f"  - {d}")
    logger.log(f"解压压缩文件统计: {'是' if EXTRACT_ARCHIVES else '否'}")
    logger.log("=" * 80)
    
    # 合并统计
    total_files = 0
    total_size = 0
    total_archive_count = 0
    total_archive_files = 0
    total_archive_size = 0
    
    ext_stats = defaultdict(lambda: {'count': 0, 'size': 0, 'archive_count': 0, 'archive_size': 0})
    category_stats = defaultdict(lambda: {'count': 0, 'size': 0, 'archive_count': 0, 'archive_size': 0})
    folder_stats = defaultdict(lambda: {
        'count': 0,
        'size': 0,
        'categories': defaultdict(int),
        'archive_files': 0
    })
    
    for scan_dir in SCAN_DIRS:
        if not os.path.exists(scan_dir):
            logger.log(f"警告: 目录不存在，跳过 - {scan_dir}")
            continue
        
        logger.log(f"\n扫描中: {scan_dir} ...")
        result = scan_directory(scan_dir, logger, EXTRACT_ARCHIVES)
        
        total_files += result['total_files']
        total_size += result['total_size']
        total_archive_count += result['archive_count']
        total_archive_files += result['archive_files_count']
        total_archive_size += result['archive_files_size']
        
        for ext, stats in result['ext_stats'].items():
            ext_stats[ext]['count'] += stats['count']
            ext_stats[ext]['size'] += stats['size']
            ext_stats[ext]['archive_count'] += stats['archive_count']
            ext_stats[ext]['archive_size'] += stats['archive_size']
        
        for cat, stats in result['category_stats'].items():
            category_stats[cat]['count'] += stats['count']
            category_stats[cat]['size'] += stats['size']
            category_stats[cat]['archive_count'] += stats['archive_count']
            category_stats[cat]['archive_size'] += stats['archive_size']
        
        drive = os.path.splitdrive(scan_dir)[0]
        for folder, stats in result['folder_stats'].items():
            key = f"[{drive}] {folder}" if folder != "根目录文件" else f"[{drive}] {os.path.basename(scan_dir)}"
            folder_stats[key]['count'] += stats['count']
            folder_stats[key]['size'] += stats['size']
            folder_stats[key]['archive_files'] += stats['archive_files']
            for cat, cnt in stats['categories'].items():
                folder_stats[key]['categories'][cat] += cnt
    
    # 输出结果
    logger.log("\n" + "=" * 80)
    logger.log("总体统计")
    logger.log("=" * 80)
    logger.log(f"  文件总数:         {total_files}")
    logger.log(f"  文件总大小:       {format_size(total_size)}")
    if EXTRACT_ARCHIVES:
        logger.log(f"  压缩包数量:       {total_archive_count}")
        logger.log(f"  压缩包内文件数:   {total_archive_files}")
        logger.log(f"  压缩包内文件大小: {format_size(total_archive_size)}")
        logger.log(f"  合计文件数:       {total_files + total_archive_files} (含压缩包内文件)")
        logger.log(f"  合计文件大小:     {format_size(total_size + total_archive_size)} (含压缩包内文件)")
    
    # 按文件分类统计
    logger.log("\n" + "=" * 80)
    logger.log("按文件分类统计")
    logger.log("=" * 80)
    if EXTRACT_ARCHIVES:
        logger.log(f"  {'分类':<10} {'直接数量':>10} {'直接大小':>15} {'压缩包内':>10} {'压缩包大小':>15} {'合计数量':>10}")
        logger.log("-" * 80)
    else:
        logger.log(f"  {'分类':<10} {'数量':>10} {'大小':>15}")
        logger.log("-" * 80)
    
    sorted_categories = sorted(category_stats.items(), key=lambda x: -(x[1]['count'] + x[1]['archive_count']))
    for cat, stats in sorted_categories:
        if EXTRACT_ARCHIVES:
            total_count = stats['count'] + stats['archive_count']
            logger.log(f"  {cat:<10} {stats['count']:>10} {format_size(stats['size']):>15} {stats['archive_count']:>10} {format_size(stats['archive_size']):>15} {total_count:>10}")
        else:
            logger.log(f"  {cat:<10} {stats['count']:>10} {format_size(stats['size']):>15}")
    
    # 按文件扩展名统计
    logger.log("\n" + "=" * 80)
    logger.log("按文件扩展名统计（前30）")
    logger.log("=" * 80)
    if EXTRACT_ARCHIVES:
        logger.log(f"  {'扩展名':<12} {'直接数量':>10} {'直接大小':>15} {'压缩包内':>10} {'压缩包大小':>15} {'合计':>10}")
        logger.log("-" * 80)
    else:
        logger.log(f"  {'扩展名':<12} {'数量':>10} {'大小':>15}")
        logger.log("-" * 80)
    
    sorted_exts = sorted(ext_stats.items(), key=lambda x: -(x[1]['count'] + x[1]['archive_count']))
    for ext, stats in sorted_exts[:30]:
        if EXTRACT_ARCHIVES:
            total_count = stats['count'] + stats['archive_count']
            logger.log(f"  .{ext:<11} {stats['count']:>10} {format_size(stats['size']):>15} {stats['archive_count']:>10} {format_size(stats['archive_size']):>15} {total_count:>10}")
        else:
            logger.log(f"  .{ext:<11} {stats['count']:>10} {format_size(stats['size']):>15}")
    
    if len(sorted_exts) > 30:
        logger.log(f"  ... 还有 {len(sorted_exts) - 30} 种其他类型")
    
    # 完整扩展名列表
    logger.log("\n" + "=" * 80)
    logger.log("完整扩展名列表（按数量排序）")
    logger.log("=" * 80)
    for ext, stats in sorted_exts:
        total_count = stats['count'] + stats['archive_count']
        total_ext_size = stats['size'] + stats['archive_size']
        if EXTRACT_ARCHIVES and stats['archive_count'] > 0:
            logger.log(f"  .{ext:<15} 数量: {total_count:>8} (直接:{stats['count']}, 压缩包内:{stats['archive_count']})  大小: {format_size(total_ext_size)}")
        else:
            logger.log(f"  .{ext:<15} 数量: {stats['count']:>8}  大小: {format_size(stats['size'])}")
    
    # 按一级目录统计
    logger.log("\n" + "=" * 80)
    logger.log("按一级目录统计")
    logger.log("=" * 80)
    
    sorted_folders = sorted(folder_stats.items(), key=lambda x: -x[1]['count'])
    
    for folder_name, stats in sorted_folders:
        cats = stats['categories']
        
        logger.log(f"\n  【{folder_name}】")
        if EXTRACT_ARCHIVES and stats['archive_files'] > 0:
            logger.log(f"      文件数: {stats['count']}  大小: {format_size(stats['size'])}  压缩包内文件: {stats['archive_files']}")
        else:
            logger.log(f"      文件数: {stats['count']}  大小: {format_size(stats['size'])}")
        
        cat_parts = []
        for cat in ['文本', 'PDF', '表格', 'PPT', '图片', '视频', '音频', '压缩包', '代码', '电子书', '设计', '其他']:
            if cats.get(cat, 0) > 0:
                cat_parts.append(f"{cat}:{cats[cat]}")
        if cat_parts:
            logger.log(f"      {', '.join(cat_parts)}")
    
    # 最终汇总
    logger.log("\n" + "=" * 80)
    logger.log("最终汇总")
    logger.log("=" * 80)
    
    logger.log("\n  【直接文件统计】")
    logger.log(f"    文件总数:     {total_files}")
    logger.log(f"    文件总大小:   {format_size(total_size)}")
    
    logger.log("\n  【按分类统计 - 直接文件】")
    for cat in ['文本', 'PDF', '表格', 'PPT', '图片', '视频', '音频', '压缩包', '电子书', '设计', '代码', '其他']:
        count = category_stats[cat]['count']
        size = category_stats[cat]['size']
        if count > 0:
            logger.log(f"    {cat:<10} 数量: {count:>8}  大小: {format_size(size)}")
    
    if EXTRACT_ARCHIVES:
        logger.log("\n  【压缩包内文件统计】")
        logger.log(f"    压缩包数量:       {total_archive_count}")
        logger.log(f"    压缩包内文件数:   {total_archive_files}")
        logger.log(f"    压缩包内文件大小: {format_size(total_archive_size)}")
        
        logger.log("\n  【按分类统计 - 压缩包内文件】")
        for cat in ['文本', 'PDF', '表格', 'PPT', '图片', '视频', '音频', '压缩包', '电子书', '设计', '代码', '其他']:
            count = category_stats[cat]['archive_count']
            size = category_stats[cat]['archive_size']
            if count > 0:
                logger.log(f"    {cat:<10} 数量: {count:>8}  大小: {format_size(size)}")
        
        logger.log("\n  【总计（直接文件 + 压缩包内文件）】")
        grand_total_files = total_files + total_archive_files
        grand_total_size = total_size + total_archive_size
        logger.log(f"    文件总数:     {grand_total_files}")
        logger.log(f"    文件总大小:   {format_size(grand_total_size)}")
        
        logger.log("\n  【按分类统计 - 总计】")
        for cat in ['文本', 'PDF', '表格', 'PPT', '图片', '视频', '音频', '压缩包', '电子书', '设计', '代码', '其他']:
            count = category_stats[cat]['count'] + category_stats[cat]['archive_count']
            size = category_stats[cat]['size'] + category_stats[cat]['archive_size']
            if count > 0:
                logger.log(f"    {cat:<10} 数量: {count:>8}  大小: {format_size(size)}")
    
    logger.log("\n" + "=" * 80)
    logger.log(f"扫描完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.log("=" * 80)
    
    # 保存日志
    logger.save()


if __name__ == "__main__":
    main()
