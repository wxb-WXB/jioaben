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
from src.config import API_KEY, API_HOST, WORKSPACES, AUTH_TOKEN

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)


def get_folder_tree(workspace_id: str) -> list:
    """
    获取文件夹树结构
    
    Args:
        workspace_id: 工作空间ID
        
    Returns:
        list: 文件夹树
    """
    url = f"{API_HOST}/api/v1/console/datasets/folders/tree"
    
    params = {
        "workspace_id": workspace_id,
    }
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
        "x-workspace-id": workspace_id,
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=60)
        
        if response.status_code == 200:
            data = response.json().get("data", {})
            tree = data.get("tree", [])
            log.info(f"  获取到文件夹树，根节点数: {len(tree)}")
            return tree
        else:
            log.error(f"获取文件夹树失败: {response.status_code}, {response.text[:200]}")
            return []
    except Exception as e:
        log.error(f"请求失败: {e}")
        return []


def collect_folders_from_tree(tree: list, parent_path: str = '') -> list:
    """
    从树结构中收集所有文件夹信息
    
    Args:
        tree: 文件夹树
        parent_path: 父路径
        
    Returns:
        list: 文件夹列表 [{'id': ..., 'name': ..., 'path': ...}, ...]
    """
    result = []
    for item in tree:
        # 只处理文件夹类型
        if item.get("type") != "folder":
            continue
        
        name = item.get('name', '')
        folder_id = item.get('id')
        this_path = f"{parent_path}/{name}" if parent_path else name
        
        result.append({
            'id': folder_id,
            'name': name,
            'path': this_path
        })
        
        # 递归处理子文件夹
        children = item.get('children', [])
        if children:
            result.extend(collect_folders_from_tree(children, this_path))
    
    return result


def save_to_database(folders: list):
    """
    保存文件夹映射到数据库
    
    Args:
        folders: 文件夹列表 [{'id': ..., 'name': ..., 'path': ...}, ...]
    """
    # 清空现有数据
    FolderMap.delete().execute()
    
    count = 0
    for folder in folders:
        try:
            FolderMap.create(
                id=folder['id'],
                name=folder['name'],
                folderPath=folder['path']
            )
            count += 1
            log.info(f"  保存: {folder['path']}")
        except Exception as e:
            log.error(f"  保存失败 [{folder['path']}]: {e}")
    
    return count


def main():
    log.info("=" * 60)
    log.info("获取目录映射工具")
    log.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)
    
    # 先清空数据库
    FolderMap.delete().execute()
    log.info("已清空现有数据")
    
    total_count = 0
    
    for ws in WORKSPACES:
        workspace_id = ws["id"]
        workspace_name = ws["name"]
        
        log.info(f"\n扫描工作空间: {workspace_name}")
        log.info("-" * 40)
        
        # 获取文件夹树
        tree = get_folder_tree(workspace_id)
        
        if not tree:
            log.warning(f"  未获取到文件夹")
            continue
        
        # 从树结构中收集所有文件夹
        folders = collect_folders_from_tree(tree)
        log.info(f"  共找到 {len(folders)} 个文件夹")
        
        # 保存到数据库
        if folders:
            for folder in folders:
                try:
                    FolderMap.create(
                        id=folder['id'],
                        name=folder['name'],
                        folderPath=folder['path']
                    )
                    total_count += 1
                    log.info(f"    保存: {folder['path']}")
                except Exception as e:
                    log.error(f"    保存失败 [{folder['path']}]: {e}")
    
    log.info("")
    log.info("=" * 60)
    log.info(f"完成！共保存 {total_count} 个文件夹映射")
    log.info(f"数据库位置: {db.database}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
