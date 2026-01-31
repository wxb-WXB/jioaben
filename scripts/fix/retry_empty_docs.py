# -*- coding: utf-8 -*-
"""
空内容文档重试脚本

功能：
- 扫描知识库中向量化成功的文档
- 检查文档是否有分段内容
- 如果向量化成功但分段为空，则重新向量化
- 记录空分段文档到日志，下次启动时优先处理

使用方法：
python scripts/fix/retry_empty_docs.py
"""
import sys
import time
import os
import json
import requests
from datetime import datetime

# 设置控制台编码
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# 导入核心模块
from src.core import LingyanDataset
from src.core.models import FolderMap
from src.config import API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACE_NAME

# ============================================================
# 配置参数 - 修改这里来控制脚本行为
# ============================================================

# 只处理指定目录下的知识库（为空则处理所有目录）
TARGET_FOLDER_PATH = None

# ------------------------------
# 批次控制
# ------------------------------
BATCH_SIZE = 30          # 每批启动的任务数
BATCH_WAIT = 30          # 每批完成后等待时间（秒）

# ------------------------------
# 网络重试控制
# ------------------------------
MAX_RETRIES = 3          # 网络错误最大重试次数
RETRY_DELAY = 5          # 重试间隔（秒）

# ------------------------------
# 文件类型过滤（基于API返回的type字段）
# ------------------------------
INCLUDE_FILE_TYPES = None  # 处理所有类型
# INCLUDE_FILE_TYPES = {'doc', 'docx', 'txt', 'md', 'wps'}  # 只处理文本
# INCLUDE_FILE_TYPES = {'pdf'}  # 只处理PDF

EXCLUDE_FILE_TYPES = None

# ------------------------------
# 向量化任务配置
# ------------------------------
SPLIT_MODE = 'common'    # 'common'(普通切割) 或 'semantic'(语义切割)
PARSE_ENHANCE = False    # 是否开启精准解析
IMAGE_TASK = False       # 是否处理图片任务

# ------------------------------
# 日志文件配置
# ------------------------------
EMPTY_DOCS_LOG_FILE = "logs/empty_docs_pending.json"  # 待处理的空分段文档记录

# ============================================================
# 以下为脚本逻辑
# ============================================================

# 禁用 SSL 警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

dataset_api = LingyanDataset(API_KEY)

# 通用请求头
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json",
    "X-Workspace-Id": WORKSPACE_ID,
    "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


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
    """从文档的 tasks 字段获取向量化任务状态"""
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task", None
    
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


def is_vector_success(doc):
    """判断文档是否向量化成功"""
    doc_status, _ = get_doc_status(doc)
    return doc_status in ["completed", "success"]


def should_process_file(doc_type):
    """判断是否应该处理该文件类型"""
    if EXCLUDE_FILE_TYPES and doc_type in EXCLUDE_FILE_TYPES:
        return False
    if INCLUDE_FILE_TYPES:
        return doc_type in INCLUDE_FILE_TYPES
    return True


def get_document_segments(dataset_id, document_id):
    """获取文档的分段列表"""
    url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/segments"
    
    params = {
        "dataset_id": dataset_id,
        "document_id": document_id,
        "page": 1,
        "page_size": 10  # 只需要检查是否有分段，不需要全部
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=60, verify=False)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 200:
                    data = result.get("data", {})
                    if isinstance(data, dict):
                        segments = data.get("list", [])
                        total = data.get("total", len(segments))
                    elif isinstance(data, list):
                        segments = data
                        total = len(segments)
                    else:
                        segments = []
                        total = 0
                    
                    return True, segments, total
            
            return False, [], 0
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return False, [], 0
    
    return False, [], 0


def start_vector_task(dataset_id, document_id, workspace_id):
    """启动向量化任务"""
    for attempt in range(MAX_RETRIES):
        try:
            status, result = dataset_api.create_task(
                dataset_id=dataset_id,
                document_id=document_id,
                split_mode=SPLIT_MODE,
                task_type="normal",
                image_task=IMAGE_TASK,
                parse_enhance=PARSE_ENHANCE,
                workspace_id=workspace_id
            )
            return status == 200, result
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return False, str(e)
    return False, "重试失败"


def get_log_file_path():
    """获取日志文件的完整路径"""
    return os.path.join(project_root, EMPTY_DOCS_LOG_FILE)


def load_pending_docs():
    """加载待处理的空分段文档列表"""
    log_file = get_log_file_path()
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('pending_docs', [])
        except Exception as e:
            print(f"加载待处理文档日志失败: {e}")
    return []


def save_pending_docs(docs):
    """保存待处理的空分段文档列表"""
    log_file = get_log_file_path()
    # 确保目录存在
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    try:
        data = {
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'count': len(docs),
            'pending_docs': docs
        }
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已保存 {len(docs)} 个待处理文档到 {EMPTY_DOCS_LOG_FILE}")
    except Exception as e:
        print(f"保存待处理文档日志失败: {e}")


def remove_from_pending(pending_docs, dataset_id, document_id):
    """从待处理列表中移除已处理的文档"""
    return [doc for doc in pending_docs 
            if not (doc['dataset_id'] == dataset_id and doc['document_id'] == document_id)]


