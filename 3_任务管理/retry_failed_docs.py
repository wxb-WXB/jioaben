"""
检测失败的文档并重新启动向量化任务
- 遍历知识库，发现失败文档后立即处理
- 每次启动20个向量化任务后暂停等待
"""
import sys
import time
import os

# 设置控制台编码
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset
from models import FolderMap

api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 两个 workspace ID
workspace_ids = [("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "工作空间1"),]

# 每批处理的文档数量
BATCH_SIZE = 50

# 每批处理完后等待的时间（秒）
WAIT_TIME = 700

dataset_api = LingyanDataset(api_key)


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


def get_doc_status(doc):
    """
    从文档的 tasks 字段获取向量化任务状态
    """
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task", None
    
    # 优先查找 type=normal 的任务（这是向量化任务）
    normal_task = None
    for task in tasks:
        if task.get("type") == "normal":
            normal_task = task
            break
    
    if normal_task:
        return normal_task.get("status", "unknown"), normal_task.get("type")
    else:
        latest_task = tasks[-1]
        return latest_task.get("status", "unknown"), latest_task.get("type")


def retry_single_doc(doc, batch_num, batch_pos):
    """重试单个文档"""
    print(f"\n[批次{batch_num}][{batch_pos}/{BATCH_SIZE}] 重试文档: {doc['document_name']}")
    print(f"  目录路径: {doc['folder_path']}")
    print(f"  知识库: {doc['dataset_name']}")
    print(f"  文档ID: {doc['document_id']}")
    
    try:
        status, result = dataset_api.create_task(
            dataset_id=doc['dataset_id'],
            document_id=doc['document_id'],
            split_mode="semantic",
            task_type="normal",
            image_task=False,
            parse_enhance=True
        )
        
        if status == 200:
            print(f"  ✓ 任务创建成功")
            return True
        else:
            print(f"  ✗ 任务创建失败: {result}")
            return False
            
    except Exception as e:
        print(f"  ✗ 出错: {e}")
        return False


def scan_and_retry(workspace_id, workspace_name):
    """
    扫描知识库，发现失败文档后立即处理
    每处理完20个文档后暂停等待
    """
    print(f"\n正在扫描 [{workspace_name}] 的知识库...")
    status, datasets = dataset_api.list_datasets(workspace_id)
    
    if status != 200:
        print(f"获取知识库列表失败: {datasets}")
        return 0, 0
    
    print(f"找到 {len(datasets)} 个知识库")
    
    total_success = 0
    total_fail = 0
    current_batch = []  # 当前批次的文档
    batch_num = 1
    
    for i, ds in enumerate(datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        print(f"\n[{i+1}/{len(datasets)}] 检查知识库: {dataset_name}")
        print(f"  目录路径: {folder_path}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id)
            if status != 200:
                print(f"  获取文档失败")
                continue
            
            # 收集该知识库中的失败文档
            failed_in_ds = []
            for doc in documents:
                doc_status, _ = get_doc_status(doc)
                
                if doc_status in ["error", "failed"]:
                    failed_in_ds.append({
                        "dataset_id": dataset_id,
                        "dataset_name": dataset_name,
                        "document_id": doc.get("id"),
                        "document_name": doc.get("name"),
                        "workspace": workspace_name,
                        "folder_path": folder_path
                    })
            
            if len(failed_in_ds) == 0:
                print(f"  无失败文档，继续扫描...")
                continue
            
            print(f"  发现 {len(failed_in_ds)} 个失败文档，开始处理...")
            print(f"{'='*60}")
            
            # 立即处理这些失败文档
            for doc in failed_in_ds:
                current_batch.append(doc)
                batch_pos = len(current_batch)
                
                # 处理文档
                if retry_single_doc(doc, batch_num, batch_pos):
                    total_success += 1
                else:
                    total_fail += 1
                
                # 如果当前批次满了，暂停等待
                if len(current_batch) >= BATCH_SIZE:
                    print(f"\n{'='*60}")
                    print(f"第 {batch_num} 批完成（成功: {total_success}, 失败: {total_fail}）")
                    print(f"等待 {WAIT_TIME} 秒后继续...")
                    print(f"{'='*60}")
                    time.sleep(WAIT_TIME)
                    
                    batch_num += 1
                    current_batch = []
            
            print(f"{'='*60}")
            print(f"知识库 [{dataset_name}] 处理完成")
                
        except Exception as e:
            print(f"  出错: {e}")
    
    return total_success, total_fail


def main():
    print("="*60)
    print("失败文档重试工具（边扫描边处理）")
    print(f"每批处理 {BATCH_SIZE} 个文档，每批间隔 {WAIT_TIME} 秒")
    print("="*60)
    
    total_success = 0
    total_fail = 0
    
    for ws_id, ws_name in workspace_ids:
        success, fail = scan_and_retry(ws_id, ws_name)
        total_success += success
        total_fail += fail
    
    print(f"\n{'='*60}")
    print(f"全部完成！")
    print(f"成功: {total_success}, 失败: {total_fail}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
