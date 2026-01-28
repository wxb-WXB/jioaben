"""
全局删除知识库中的指定类型文件或空文件（file_size=0）
"""
import sys
import os
import logging
import time
from datetime import datetime

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset

# 确保logs文件夹存在（使用项目根目录）
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志文件名（按日期）
log_filename = os.path.join(logs_dir, f"delete_files_{datetime.now().strftime('%Y-%m-%d')}.log")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("delete_files")

# ===================== 配置区域 =====================
workspace_ids = [
    ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库"),
    # ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "第二个知识库"),
]

api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 要删除的文件类型列表（注意：不带点，如 "png" 而不是 ".png"）
file_types_to_delete = ["png", "zip", "jpg", "jpeg", "mp4", "dwg", "htm", "ico", "css", "pdg", "dat", "xml"]

# 是否删除 file_size 为 0 的文件
DELETE_ZERO_SIZE = True

# ====================================================


def get_doc_size(doc):
    """获取文档大小"""
    size = doc.get("word_count")
    if size is not None and size > 0:
        return size
    size = doc.get("size")
    if size is not None and size > 0:
        return size
    size = doc.get("file_size")
    if size is not None and size > 0:
        return size
    return 0


def delete_empty_and_type_files(dataset_service, workspace_id, file_types, delete_zero_size=True):
    """
    删除空文件和指定类型的文件
    """
    # 获取知识库列表
    status, datasets = dataset_service.list_datasets(workspace_id)
    if status != 200:
        log.error(f"获取知识库列表失败: {datasets}")
        return 0, []
    
    total_deleted = 0
    failed_list = []
    
    log.info(f"共找到 {len(datasets)} 个知识库")
    
    for i, ds in enumerate(datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        
        log.info(f"[{i+1}/{len(datasets)}] 处理知识库: {dataset_name}")
        
        try:
            status, documents = dataset_service.list_documents(dataset_id)
            if status != 200:
                continue
            
            for doc in documents:
                doc_id = doc.get("id")
                doc_name = doc.get("name", "未知")
                doc_type = doc.get("type", "").lower()
                doc_size = get_doc_size(doc)
                
                should_delete = False
                delete_reason = ""
                
                # 检查是否需要删除
                if delete_zero_size and doc_size == 0:
                    should_delete = True
                    delete_reason = "file_size=0"
                elif doc_type in [t.lower() for t in file_types]:
                    should_delete = True
                    delete_reason = f"类型={doc_type}"
                
                if should_delete:
                    log.info(f"  删除文档: {doc_name} ({delete_reason})")
                    
                    del_status, del_result = dataset_service.delete_document(dataset_id, doc_id)
                    
                    if del_status == 200:
                        total_deleted += 1
                        log.info(f"    ✓ 删除成功")
                    else:
                        failed_list.append({
                            "name": doc_name,
                            "dataset_name": dataset_name,
                            "reason": delete_reason,
                            "error": del_result
                        })
                        log.error(f"    ✗ 删除失败: {del_result}")
                    
                    # 避免请求过快
                    time.sleep(1)
                    
        except Exception as e:
            log.error(f"处理知识库 {dataset_name} 出错: {e}")
    
    return total_deleted, failed_list


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("开始删除空文件和指定类型的文件")
    log.info(f"要删除的文件类型: {file_types_to_delete}")
    log.info(f"删除 file_size=0 的文件: {DELETE_ZERO_SIZE}")
    log.info("=" * 60)

    dataset = LingyanDataset(api_key)
    
    grand_total_deleted = 0
    grand_total_failed = []
    
    for ws_id, ws_name in workspace_ids:
        log.info(f"\n处理工作空间: [{ws_name}]")
        log.info("-" * 40)
        
        deleted, failed = delete_empty_and_type_files(
            dataset,
            ws_id,
            file_types_to_delete,
            DELETE_ZERO_SIZE
        )
        
        grand_total_deleted += deleted
        grand_total_failed.extend(failed)
        
        log.info(f"[{ws_name}] 删除完成: 成功 {deleted} 个, 失败 {len(failed)} 个")

    # 输出结果
    log.info("\n" + "=" * 60)
    log.info("全部删除完成！统计信息：")
    log.info(f"总共删除: {grand_total_deleted} 个文档")
    log.info(f"删除失败: {len(grand_total_failed)} 个文档")
    
    if grand_total_failed:
        log.info("-" * 40)
        log.info("删除失败的文档列表：")
        for failed in grand_total_failed:
            log.error(f"  文档: {failed['name']} (知识库: {failed['dataset_name']})")
            log.error(f"    原因: {failed['reason']}, 错误: {failed['error']}")
    
    log.info("=" * 60)
