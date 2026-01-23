import os
import sys
import requests
import json

# 获取脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))

# 删除原有的folder.db（必须在导入models之前删除）
folder_db_path = os.path.join(script_dir, 'folder.db')
if os.path.exists(folder_db_path):
    os.remove(folder_db_path)

# 添加核心模块到路径
sys.path.insert(0, os.path.join(script_dir, '1_核心模块'))
from models import db, FolderMap

# 获取目录id和目录名的映射

workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"

url = "http://10.4.49.66:18080/api/v1/console/datasets/folders/tree"

query = {
    "workspace_id": workspace_id,
}

header = {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMDIzY2EzZDUyY2YwNDY0N2EwM2IyN2JhMWExMmNhMDUiLCJ1c2VybmFtZSI6IjEzNjI0ODM1MTE2IiwiaXNfc3VwZXJ1c2VyIjp0cnVlLCJleHAiOjE3Njk2OTY2MTV9.ccjfUXEaK9G_xZdPT8V4CKMkk-jBW3ei-tU30HlpiwU",
    "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
    "x-workspace-id": workspace_id,
}

response = requests.get(url, params=query, headers=header)
if response.status_code != 200:
    print(f"获取目录树失败: {response.status_code}, {response.text}")
    exit()
data = response.json().get("data")
if data is None:
    print(f"API返回的data为空，完整响应: {response.json()}")
    exit()
tree = data.get("tree")
if tree is None:
    print(f"API返回的tree为空，data内容: {data}")
    exit()

def collect_name_id_paths(data, parent_path=''):
    """
    遍历嵌套字典列表，生成所有 name 路径到 id 的映射。

    Args:
        data (list): 列表，每个元素为一个有 id、name、children 字段的字典
        parent_path (str): 上一级路径，递归内部使用，初次调用可不传
    """
    result = []
    for item in data:
        if item.get("type") != "folder":
            continue
        name = item.get('name', '')
        this_path = f"{parent_path}/{name}" if parent_path else name
        result.append({'path': this_path, 'id': item['id']})
        children = item.get('children', [])
        if children:
            result.extend(collect_name_id_paths(children, this_path))
    return result

folder_maps = collect_name_id_paths(tree)

print(f"找到 {len(folder_maps)} 个目录")

for mapping in folder_maps:
    FolderMap.create(
        id=mapping['id'],
        name=mapping['path'].split('/')[-1],
        folderPath=mapping['path']
    )

db.close()
print(f"已保存到数据库: {folder_db_path}")