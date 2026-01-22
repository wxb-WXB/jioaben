"""
列出所有知识库的名称和dataset_id
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from LingyanAi import LingyanDataset

api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 两个 workspace ID
workspace_ids = [
    ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "工作空间1"),
    ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "工作空间2"),
]

dataset = LingyanDataset(api_key)

all_datasets = []

for ws_id, ws_name in workspace_ids:
    status, datasets_list = dataset.list_datasets(ws_id)
    if status == 200:
        for ds in datasets_list:
            all_datasets.append({
                "name": ds.get("name", "未知"),
                "id": ds.get("id", ""),
                "workspace": ws_name
            })

print(f"共找到 {len(all_datasets)} 个知识库\n")
print("="*80)

# 按工作空间分组输出
for ws_id, ws_name in workspace_ids:
    ws_datasets = [d for d in all_datasets if d["workspace"] == ws_name]
    print(f"\n【{ws_name}】共 {len(ws_datasets)} 个知识库")
    print("-"*80)
    for ds in sorted(ws_datasets, key=lambda x: x["name"]):
        print(f"{ds['name']}：{ds['id']}")

# 保存到文件
output_file = "all_datasets_list.txt"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(f"共 {len(all_datasets)} 个知识库\n")
    f.write("="*80 + "\n")
    
    for ws_id, ws_name in workspace_ids:
        ws_datasets = [d for d in all_datasets if d["workspace"] == ws_name]
        f.write(f"\n【{ws_name}】共 {len(ws_datasets)} 个知识库\n")
        f.write("-"*80 + "\n")
        for ds in sorted(ws_datasets, key=lambda x: x["name"]):
            f.write(f"{ds['name']}：{ds['id']}\n")

print(f"\n\n已保存到文件: {output_file}")
