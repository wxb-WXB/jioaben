"""
调试脚本：查看文档的数据结构
"""
import json
from LingyanAi import LingyanDataset

api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"

dataset = LingyanDataset(api_key)

# 获取知识库列表
status, datasets = dataset.list_datasets(workspace_id)
print(f"获取到 {len(datasets)} 个知识库")

# 取第一个知识库，查看其文档结构
if datasets:
    first_dataset = datasets[0]
    dataset_id = first_dataset.get("id")
    dataset_name = first_dataset.get("name")
    print(f"\n查看知识库: {dataset_name} (ID: {dataset_id})")
    
    status, documents = dataset.list_documents(dataset_id)
    print(f"获取到 {len(documents)} 个文档")
    
    # 打印前5个文档的完整结构
    print("\n=== 文档数据结构示例 ===")
    for i, doc in enumerate(documents[:5]):
        print(f"\n--- 文档 {i+1} ---")
        print(json.dumps(doc, indent=2, ensure_ascii=False))