def print_config():
    """打印当前配置"""
    print("="*60)
    print("当前配置:")
    print("="*60)
    print(f"  批次大小: {BATCH_SIZE}")
    print(f"  批次等待: {BATCH_WAIT} 秒")
    print(f"  切割模式: {SPLIT_MODE}")
    print(f"  精准解析: {'开启' if PARSE_ENHANCE else '关闭'}")
    
    if INCLUDE_FILE_TYPES:
        print(f"  处理文件类型: {', '.join(sorted(INCLUDE_FILE_TYPES))}")
    else:
        print(f"  处理文件类型: 全部")
    
    print("="*60)


def process_single_doc(doc_info, workspace_id, batch_num, batch_count, stats):
    """处理单个文档的向量化任务"""
    dataset_id = doc_info['dataset_id']
    doc_id = doc_info['document_id']
    doc_name = doc_info['name']
    doc_type = doc_info.get('type', '')
    full_path = doc_info['path']
    
    print(f"\n  [批次{batch_num}][{batch_count}/{BATCH_SIZE}] 重新向量化: {doc_name} [type={doc_type}]")
    print(f"    路径: {full_path}")
    
    success, result = start_vector_task(dataset_id, doc_id, workspace_id)
    
    if success:
        print(f"    ✓ 成功")
        stats['success'] += 1
        return True, None
    else:
        print(f"    ✗ 失败: {result}")
        stats['fail'] += 1
        return False, {
            'name': doc_name,
            'path': full_path,
            'error': str(result),
        }


