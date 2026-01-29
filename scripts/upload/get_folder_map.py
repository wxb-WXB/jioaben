# -*- coding: utf-8 -*-
"""
获取目录映射脚本

功能：
- 从灵燕平台获取所有文件夹的ID和路径信息
- 保存到本地 folder.db 数据库
- 用于上传时根据本地路径找到对应的远程目录ID

使用方法：
python scripts/upload/get_folder_map.py

注意：
- 首次使用上传功能前需要先运行此脚本
- 如果平台上新建了文件夹，需要重新运行此脚本更新映射
"""
import sys
import os
import requests
import logging
from datetime import datetime

# 设置控制台编码
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core.models import FolderMap, db
from src.config import API_KEY, API_HOST, WORKSPACES

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)


def get_folders(workspace_id: str, parent_id: str = None) -> list:
    """
    递归获取所有文件夹
    
    Args:
        workspace_id: 工作空间ID
        parent_id: 父文件夹ID（None表示根目录）
        
    Returns:
        list: 文件夹列表
    """
    url = f"{API_HOST}/api/v1/service/folders"
    
    params = {
        "workspace_id": workspace_id,
        "page_size": 1000,
    }
    if parent_id:
        params["parent_id"] = parent_id
    
    headers = {
        "accept": "application/json",
        "X-API-Key": API_KEY,
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=60)
        if response.status_code == 200:
            data = response.json().get("data", [])
            return data if isinstance(data, list) else []
        else:
            log.error(f"获取文件夹列表失败: {response.status_code}")
            return []
    except Exception as e:
        log.error(f"请求失败: {e}")
        return []


def build_folder_path(folder: dict, all_folders: dict) -> str:
    """
    构建文件夹的完整路径
    
    Args:
        folder: 文件夹信息
        all_folders: 所有文件夹的字典 {id: folder}
        
    Returns:
        str: 完整路径
    """
    path_parts = [folder.get("name", "")]
    parent_id = folder.get("parent_id")
    
    while parent_id and parent_id in all_folders:
        parent = all_folders[parent_id]
        path_parts.insert(0, parent.get("name", ""))
        parent_id = parent.get("parent_id")
    
    return "/".join(path_parts)


def scan_folders_recursive(workspace_id: str, parent_id: str = None, all_folders: dict = None) -> dict:
    """
    递归扫描所有文件夹
    
    Args:
        workspace_id: 工作空间ID
        parent_id: 父文件夹ID
        all_folders: 累积的文件夹字典
        
    Returns:
        dict: 所有文件夹的字典 {id: folder}
    """
    if all_folders is None:
        all_folders = {}
    
    folders = get_folders(workspace_id, parent_id)
    
    for folder in folders:
        folder_id = folder.get("id")
        if folder_id:
            all_folders[folder_id] = folder
            # 递归获取子文件夹
            scan_folders_recursive(workspace_id, folder_id, all_folders)
    
    return all_folders


def save_to_database(folders: dict):
    """
    保存文件夹映射到数据库
    
    Args:
        folders: 文件夹字典 {id: folder}
    """
    # 清空现有数据
    FolderMap.delete().execute()
    
    count = 0
    for folder_id, folder in folders.items():
        folder_path = build_folder_path(folder, folders)
        
        try:
            FolderMap.create(
                id=folder_id,
                name=folder.get("name", ""),
                folderPath=folder_path
            )
            count += 1
            log.info(f"  保存: {folder_path}")
        except Exception as e:
            log.error(f"  保存失败 [{folder_path}]: {e}")
    
    return count


def main():
    log.info("=" * 60)
    log.info("获取目录映射工具")
    log.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)
    
    total_count = 0
    
    for ws in WORKSPACES:
        workspace_id = ws["id"]
        workspace_name = ws["name"]
        
        log.info(f"\n扫描工作空间: {workspace_name}")
        log.info("-" * 40)
        
        # 递归获取所有文件夹
        all_folders = scan_folders_recursive(workspace_id)
        log.info(f"找到 {len(all_folders)} 个文件夹")
        
        # 保存到数据库
        if all_folders:
            count = save_to_database(all_folders)
            total_count += count
    
    log.info("")
    log.info("=" * 60)
    log.info(f"完成！共保存 {total_count} 个文件夹映射")
    log.info(f"数据库位置: {db.database}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
