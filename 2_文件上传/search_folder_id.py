# -*- coding: utf-8 -*-
"""
搜索目录ID工具

用于在 folder.db 中搜索包含指定关键词的目录，并显示其ID
"""

import os
import sys

# 获取脚本所在目录和项目根目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# 添加核心模块到路径
sys.path.insert(0, os.path.join(project_root, '1_核心模块'))
from models import FolderMap

# ============ 配置 ============
SEARCH_KEYWORD = "03土建A1施工文件"
# ==============================

print("=" * 60)
print("搜索目录ID工具")
print("=" * 60)

print(f"\n🔎 搜索关键词：{SEARCH_KEYWORD}")
print("-" * 60)

# 搜索
results = []
for folder in FolderMap.select():
    if SEARCH_KEYWORD in folder.folderPath:
        results.append({
            'path': folder.folderPath,
            'id': folder.id,
            'name': folder.name
        })

if results:
    print(f"找到 {len(results)} 个匹配的目录：\n")
    for i, r in enumerate(results):
        print(f"{i+1}. 路径：{r['path']}")
        print(f"   名称：{r['name']}")
        print(f"   ID：{r['id']}")
        print()
else:
    print(f"❌ 未找到包含 '{SEARCH_KEYWORD}' 的目录")
    print("\n数据库中的所有目录（前20个）：")
    for i, folder in enumerate(FolderMap.select().limit(20)):
        print(f"  {i+1}. {folder.folderPath}")