def main():
    start_time = datetime.now()
    
    print("="*60)
    print(f"空内容文档重试工具")
    print(f"功能：扫描向量化成功但分段为空的文档，重新向量化")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print_config()
    
    # 统计
    total_scanned = 0      # 扫描的向量化成功文档数
    total_empty = 0        # 空内容文档数
    total_started = 0      # 启动的任务数
    total_success = 0      # 启动成功数
    total_fail = 0         # 启动失败数
    batch_count = 0        # 当前批次已启动数量
    batch_num = 1
    
    # 记录
    empty_docs = []        # 空内容文档列表
    failed_docs = []       # 启动失败的文档
    
    workspace_id = WORKSPACE_ID
    workspace_name = WORKSPACE_NAME
    
    # ============================================================
    # 第一阶段：优先处理上次记录的待处理文档
    # ============================================================
    pending_docs = load_pending_docs()
    if pending_docs:
        print(f"\n{'='*60}")
        print(f"发现 {len(pending_docs)} 个上次记录的待处理文档，优先处理...")
        print(f"{'='*60}")
        
        stats = {'success': 0, 'fail': 0}
        still_pending = []  # 仍然需要处理的文档（仍为空分段）
        
        for i, doc_info in enumerate(pending_docs):
            # 先检查该文档是否仍然是空分段
            dataset_id = doc_info['dataset_id']
            doc_id = doc_info['document_id']
            doc_name = doc_info['name']
            
            print(f"\n[{i+1}/{len(pending_docs)}] 检查: {doc_name}")
            
            success, segments, total = get_document_segments(dataset_id, doc_id)
            
            if not success:
                print(f"  获取分段失败，保留在待处理列表")
                still_pending.append(doc_info)
                continue
            
            if total > 0:
                print(f"  已有 {total} 个分段，从待处理列表移除")
                continue
            
            # 仍然是空分段，启动向量化
            total_started += 1
            batch_count += 1
            
            proc_success, failed_info = process_single_doc(
                doc_info, workspace_id, batch_num, batch_count, stats
            )
            
            if proc_success:
                total_success += 1
            else:
                total_fail += 1
                if failed_info:
                    failed_docs.append(failed_info)
                still_pending.append(doc_info)  # 失败的保留在待处理列表
            
            # 批次满了，等待
            if batch_count >= BATCH_SIZE:
                print(f"\n{'='*60}")
                print(f"第 {batch_num} 批完成！成功: {total_success}, 失败: {total_fail}")
                print(f"等待 {BATCH_WAIT} 秒后继续...")
                print(f"{'='*60}")
                time.sleep(BATCH_WAIT)
                batch_num += 1
                batch_count = 0
        
        # 更新待处理文档日志
        if still_pending:
            save_pending_docs(still_pending)
        else:
            # 清空日志文件
            save_pending_docs([])
            print("所有待处理文档已处理完毕")
        
        print(f"\n{'='*60}")
        print(f"待处理文档处理完成: 成功 {stats['success']}, 失败 {stats['fail']}")
        print(f"{'='*60}")
    
    # ============================================================
    # 第二阶段：扫描知识库发现新的空分段文档
    # ============================================================
    print(f"\n正在扫描 [{workspace_name}] 的知识库...")
    
    try:
        status, datasets = dataset_api.list_datasets(workspace_id)
    except Exception as e:
        print(f"获取知识库列表失败: {e}")
        return
    
    if status != 200:
        print(f"获取知识库列表失败: {datasets}")
        return
    
    print(f"找到 {len(datasets)} 个知识库")
    
    for i, ds in enumerate(datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
            continue
        
        print(f"\n[{i+1}/{len(datasets)}] 扫描知识库: {dataset_name}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id, workspace_id)
            if status != 200:
                print(f"  获取文档失败")
                continue
            
            # 筛选向量化成功的文档
            success_docs = [doc for doc in documents if is_vector_success(doc)]
            
            if not success_docs:
                print(f"  无向量化成功的文档")
                continue
            
            print(f"  向量化成功: {len(success_docs)} 个，检查分段...")
            
            ds_empty = 0
            for doc in success_docs:
                doc_name = doc.get("name", "")
                doc_type = doc.get("type", "")
                doc_id = doc.get("id")
                
                if not should_process_file(doc_type):
                    continue
                
                total_scanned += 1
                
                # 检查分段
                success, segments, total = get_document_segments(dataset_id, doc_id)
                
                if not success:
                    print(f"    获取分段失败: {doc_name}")
                    continue
                
                # 检查是否为空
                if total == 0 or len(segments) == 0:
                    total_empty += 1
                    ds_empty += 1
                    
                    # 构建路径
                    if folder_path and folder_path != "根目录":
                        full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                    else:
                        full_path = f"{dataset_name}/{doc_name}"
                    
                    empty_docs.append({
                        'dataset_id': dataset_id,
                        'document_id': doc_id,
                        'name': doc_name,
                        'type': doc_type,
                        'path': full_path,
                    })
                    
                    # 启动重新向量化
                    total_started += 1
                    batch_count += 1
                    
                    print(f"\n  [批次{batch_num}][{batch_count}/{BATCH_SIZE}] 空内容，重新向量化: {doc_name} [type={doc_type}]")
                    print(f"    路径: {full_path}")
                    
                    success, result = start_vector_task(dataset_id, doc_id, workspace_id)
                    
                    if success:
                        print(f"    ✓ 成功")
                        total_success += 1
                    else:
                        print(f"    ✗ 失败: {result}")
                        total_fail += 1
                        failed_docs.append({
                            'name': doc_name,
                            'path': full_path,
                            'error': str(result),
                        })
                    
                    # 批次满了，等待
                    if batch_count >= BATCH_SIZE:
                        print(f"\n{'='*60}")
                        print(f"第 {batch_num} 批完成！成功: {total_success}, 失败: {total_fail}")
                        print(f"等待 {BATCH_WAIT} 秒后继续...")
                        print(f"{'='*60}")
                        time.sleep(BATCH_WAIT)
                        batch_num += 1
                        batch_count = 0
            
            if ds_empty > 0:
                print(f"\n  知识库 [{dataset_name}] 发现 {ds_empty} 个空内容文档")
            else:
                print(f"  无空内容文档")
                
        except Exception as e:
            print(f"  出错: {e}")
            time.sleep(RETRY_DELAY)
    
    end_time = datetime.now()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0]
    
    # 最终统计
    print(f"\n{'='*60}")
    print(f"全部完成！")
    print(f"{'='*60}")
    print(f"  开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  总耗时: {duration_str}")
    print(f"  扫描向量成功文档: {total_scanned}")
    print(f"  发现空内容文档: {total_empty}")
    print(f"  启动重新向量化: {total_started}")
    print(f"  成功: {total_success}")
    print(f"  失败: {total_fail}")
    if total_started > 0:
        success_rate = total_success / total_started * 100
        print(f"  成功率: {success_rate:.1f}%")
    
    # 显示空内容文档列表
    if empty_docs:
        print(f"\n{'='*60}")
        print(f"空内容文档列表 ({len(empty_docs)} 个):")
        print(f"{'='*60}")
        for doc in empty_docs[:100]:
            print(f"  [{doc['type']}] {doc['path']}")
        if len(empty_docs) > 100:
            print(f"  ... 还有 {len(empty_docs) - 100} 个")
    
    # 显示失败列表
    if failed_docs:
        print(f"\n{'='*60}")
        print(f"启动失败列表 ({len(failed_docs)} 个):")
        print(f"{'='*60}")
        for doc in failed_docs[:50]:
            print(f"  {doc['path']}")
            print(f"    错误: {doc['error']}")
        if len(failed_docs) > 50:
            print(f"  ... 还有 {len(failed_docs) - 50} 个")
    
    # 保存本次发现的空内容文档到待处理日志（供下次启动时优先处理）
    if empty_docs:
        # 合并之前仍待处理的文档
        existing_pending = load_pending_docs()
        existing_ids = {(d['dataset_id'], d['document_id']) for d in existing_pending}
        
        # 添加本次新发现的空内容文档（去重）
        new_pending = list(existing_pending)
        for doc in empty_docs:
            doc_key = (doc['dataset_id'], doc['document_id'])
            if doc_key not in existing_ids:
                new_pending.append(doc)
        
        if new_pending:
            save_pending_docs(new_pending)
            print(f"\n已记录 {len(new_pending)} 个空内容文档到待处理日志，下次启动时将优先处理")
    
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
