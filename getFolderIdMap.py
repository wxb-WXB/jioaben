import requests
import json
from models import db, FolderMap

# 获取目录id和目录名的映射

workspace_id = "faa3722a-398e-4f1a-aad8-7aecfff4f369"

url = "http://10.4.49.66:18080/api/v1/console/datasets/folders/tree"

query = {
    "workspace_id": workspace_id,
}

header = {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMDIzY2EzZDUyY2YwNDY0N2EwM2IyN2JhMWExMmNhMDUiLCJ1c2VybmFtZSI6IjEzNjI0ODM1MTE2IiwiaXNfc3VwZXJ1c2VyIjpmYWxzZSwiZXhwIjoxNzY4ODk2NTExfQ.3yIg8VA2QcZlWsSGnWEHMj2tyXrOyyOG0Nvh6dULLiQ",
    "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
    "x-workspace-id": workspace_id,
}

response = requests.get(url, params=query, headers=header)
data = response.json().get("data")
tree = data.get("tree")

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

for mapping in folder_maps:
    FolderMap.create(
        id=mapping['id'],
        name=mapping['path'].split('/')[-1],
        folderPath=mapping['path']
    )

db.close()