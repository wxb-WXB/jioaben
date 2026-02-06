# -*- coding: utf-8 -*-
"""
删除"科技数智部"知识库中关于会议的文档

功能：
- 查询"科技数智部"相关的知识库
- 查找包含"会议"关键词的文档
- 删除匹配的文档

使用方法：
python scripts/delete/delete_meeting_docs.py
"""
import sys
import os
import logging
import time
from datetime import datetime

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core import LingyanDataset
from src.config import API_KEY, WORKSPACE_IDS, LOGS_DIR

# 确保logs文件夹存在
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# 配置日志
log_filename = os.path.join(LOGS_DIR, f"delete_meeting_docs_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("delete_meeting_docs")

# ===================== 配置区域 =====================
# 目标知识库关键词（匹配知识库名称）
TARGET_DATASET_KEYWORD = "科技数智部"

# 文档名称关键词（匹配文档名称）
DOC_KEYWORDS = ["会议"]

# 删除间隔（秒）
DELETE_INTERVAL = 0.5

# 是否执行实际删除（False时只统计不删除，用于预览）
DRY_RUN = False
# ====================================================


def is_target_dataset(dataset_name):
    """判断知识库是否为目标知识库"""
    return TARGET_DATASET_KEYWORD in dataset_name


def is_meeting_document(doc_name):
    """判断文档是否包含会议关键词"""
    doc_name_lower = doc_name.lower()
    for keyword in DOC_KEYWORDS:
        if keyword.lower() in doc_name_lower:
            return True
    return False


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


def delete_meeting_documents(dataset_service, workspace_id):
    """删除科技数智部下关于会议的文档"""
    status, datasets = dataset_service.list_datasets(workspace_id)
    if status != 200:
        log.error(f"获取知识库列表失败: {datasets}")
        return 0, [], []
    
    total_deleted = 0
    deleted_list = []
    failed_list = []
    
    # 筛选出科技数智部相关的知识库
    target_datasets = [ds for ds in datasets if is_target_dataset(ds.get("name", ""))]
    
    log.info(f"共找到 {len(datasets)} 个知识库")
    log.info(f"其中 {len(target_datasets)} 个属于 '{TARGET_DATASET_KEYWORD}'")
    
    if not target_datasets:
        log.warning(f"未找到包含 '{TARGET_DATASET_KEYWORD}' 的知识库")
        return 0, [], []
    
    log.info("-" * 60)
    
    for i, ds in enumerate(target_datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        
        log.info(f"[{i+1}/{len(target_datasets)}] 处理知识库: {dataset_name}")
        
        try:
            status, documents = dataset_service.list_documents(dataset_id)
            if status != 200:
                log.error(f"  获取文档列表失败: {documents}")
                continue
            
            log.info(f"  共有 {len(documents)} 个文档")
            
            # 筛选出包含"会议"关键词的文档
            meeting_docs = [doc for doc in documents if is_meeting_document(doc.get("name", ""))]
            
            if not meeting_docs:
                log.info(f"  未找到包含会议关键词的文档")
                continue
            
            log.info(f"  找到 {len(meeting_docs)} 个包含会议关键词的文档")
            log.info("-" * 40)
            
            for j, doc in enumerate(meeting_docs):
                doc_id = doc.get("id")
                doc_name = doc.get("name", "未知")
                doc_type = doc.get("type", "").lower()
                doc_size = get_doc_size(doc)
                
                log.info(f"  [{j+1}/{len(meeting_docs)}] 文档: {doc_name} (类型={doc_type}, 大小={doc_size})")
                
                if DRY_RUN:
                    log.info(f"    [预览模式] 将被删除")
                    deleted_list.append({
                        "workspace": workspace_id,
                        "dataset_name": dataset_name,
                        "doc_name": doc_name,
                        "doc_type": doc_type,
                        "doc_size": doc_size,
                    })
                    total_deleted += 1
                else:
                    del_status, del_result = dataset_service.delete_document(dataset_id, doc_id)
                    
                    if del_status == 200:
                        total_deleted += 1
                        deleted_list.append({
                            "workspace": workspace_id,
                            "dataset_name": dataset_name,
                            "doc_name": doc_name,
                            "doc_type": doc_type,
                            "doc_size": doc_size,
                        })
                        log.info(f"    ✓ 删除成功")
                    else:
                        failed_list.append({
                            "workspace": workspace_id,
                            "dataset_name": dataset_name,
                            "doc_name": doc_name,
                            "error": del_result
                        })
                        log.error(f"    ✗ 删除失败: {del_result}")
                    
                    time.sleep(DELETE_INTERVAL)
            
            log.info("-" * 40)
                    
        except Exception as e:
            log.error(f"处理知识库 {dataset_name} 出错: {e}")
    
    return total_deleted, deleted_list, failed_list


if __name__ == "__main__":
    log.info("=" * 60)
    if DRY_RUN:
        log.info("【预览模式】查找科技数智部下关于会议的文档（不执行删除）")
    else:
        log.info("开始删除科技数智部下关于会议的文档")
    log.info(f"目标知识库关键词: {TARGET_DATASET_KEYWORD}")
    log.info(f"文档名称关键词: {DOC_KEYWORDS}")
    log.info("=" * 60)

    dataset = LingyanDataset(API_KEY)
    
    grand_total_deleted = 0
    grand_deleted_list = []
    grand_failed_list = []
    
    for ws_id, ws_name in WORKSPACE_IDS:
        log.info(f"\n处理工作空间: [{ws_name}]")
        log.info("-" * 60)
        
        deleted_count, deleted_list, failed_list = delete_meeting_documents(
            dataset,
            ws_id
        )
        
        grand_total_deleted += deleted_count
        grand_deleted_list.extend(deleted_list)
        grand_failed_list.extend(failed_list)
        
        log.info(f"[{ws_name}] 完成: 删除 {deleted_count} 个, 失败 {len(failed_list)} 个")

    log.info("\n" + "=" * 60)
    if DRY_RUN:
        log.info("【预览模式】统计结果（未执行实际删除）：")
    else:
        log.info("全部删除完成！统计信息：")
    log.info(f"总共{'将要删除' if DRY_RUN else '已删除'}: {grand_total_deleted} 个文档")
    if not DRY_RUN:
        log.info(f"删除失败: {len(grand_failed_list)} 个文档")
    
    if grand_deleted_list:
        log.info("-" * 60)
        log.info(f"{'将要删除' if DRY_RUN else '已删除'}的文档列表：")
        for item in grand_deleted_list:
            log.info(f"  知识库: {item['dataset_name']}")
            log.info(f"    文档: {item['doc_name']} (类型: {item['doc_type']})")
    
    if grand_failed_list and not DRY_RUN:
        log.info("-" * 60)
        log.info("删除失败的文档列表：")
        for failed in grand_failed_list:
            log.error(f"  知识库: {failed['dataset_name']}")
            log.error(f"    文档: {failed['doc_name']}")
            log.error(f"    错误: {failed['error']}")
    
    log.info("=" * 60)
    log.info(f"日志文件: {log_filename}")
    
    if DRY_RUN:
        log.info("\n提示: 当前为预览模式，未执行实际删除")
        log.info("      如需执行删除，请修改脚本中的 DRY_RUN = False")
