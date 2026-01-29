# -*- coding: utf-8 -*-
"""
统计灵燕知识库中的0字节文件

功能：
- 扫描灵燕知识库中的所有文档
- 检查文档的 file_size 字段
- 找出所有0字节文件并输出路径
- 输出总数统计

使用方法：
    python scripts/local/check_zero_files.py
"""
import os
import sys
import logging
from datetime import datetime

# 设置控制台编码
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from src.core import LingyanDataset
from src.core.models import FolderMap
from src.config import API_KEY, WORKSPACE_ID, WORKSPACE_NAME, LOGS_DIR

# 日志文件路径
LOG_FILE = os.path.join(LOGS_DIR, f"zero_files_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# 初始化API
dataset_api = LingyanDataset(API_KEY)


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


def scan_zero_files(workspace_id, workspace_name):
    """扫描知识库，找出0字节文件"""
    log.info(f"正在扫描 [{workspace_name}] 的知识库...")
    
    status, datasets = dataset_api.list_datasets(workspace_id)
    
    if status != 200:
        log.error(f"获取知识库列表失败: {datasets}")
        return [], 0, 0
    
    log.info(f"找到 {len(datasets)} 个知识库")
    log.info("=" * 60)
    
    zero_files = []
    total_docs = 0
    total_datasets = len(datasets)
    
    for i, ds in enumerate(datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        log.info(f"[{i+1}/{total_datasets}] 扫描知识库: {dataset_name}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id)
            if status != 200:
                log.error(f"  获取文档失败")
                continue
            
            ds_zero_count = 0
            
            for doc in documents:
                total_docs += 1
                file_size = doc.get("file_size", -1)
                doc_name = doc.get("name", "")
                doc_id = doc.get("id", "")
                
                if file_size == 0:
                    ds_zero_count += 1
                    zero_files.append({
                        "dataset_name": dataset_name,
                        "dataset_id": dataset_id,
                        "folder_path": folder_path,
                        "document_name": doc_name,
                        "document_id": doc_id,
                        "file_size": file_size,
                    })
            
            if ds_zero_count > 0:
                log.info(f"  文档数: {len(documents)}, 0字节文件: {ds_zero_count}")
            else:
                log.info(f"  文档数: {len(documents)}, 无0字节文件")
                
        except Exception as e:
            log.error(f"  出错: {e}")
    
    return zero_files, total_docs, total_datasets


def save_log(zero_files, total_docs, total_datasets):
    """保存日志"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"0字节文件统计报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"工作空间：{WORKSPACE_NAME}\n")
        f.write(f"工作空间ID：{WORKSPACE_ID}\n")
        f.write("\n")
        
        f.write(f"总知识库数：{total_datasets}\n")
        f.write(f"总文档数：{total_docs}\n")
        f.write(f"0字节文件数：{len(zero_files)}\n")
        f.write("\n")
        
        if zero_files:
            f.write("=" * 80 + "\n")
            f.write("0字节文件列表\n")
            f.write("=" * 80 + "\n\n")
            
            for i, file_info in enumerate(zero_files, 1):
                f.write(f"{i}. {file_info['folder_path']}/{file_info['document_name']}\n")
                f.write(f"   知识库: {file_info['dataset_name']}\n")
                f.write(f"   文档ID: {file_info['document_id']}\n")
                f.write("\n")
        
        f.write("=" * 80 + "\n")
        f.write(f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n")
    
    log.info(f"日志已保存到：{LOG_FILE}")


def main():
    log.info("=" * 60)
    log.info("0字节文件统计工具（灵燕知识库）")
    log.info("=" * 60)
    log.info(f"工作空间：{WORKSPACE_NAME}")
    log.info(f"工作空间ID：{WORKSPACE_ID}")
    log.info("-" * 60)
    
    # 扫描0字节文件
    zero_files, total_docs, total_datasets = scan_zero_files(WORKSPACE_ID, WORKSPACE_NAME)
    
    # 输出结果
    log.info("")
    log.info("=" * 60)
    log.info("统计结果")
    log.info("=" * 60)
    log.info(f"  总知识库数：    {total_datasets}")
    log.info(f"  总文档数：      {total_docs}")
    log.info(f"  0字节文件数：   {len(zero_files)}")
    
    if zero_files:
        log.info("")
        log.info("-" * 60)
        log.info("0字节文件列表：")
        log.info("-" * 60)
        # 控制台只显示前20个
        for i, file_info in enumerate(zero_files[:20], 1):
            log.info(f"  {i}. [{file_info['dataset_name']}] {file_info['document_name']}")
        if len(zero_files) > 20:
            log.info(f"  ... 还有 {len(zero_files) - 20} 个，详见日志文件")
    else:
        log.info("")
        log.info("没有发现0字节文件。")
    
    # 保存日志
    save_log(zero_files, total_docs, total_datasets)
    
    log.info("")
    log.info("=" * 60)
    log.info("完成！")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
