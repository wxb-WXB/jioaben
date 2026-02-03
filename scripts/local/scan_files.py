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
- 支持多进程并行扫描多个目录
- 支持导出CSV表格

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
import csv
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from multiprocessing import Manager
import threading
import time

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
    r"F:\0-智能体资料汇总收集",
    r"F:\办公室档案知识库资料1",
    r"F:\办公室档案知识库资料2",
    r"F:\办公室档案知识库资料3",
    r" F:\01 知识库答案文本"
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

# 并行扫描的进程数（None表示自动使用CPU核心数）
PARALLEL_WORKERS = None

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

# 分类说明（包含的主要文件类型）
CATEGORY_DESCRIPTIONS = {
    '文本': 'doc/docx/txt/md/rtf/wps等',
    'PDF': 'pdf',
    '表格': 'xls/xlsx/csv/et/ods等',
    'PPT': 'ppt/pptx/dps/key等',
    '图片': 'jpg/png/gif/bmp/psd/svg等',
    '视频': 'mp4/avi/mkv/mov/wmv/flv等',
    '音频': 'mp3/wav/flac/aac/ogg/wma等',
    '压缩包': 'zip/rar/7z/tar/gz等',
    '电子书': 'epub/mobi/azw/chm/djvu等',
    '设计': 'psd/ai/sketch/fig/xd/indd/cdr/dwg/dxf',
    '代码': 'py/js/java/c/cpp/go/php等',
    '网页': 'html/css/xml/json/yaml等',
    '数据库': 'db/sqlite/mdb/sql等',
    '字体': 'ttf/otf/woff/woff2等',
    '可执行': 'exe/msi/dll/app/dmg等',
    '配置': 'ini/cfg/conf/config等',
    '其他': '未分类的其他文件类型',
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


def print_table(headers, rows, col_widths=None, logger=None):
    """
    打印格式化表格
    headers: 表头列表
    rows: 数据行列表（每行是一个列表）
    col_widths: 可选的列宽列表
    logger: 可选的日志记录器
    """
    if col_widths is None:
        # 自动计算列宽
        col_widths = []
        for i, h in enumerate(headers):
            max_width = len(str(h))
            for row in rows:
                if i < len(row):
                    # 处理中文字符宽度
                    cell = str(row[i])
                    cell_width = sum(2 if ord(c) > 127 else 1 for c in cell)
                    max_width = max(max_width, cell_width)
            col_widths.append(max_width + 2)
    
    def format_cell(text, width):
        """格式化单元格，处理中文对齐"""
        text = str(text)
        text_width = sum(2 if ord(c) > 127 else 1 for c in text)
        padding = width - text_width
        return text + " " * max(0, padding)
    
    def log_line(line):
        if logger:
            logger.log(line)
        else:
            print(line)
    
    # 打印表头分隔线
    separator = "+" + "+".join("-" * w for w in col_widths) + "+"
    log_line(separator)
    
    # 打印表头
    header_line = "|" + "|".join(format_cell(h, col_widths[i]) for i, h in enumerate(headers)) + "|"
    log_line(header_line)
    log_line(separator)
    
    # 打印数据行
    for row in rows:
        row_line = "|" + "|".join(format_cell(row[i] if i < len(row) else "", col_widths[i]) for i in range(len(headers))) + "|"
        log_line(row_line)
    
    log_line(separator)


def export_to_csv(filepath, headers, rows):
    """导出数据到CSV文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"CSV已导出到: {filepath}")


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


def scan_directory(root_dir, logger=None, extract_archives=True, progress_dict=None):
    """递归扫描目录所有层级，返回统计数据"""
    total_files = 0
    total_size = 0
    dir_count = 0
    archive_count = 0
    archive_files_count = 0
    archive_files_size = 0
    
    # 用于进度显示的目录名
    dir_name = os.path.basename(root_dir) or root_dir
    
    ext_stats = defaultdict(lambda: {'count': 0, 'size': 0, 'archive_count': 0, 'archive_size': 0})
    category_stats = defaultdict(lambda: {'count': 0, 'size': 0, 'archive_count': 0, 'archive_size': 0})
    folder_stats = defaultdict(lambda: {
        'count': 0,
        'size': 0,
        'categories': defaultdict(lambda: {'count': 0, 'size': 0}),
        'archive_files': 0
    })
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dir_count += 1
        
        # 更新共享进度（用于多进程）
        if progress_dict is not None:
            progress_dict[dir_name] = f"{dir_count} 目录, {total_files} 文件"
        
        # 显示扫描进度（仅在有logger时显示，单进程模式）
        if logger and dir_count % 100 == 0:
            logger.log(f"\r    [{dir_name}] 已扫描 {dir_count} 个目录, {total_files} 个文件...", end="", console_only=True)
        
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
            folder_stats[top_folder]['categories'][category]['count'] += 1
            folder_stats[top_folder]['categories'][category]['size'] += file_size
            
            # 如果是压缩文件且开启了解压统计
            if extract_archives and ext in SUPPORTED_ARCHIVES:
                archive_count += 1
                files_in_archive, size_in_archive = extract_and_scan_archive_silent(
                    filepath, ext_stats, category_stats
                )
                archive_files_count += files_in_archive
                archive_files_size += size_in_archive
                folder_stats[top_folder]['archive_files'] += files_in_archive
    
    # 标记完成
    if progress_dict is not None:
        progress_dict[dir_name] = f"✓ 完成: {dir_count} 目录, {total_files} 文件"
    
    if logger:
        logger.log(f"\r    [{dir_name}] 完成! 共扫描 {dir_count} 个目录, {total_files} 个文件" + " " * 20, console_only=True)
    
    # 将defaultdict转换为普通dict以便跨进程传递
    result = {
        'scan_dir': root_dir,
        'total_files': total_files,
        'total_size': total_size,
        'ext_stats': dict(ext_stats),
        'category_stats': dict(category_stats),
        'folder_stats': {k: {'count': v['count'], 'size': v['size'], 'categories': {ck: dict(cv) for ck, cv in v['categories'].items()}, 'archive_files': v['archive_files']} for k, v in folder_stats.items()},
        'archive_count': archive_count,
        'archive_files_count': archive_files_count,
        'archive_files_size': archive_files_size,
    }
    return result


def extract_and_scan_archive_silent(archive_path, ext_stats, category_stats):
    """
    解压压缩文件并统计其中的内容（静默版本，不输出日志）
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
            except:
                pass
                
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
            except:
                pass
    
    except:
        pass
    
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    return total_files, total_size


def scan_directory_worker(args):
    """多进程工作函数，包装scan_directory"""
    scan_dir, extract_archives, progress_dict = args
    if not os.path.exists(scan_dir):
        return None
    return scan_directory(scan_dir, logger=None, extract_archives=extract_archives, progress_dict=progress_dict)


def format_size(size_bytes):
    """格式化文件大小（支持到TB级别）"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes < 1024 * 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024 * 1024):.2f} TB"


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
        'categories': defaultdict(lambda: {'count': 0, 'size': 0}),
        'archive_files': 0
    })
    
    # 检查目录是否存在
    valid_dirs = []
    for scan_dir in SCAN_DIRS:
        if not os.path.exists(scan_dir):
            logger.log(f"警告: 目录不存在，跳过 - {scan_dir}")
        else:
            valid_dirs.append(scan_dir)
    
    if not valid_dirs:
        logger.log("错误: 没有有效的扫描目录!")
        return
    
    # 确定并行进程数
    num_workers = PARALLEL_WORKERS or min(len(valid_dirs), multiprocessing.cpu_count())
    logger.log(f"\n使用 {num_workers} 个进程并行扫描 {len(valid_dirs)} 个目录...")
    
    # 并行扫描所有目录
    results = []
    if len(valid_dirs) == 1:
        # 只有一个目录时，直接扫描（避免多进程开销）
        logger.log(f"\n扫描中: {valid_dirs[0]} ...")
        result = scan_directory(valid_dirs[0], logger, EXTRACT_ARCHIVES)
        if result:
            results.append(result)
    else:
        # 多个目录时，使用多进程并行扫描
        # 创建共享的进度字典
        manager = Manager()
        progress_dict = manager.dict()
        total_dirs = len(valid_dirs)
        
        # 进度显示标志
        stop_progress = threading.Event()
        
        def show_progress():
            """后台线程显示进度条"""
            bar_width = 30
            while not stop_progress.is_set():
                # 统计完成数量
                completed = sum(1 for s in progress_dict.values() if s.startswith("✓"))
                percent = completed / total_dirs * 100
                filled = int(bar_width * completed / total_dirs)
                bar = "█" * filled + "░" * (bar_width - filled)
                print(f"\r  扫描进度: [{bar}] {percent:5.1f}% ({completed}/{total_dirs})", end="", flush=True)
                time.sleep(0.3)
        
        # 启动进度显示线程
        progress_thread = threading.Thread(target=show_progress, daemon=True)
        progress_thread.start()
        
        try:
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                # 提交所有任务
                future_to_dir = {
                    executor.submit(scan_directory_worker, (scan_dir, EXTRACT_ARCHIVES, progress_dict)): scan_dir 
                    for scan_dir in valid_dirs
                }
                
                # 收集结果
                for future in as_completed(future_to_dir):
                    scan_dir = future_to_dir[future]
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.log(f"\n  ✗ 失败: {scan_dir} - {e}")
        finally:
            # 停止进度显示
            stop_progress.set()
            progress_thread.join(timeout=1)
            # 显示完成的进度条
            bar = "█" * 30
            print(f"\r  扫描进度: [{bar}] 100.0% ({total_dirs}/{total_dirs})")
        
        logger.log(f"  共扫描 {sum(r['total_files'] for r in results)} 个文件, {format_size(sum(r['total_size'] for r in results))}")
    
    # 合并所有结果
    logger.log(f"\n合并 {len(results)} 个目录的统计结果...")
    for result in results:
        scan_dir = result['scan_dir']
        
        total_files += result['total_files']
        total_size += result['total_size']
        total_archive_count += result['archive_count']
        total_archive_files += result['archive_files_count']
        total_archive_size += result['archive_files_size']
        
        for ext, stats in result['ext_stats'].items():
            ext_stats[ext]['count'] += stats['count']
            ext_stats[ext]['size'] += stats['size']
            ext_stats[ext]['archive_count'] += stats.get('archive_count', 0)
            ext_stats[ext]['archive_size'] += stats.get('archive_size', 0)
        
        for cat, stats in result['category_stats'].items():
            category_stats[cat]['count'] += stats['count']
            category_stats[cat]['size'] += stats['size']
            category_stats[cat]['archive_count'] += stats.get('archive_count', 0)
            category_stats[cat]['archive_size'] += stats.get('archive_size', 0)
        
        drive = os.path.splitdrive(scan_dir)[0]
        for folder, stats in result['folder_stats'].items():
            key = f"[{drive}] {folder}" if folder != "根目录文件" else f"[{drive}] {os.path.basename(scan_dir)}"
            folder_stats[key]['count'] += stats['count']
            folder_stats[key]['size'] += stats['size']
            folder_stats[key]['archive_files'] += stats['archive_files']
            for cat, cat_stats in stats['categories'].items():
                folder_stats[key]['categories'][cat]['count'] += cat_stats['count']
                folder_stats[key]['categories'][cat]['size'] += cat_stats['size']
    
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
    
    # ============================================================
    # 表格输出 - 按文件分类统计
    # ============================================================
    logger.log("\n" + "=" * 80)
    logger.log("📊 按文件分类统计（表格）")
    logger.log("=" * 80)
    
    sorted_categories = sorted(category_stats.items(), key=lambda x: -(x[1]['count'] + x[1]['archive_count']))
    
    if EXTRACT_ARCHIVES:
        cat_headers = ["分类", "包含的文件类型", "直接数量", "直接大小", "压缩包内数量", "压缩包内大小", "合计数量", "合计大小"]
        cat_rows = []
        for cat, stats in sorted_categories:
            total_count = stats['count'] + stats['archive_count']
            total_cat_size = stats['size'] + stats['archive_size']
            desc = CATEGORY_DESCRIPTIONS.get(cat, "")
            cat_rows.append([
                cat,
                desc,
                stats['count'],
                format_size(stats['size']),
                stats['archive_count'],
                format_size(stats['archive_size']),
                total_count,
                format_size(total_cat_size)
            ])
        # 添加汇总行
        cat_rows.append([
            "【合计】",
            "-",
            total_files,
            format_size(total_size),
            total_archive_files,
            format_size(total_archive_size),
            total_files + total_archive_files,
            format_size(total_size + total_archive_size)
        ])
    else:
        cat_headers = ["分类", "包含的文件类型", "数量", "大小", "占比"]
        cat_rows = []
        for cat, stats in sorted_categories:
            percent = f"{stats['count'] / total_files * 100:.1f}%" if total_files > 0 else "0%"
            desc = CATEGORY_DESCRIPTIONS.get(cat, "")
            cat_rows.append([cat, desc, stats['count'], format_size(stats['size']), percent])
        cat_rows.append(["【合计】", "-", total_files, format_size(total_size), "100%"])
    
    print_table(cat_headers, cat_rows, logger=logger)
    
    # ============================================================
    # 表格输出 - 按一级目录统计
    # ============================================================
    logger.log("\n" + "=" * 80)
    logger.log("📊 按一级目录统计（表格）")
    logger.log("=" * 80)
    
    sorted_folders = sorted(folder_stats.items(), key=lambda x: -x[1]['count'])
    
    # 定义所有分类列（包含音频和视频）
    all_categories = ['文本', 'PDF', '表格', 'PPT', '图片', '视频', '音频', '压缩包', '电子书', '设计', '代码', '网页', '数据库', '字体', '可执行', '配置', '其他']
    
    # ============================================================
    # 表格1：按分类汇总统计（所有目录加起来的总数）
    # ============================================================
    logger.log("\n【汇总统计 - 所有目录合计】")
    
    summary_headers = ["分类", "包含的文件类型", "文件数量", "文件大小", "占比(数量)", "占比(大小)"]
    summary_rows = []
    
    for cat in all_categories:
        cat_total_count = 0
        cat_total_size = 0
        for folder_name, stats in folder_stats.items():
            cat_data = stats['categories'].get(cat, {'count': 0, 'size': 0})
            cat_total_count += cat_data['count']
            cat_total_size += cat_data['size']
        
        if cat_total_count > 0:
            count_percent = f"{cat_total_count / total_files * 100:.1f}%" if total_files > 0 else "0%"
            size_percent = f"{cat_total_size / total_size * 100:.1f}%" if total_size > 0 else "0%"
            desc = CATEGORY_DESCRIPTIONS.get(cat, "")
            summary_rows.append([cat, desc, cat_total_count, format_size(cat_total_size), count_percent, size_percent])
    
    # 添加合计行
    summary_rows.append(["【合计】", "-", total_files, format_size(total_size), "100%", "100%"])
    
    print_table(summary_headers, summary_rows, logger=logger)
    
    # ============================================================
    # 表格2：按目录分类统计（每个目录的详细统计）
    # ============================================================
    logger.log("\n【分目录统计 - 各目录详情】")
    
    # 先输出分类说明
    logger.log("\n  📋 分类说明:")
    for cat in all_categories:
        desc = CATEGORY_DESCRIPTIONS.get(cat, "")
        logger.log(f"     {cat}: {desc}")
    logger.log("")
    
    # 构建表头：每个分类有数量和大小两列
    folder_headers = ["目录", "总文件数", "总大小"]
    if EXTRACT_ARCHIVES:
        folder_headers.append("压缩包内")
    
    for cat in all_categories:
        folder_headers.append(f"{cat}(数量)")
        folder_headers.append(f"{cat}(大小)")
    
    folder_rows = []
    for folder_name, stats in sorted_folders:
        cats = stats['categories']
        
        row = [folder_name, stats['count'], format_size(stats['size'])]
        if EXTRACT_ARCHIVES:
            row.append(stats['archive_files'])
        
        # 添加每个分类的数量和大小
        for cat in all_categories:
            cat_data = cats.get(cat, {'count': 0, 'size': 0})
            count = cat_data['count'] if cat_data['count'] > 0 else ""
            size = format_size(cat_data['size']) if cat_data['size'] > 0 else ""
            row.append(count)
            row.append(size)
        
        folder_rows.append(row)
    
    # 添加汇总行
    total_row = ["【合计】", total_files, format_size(total_size)]
    if EXTRACT_ARCHIVES:
        total_row.append(total_archive_files)
    for cat in all_categories:
        cat_total_count = 0
        cat_total_size = 0
        for folder_name, stats in folder_stats.items():
            cat_data = stats['categories'].get(cat, {'count': 0, 'size': 0})
            cat_total_count += cat_data['count']
            cat_total_size += cat_data['size']
        total_row.append(cat_total_count if cat_total_count > 0 else "")
        total_row.append(format_size(cat_total_size) if cat_total_size > 0 else "")
    folder_rows.append(total_row)
    
    print_table(folder_headers, folder_rows, logger=logger)
    
    # ============================================================
    # 表格3：全部文件扩展名统计（包括所有类型）
    # ============================================================
    logger.log("\n" + "=" * 80)
    logger.log("📊 全部文件扩展名统计（表格3 - 所有类型）")
    logger.log("=" * 80)
    
    sorted_exts = sorted(ext_stats.items(), key=lambda x: -(x[1]['count'] + x[1].get('archive_count', 0)))
    
    if EXTRACT_ARCHIVES:
        all_ext_headers = ["扩展名", "所属分类", "直接数量", "直接大小", "压缩包内数量", "压缩包内大小", "合计数量", "合计大小", "占比"]
        all_ext_rows = []
        grand_total_count = total_files + total_archive_files
        for ext, stats in sorted_exts:
            total_count = stats['count'] + stats.get('archive_count', 0)
            total_ext_size = stats['size'] + stats.get('archive_size', 0)
            percent = f"{total_count / grand_total_count * 100:.2f}%" if grand_total_count > 0 else "0%"
            all_ext_rows.append([
                f".{ext}",
                get_file_category(ext),
                stats['count'],
                format_size(stats['size']),
                stats.get('archive_count', 0),
                format_size(stats.get('archive_size', 0)),
                total_count,
                format_size(total_ext_size),
                percent
            ])
        # 添加合计行
        all_ext_rows.append([
            "【合计】", "-",
            total_files, format_size(total_size),
            total_archive_files, format_size(total_archive_size),
            grand_total_count, format_size(total_size + total_archive_size),
            "100%"
        ])
    else:
        all_ext_headers = ["扩展名", "所属分类", "数量", "大小", "占比(数量)", "占比(大小)"]
        all_ext_rows = []
        for ext, stats in sorted_exts:
            count_percent = f"{stats['count'] / total_files * 100:.2f}%" if total_files > 0 else "0%"
            size_percent = f"{stats['size'] / total_size * 100:.2f}%" if total_size > 0 else "0%"
            all_ext_rows.append([
                f".{ext}",
                get_file_category(ext),
                stats['count'],
                format_size(stats['size']),
                count_percent,
                size_percent
            ])
        all_ext_rows.append(["【合计】", "-", total_files, format_size(total_size), "100%", "100%"])
    
    print_table(all_ext_headers, all_ext_rows, logger=logger)
    logger.log(f"  共 {len(sorted_exts)} 种不同的文件扩展名")
    
    # ============================================================
    # 导出CSV文件
    # ============================================================
    csv_base = os.path.join(LOG_DIR, f"scan_stats_{timestamp}")
    
    # 导出分类统计CSV
    csv_category_file = f"{csv_base}_分类统计.csv"
    export_to_csv(csv_category_file, cat_headers, cat_rows)
    
    # 导出扩展名统计CSV（全部类型）
    csv_ext_file = f"{csv_base}_扩展名统计.csv"
    export_to_csv(csv_ext_file, all_ext_headers, all_ext_rows)
    
    # 导出目录统计CSV
    csv_folder_file = f"{csv_base}_目录统计.csv"
    export_to_csv(csv_folder_file, folder_headers, folder_rows)
    
    # 导出汇总CSV（包含所有统计信息在一个文件中）
    csv_summary_file = f"{csv_base}_汇总.csv"
    with open(csv_summary_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        
        # 总体统计
        writer.writerow(["=== 总体统计 ==="])
        writer.writerow(["项目", "数值"])
        writer.writerow(["文件总数", total_files])
        writer.writerow(["文件总大小", format_size(total_size)])
        if EXTRACT_ARCHIVES:
            writer.writerow(["压缩包数量", total_archive_count])
            writer.writerow(["压缩包内文件数", total_archive_files])
            writer.writerow(["压缩包内文件大小", format_size(total_archive_size)])
            writer.writerow(["合计文件数", total_files + total_archive_files])
            writer.writerow(["合计文件大小", format_size(total_size + total_archive_size)])
        writer.writerow([])
        
        # 分类统计
        writer.writerow(["=== 按分类统计 ==="])
        writer.writerow(cat_headers)
        writer.writerows(cat_rows)
        writer.writerow([])
        
        # 扩展名统计（全部类型）
        writer.writerow(["=== 按扩展名统计（全部类型） ==="])
        writer.writerow(all_ext_headers)
        writer.writerows(all_ext_rows)
        writer.writerow([])
        
        # 目录统计
        writer.writerow(["=== 按目录统计 ==="])
        writer.writerow(folder_headers)
        writer.writerows(folder_rows)
    
    print(f"汇总CSV已导出到: {csv_summary_file}")
    
    # ============================================================
    # 最终汇总（保留原有格式）
    # ============================================================
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
    
    # 输出导出文件列表
    logger.log("\n📁 导出文件列表:")
    logger.log(f"  - 分类统计: {csv_category_file}")
    logger.log(f"  - 扩展名统计: {csv_ext_file}")
    logger.log(f"  - 目录统计: {csv_folder_file}")
    logger.log(f"  - 汇总文件: {csv_summary_file}")
    
    # 保存日志
    logger.save()


if __name__ == "__main__":
    main()
