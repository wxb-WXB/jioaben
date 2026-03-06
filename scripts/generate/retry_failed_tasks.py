# -*- coding: utf-8 -*-
"""
失败文档重试脚本

功能：
- 遍历知识库，检测失败/无任务的文档
- 支持两种模式：批次模式 和 轮询模式
- 批次模式：每次启动N个任务，等待一段时间，继续下一批
- 轮询模式：边扫描边处理，始终保持N个任务在运行，完成一个立即补充一个
- 失败记录功能：自动记录失败文档，支持跳过或专门重试失败记录

使用方法：
python scripts/generate/retry_failed_tasks.py

失败记录配置：
- ENABLE_FAILED_RECORD = True：启用失败记录功能
- SKIP_RECORDED_FAILED = True：跳过已记录的失败文档（正常模式）
- PROCESS_ONLY_FAILED_RECORD = False：只处理失败记录（专门重试失败的）
  * 设为 True 时，只重试之前失败过的文档
  * 设为 False 时，正常处理所有失败/无任务的文档
"""
import sys
import time
import os
import requests

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
from src.config import (
    API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACES,
    PRIORITY_FOLDER_IDS, ONLY_PRIORITY_FOLDER,
    TARGET_FOLDER_PATH, ONLY_TARGET_FOLDER,
    FAILED_RECORDS_DIR,
)
import json
from datetime import datetime

# ============================================================
# 配置参数 - 修改这里来控制脚本行为
# ============================================================

# workspace ID 配置
# workspace_ids = [(ws["id"], ws["name"]) for ws in WORKSPACES]
# 只使用环北知识库
workspace_ids = [("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库")]

# 只处理指定目录下的知识库，从 config.py 读取 TARGET_FOLDER_PATH、ONLY_TARGET_FOLDER

# 优先处理的文件夹ID配置已移至 src/config.py
# 可通过修改 config.py 中的 PRIORITY_FOLDER_IDS 和 ONLY_PRIORITY_FOLDER 来调整优先级

# ------------------------------
# 运行模式
# ------------------------------
# 'batch'   - 批次模式：启动N个任务，等待一段时间，继续下一批
# 'polling' - 轮询模式：始终保持N个任务在运行，完成一个立即补充一个
RUN_MODE = 'polling'

# ------------------------------
# 批次模式配置
# ------------------------------
BATCH_SIZE = 60          # 每批启动的任务数
BATCH_WAIT = 60         # 每批完成后等待时间（秒）
REQUEST_INTERVAL = 0.1   # 每次启动任务之间的间隔（秒）

# ------------------------------
# 轮询模式配置
# ------------------------------
WINDOW_SIZE = 60         # 同时运行的任务数量（滑动窗口大小）
POLL_INTERVAL = 2        # 检查任务状态的间隔（秒）
MAX_WAIT_TIME = 3600     # 单个任务最大等待时间（秒），超时则跳过

# ------------------------------
# 网络重试控制
# ------------------------------
MAX_RETRIES = 3          # 网络错误最大重试次数
RETRY_DELAY = 2          # 重试间隔（秒）

# ------------------------------
# 文件类型过滤（基于API返回的type字段）
# ------------------------------
# INCLUDE_FILE_TYPES = {'doc', 'docx', 'txt', 'md', 'wps'}
# INCLUDE_FILE_TYPES = {'pdf'}
INCLUDE_FILE_TYPES = None  # 处理所有类型
EXCLUDE_FILE_TYPES = None  # 要排除的类型集合，None 表示不排除任何类型

# ------------------------------
# 文档状态过滤
# ------------------------------
RETRY_STATUS = ['error', 'failed', 'cancelled', 'no_task']

# ------------------------------
# 路径长度限制（超长路径直接跳过，不启动任务）
# ------------------------------
MAX_PATH_LENGTH = 150   # 完整路径超过此字符数则跳过

# ------------------------------
# 失败记录配置
# ------------------------------
ENABLE_FAILED_RECORD = True          # 是否启用失败记录功能
SKIP_RECORDED_FAILED = True          # 是否跳过已记录的失败文档
PROCESS_ONLY_FAILED_RECORD = False   # 是否只处理失败记录（True=只重试失败记录，False=正常模式）
FAILED_RECORD_FILE = os.path.join(FAILED_RECORDS_DIR, "retry_failed_tasks.json")  # 失败记录文件路径

# ------------------------------
# 向量化任务配置
# ------------------------------
SPLIT_MODE = 'common'    # 'common'(普通切割) 或 'semantic'(语义切割)
PARSE_ENHANCE = True    # 是否开启精准解析
IMAGE_TASK = False       # 是否处理图片任务

# ============================================================
# 以下为脚本逻辑
# ============================================================

# 禁用 SSL 警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

dataset_api = LingyanDataset(API_KEY)

# 失败记录缓存（document_id -> 失败信息）
failed_records = {}

# 通用请求头（用于轮询模式检查任务状态）
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json",
    "X-Workspace-Id": WORKSPACE_ID,
    "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def load_failed_records():
    """加载失败记录"""
    global failed_records
    if not ENABLE_FAILED_RECORD:
        return
    
    if os.path.exists(FAILED_RECORD_FILE):
        try:
            with open(FAILED_RECORD_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                failed_records = data.get('failed_docs', {})
                print(f"\n{'='*60}")
                print(f"已加载 {len(failed_records)} 条失败记录")
                if failed_records:
                    updated_at = data.get('updated_at', '未知')
                    print(f"最后更新: {updated_at}")
                    print(f"失败记录文件: {FAILED_RECORD_FILE}")
                    if SKIP_RECORDED_FAILED:
                        print(f"⚠️  这些文档将被跳过，不会重新处理")
                    print(f"{'='*60}\n")
        except Exception as e:
            print(f"加载失败记录出错: {e}")
            failed_records = {}
    else:
        print("未找到失败记录文件，将创建新的记录")
        failed_records = {}


def save_failed_records():
    """保存失败记录"""
    if not ENABLE_FAILED_RECORD:
        return
    
    try:
        os.makedirs(os.path.dirname(FAILED_RECORD_FILE), exist_ok=True)
        with open(FAILED_RECORD_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_failed': len(failed_records),
                'failed_docs': failed_records
            }, f, ensure_ascii=False, indent=2)
        print(f"\n{'='*60}")
        print(f"✓ 已保存 {len(failed_records)} 条失败记录")
        print(f"文件位置: {FAILED_RECORD_FILE}")
        print(f"下次启动时将自动跳过这些失败的文档")
        print(f"{'='*60}\n")
    except Exception as e:
        print(f"保存失败记录出错: {e}")


def is_in_failed_records(document_id):
    """检查文档是否在失败记录中"""
    return document_id in failed_records


def add_failed_record(doc_id, doc_name, doc_path, doc_type, error_msg):
    """添加失败记录"""
    global failed_records
    failed_records[doc_id] = {
        'name': doc_name,
        'path': doc_path,
        'type': doc_type,
        'error': error_msg,
        'failed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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


def should_process_file(doc_type):
    """判断是否应该处理该文件类型"""
    if EXCLUDE_FILE_TYPES and doc_type in EXCLUDE_FILE_TYPES:
        return False
    if INCLUDE_FILE_TYPES:
        return doc_type in INCLUDE_FILE_TYPES
    return True


def list_documents_with_retry(dataset_id, workspace_id):
    """带重试的获取文档列表"""
    for attempt in range(MAX_RETRIES):
        try:
            status, documents = dataset_api.list_documents(dataset_id, workspace_id)
            if status == 200:
                return status, documents
            return status, documents
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f" - 网络错误，{wait_time}秒后重试({attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait_time)
            else:
                raise e
    return 500, "重试失败"


def start_task(doc, workspace_id):
    """启动单个文档的向量化任务"""
    for attempt in range(MAX_RETRIES):
        try:
            status, result = dataset_api.create_task(
                dataset_id=doc['dataset_id'],
                document_id=doc['document_id'],
                split_mode=SPLIT_MODE,
                task_type="normal",
                image_task=IMAGE_TASK,
                parse_enhance=PARSE_ENHANCE,
                workspace_id=workspace_id
            )
            return status == 200, result
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f"    网络错误，{wait_time}秒后重试({attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait_time)
            else:
                return False, str(e)
    return False, "重试失败"


def get_document_info(dataset_id, document_id):
    """获取单个文档的最新信息（用于轮询模式）"""
    url = f"https://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                return True, result.get("data", {})
    except:
        pass
    return False, None


def print_config():
    """打印当前配置"""
    print("="*60)
    print("当前配置:")
    print("="*60)
    
    if RUN_MODE == 'batch':
        print(f"  运行模式: 批次模式 (batch)")
        print(f"  批次大小: {BATCH_SIZE}")
        print(f"  批次等待: {BATCH_WAIT} 秒")
        print(f"  请求间隔: {REQUEST_INTERVAL} 秒")
    else:
        print(f"  运行模式: 轮询模式 (polling)")
        print(f"  窗口大小: {WINDOW_SIZE}")
        print(f"  轮询间隔: {POLL_INTERVAL} 秒")
        print(f"  最大等待: {MAX_WAIT_TIME} 秒")
    
    if ONLY_TARGET_FOLDER and TARGET_FOLDER_PATH:
        print(f"  仅处理目标路径: {TARGET_FOLDER_PATH}")
    elif PRIORITY_FOLDER_IDS:
        print(f"  优先文件夹数量: {len(PRIORITY_FOLDER_IDS)}")
        for folder_id in PRIORITY_FOLDER_IDS:
            priority_folder_path = get_folder_path(folder_id)
            print(f"    - {priority_folder_path} (ID: {folder_id})")
        print(f"  只处理优先文件夹: {'是' if ONLY_PRIORITY_FOLDER else '否'}")
        if TARGET_FOLDER_PATH:
            print(f"  路径过滤: {TARGET_FOLDER_PATH}")
    else:
        if TARGET_FOLDER_PATH:
            print(f"  目标文件夹路径: {TARGET_FOLDER_PATH}")
        else:
            print(f"  目标文件夹路径: 全部")
    
    print(f"  切割模式: {SPLIT_MODE}")
    print(f"  精准解析: {'开启' if PARSE_ENHANCE else '关闭'}")
    
    if INCLUDE_FILE_TYPES:
        print(f"  处理文件类型: {', '.join(sorted(INCLUDE_FILE_TYPES))}")
    else:
        print(f"  处理文件类型: 全部")
    
    print(f"  重试状态: {', '.join(RETRY_STATUS)}")
    print(f"  路径长度限制: {MAX_PATH_LENGTH} 字符（超长跳过）")
    
    # 失败记录配置
    print(f"  失败记录: {'启用' if ENABLE_FAILED_RECORD else '关闭'}")
    if ENABLE_FAILED_RECORD:
        print(f"    - 跳过已失败: {'是' if SKIP_RECORDED_FAILED else '否'}")
        print(f"    - 只处理失败记录: {'是' if PROCESS_ONLY_FAILED_RECORD else '否'}")
        if len(failed_records) > 0:
            print(f"    - 已记录失败数: {len(failed_records)}")
            # 统计失败原因
            error_types = {}
            for doc_id, info in failed_records.items():
                error = info.get('error', '未知错误')
                error_types[error] = error_types.get(error, 0) + 1
            if len(error_types) > 0:
                print(f"    - 失败原因分布:")
                for error, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"      · {error}: {count} 个")
                if len(error_types) > 5:
                    print(f"      · ... 还有 {len(error_types) - 5} 种其他错误")
    
    print("="*60)


def collect_all_docs():
    """收集所有需要处理的文档"""
    all_docs = []
    
    for ws_id, ws_name in workspace_ids:
        print(f"\n正在扫描 [{ws_name}] 的知识库...")
        
        datasets_to_process = []
        other_datasets = []
        
        if ONLY_TARGET_FOLDER and TARGET_FOLDER_PATH:
            # 仅处理 TARGET_FOLDER_PATH 下的文件
            print(f"仅处理目标路径: {TARGET_FOLDER_PATH}")
            try:
                status, all_datasets = dataset_api.list_datasets(ws_id)
                if status == 200:
                    for ds in all_datasets:
                        folder_id = ds.get("folder_id")
                        folder_path = get_folder_path(folder_id)
                        if TARGET_FOLDER_PATH in folder_path:
                            other_datasets.append(ds)
                    print(f"找到 {len(other_datasets)} 个知识库（路径包含 {TARGET_FOLDER_PATH}）")
            except Exception as e:
                print(f"获取知识库列表失败: {e}")
        elif PRIORITY_FOLDER_IDS:
            print(f"优先处理 {len(PRIORITY_FOLDER_IDS)} 个文件夹:")
            
            for folder_id in PRIORITY_FOLDER_IDS:
                priority_folder_path = get_folder_path(folder_id)
                print(f"  - {priority_folder_path} (ID: {folder_id})")
                
                try:
                    status, priority_datasets = dataset_api.list_datasets(ws_id, folder_id=folder_id)
                    if status == 200:
                        datasets_to_process.extend(priority_datasets)
                        print(f"    找到 {len(priority_datasets)} 个知识库")
                except Exception as e:
                    print(f"    获取知识库失败: {e}")
        
        # 如果需要处理其他文件夹（非 ONLY_TARGET_FOLDER 模式时）
        if not ONLY_TARGET_FOLDER and not ONLY_PRIORITY_FOLDER:
            try:
                status, all_datasets = dataset_api.list_datasets(ws_id)
                if status == 200:
                    # 过滤掉已经在优先列表中的知识库
                    priority_dataset_ids = {ds.get("id") for ds in datasets_to_process}
                    for ds in all_datasets:
                        if ds.get("id") not in priority_dataset_ids:
                            folder_id = ds.get("folder_id")
                            folder_path = get_folder_path(folder_id)
                            # 如果设置了TARGET_FOLDER_PATH，需要匹配路径
                            if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                                continue
                            other_datasets.append(ds)
                    print(f"其他文件夹找到 {len(other_datasets)} 个知识库")
            except Exception as e:
                print(f"获取其他知识库列表失败: {e}")
        
        # 合并列表：优先文件夹在前
        all_datasets_list = datasets_to_process + other_datasets
        
        if not all_datasets_list:
            print("没有找到需要处理的知识库")
            continue
        
        print(f"总共需要处理 {len(all_datasets_list)} 个知识库")
        
        for i, ds in enumerate(all_datasets_list):
            dataset_id = ds.get("id")
            dataset_name = ds.get("name")
            folder_id = ds.get("folder_id")
            folder_path = get_folder_path(folder_id)
            
            # 如果设置了TARGET_FOLDER_PATH且不在优先文件夹中，需要匹配路径
            if not PRIORITY_FOLDER_IDS or folder_id not in PRIORITY_FOLDER_IDS:
                if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                    continue
            
            is_priority = folder_id in PRIORITY_FOLDER_IDS if PRIORITY_FOLDER_IDS else False
            prefix = "[优先]" if is_priority else ""
            print(f"{prefix}[{i+1}/{len(all_datasets_list)}] 扫描: {dataset_name}", end=" ")
            
            try:
                status, documents = list_documents_with_retry(dataset_id, ws_id)
                if status != 200:
                    print("- 获取文档失败")
                    continue
                
                found_count = 0
                skipped_count = 0
                for doc in documents:
                    document_id = doc.get("id")
                    doc_name = doc.get("name", "")
                    doc_type = doc.get("type", "")
                    doc_status, _ = get_doc_status(doc)
                    
                    # 构建路径
                    if folder_path and folder_path != "根目录":
                        full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                    else:
                        full_path = f"{dataset_name}/{doc_name}"
                    
                    # 如果只处理失败记录模式
                    if PROCESS_ONLY_FAILED_RECORD:
                        # 只处理在失败记录中的文档
                        if not is_in_failed_records(document_id):
                            continue
                    else:
                        # 正常模式：检查是否应该跳过
                        if doc_status not in RETRY_STATUS:
                            continue
                        
                        if not should_process_file(doc_type):
                            continue
                        
                        # 超长路径跳过
                        if len(full_path) > MAX_PATH_LENGTH:
                            continue
                        
                        # 如果启用了跳过失败记录，且文档在失败记录中，则跳过
                        if SKIP_RECORDED_FAILED and is_in_failed_records(document_id):
                            skipped_count += 1
                            continue
                    
                    all_docs.append({
                        'dataset_id': dataset_id,
                        'document_id': doc.get("id"),
                        'name': doc_name,
                        'type': doc_type,
                        'path': full_path,
                        'workspace_id': ws_id,
                    })
                    found_count += 1
                
                if found_count > 0:
                    if skipped_count > 0:
                        print(f"- 发现 {found_count} 个（跳过已失败 {skipped_count} 个）")
                    else:
                        print(f"- 发现 {found_count} 个")
                else:
                    if skipped_count > 0:
                        print(f"- 无需处理（跳过已失败 {skipped_count} 个）")
                    else:
                        print("- 无需处理")
                    
            except Exception as e:
                print(f"- 出错: {e}")
                time.sleep(RETRY_DELAY)
    
    return all_docs


def run_batch_mode():
    """批次模式：启动N个任务，等待一段时间，继续下一批"""
    from datetime import datetime
    
    start_time = datetime.now()
    
    print("="*60)
    print(f"失败/无任务文档重试工具（批次模式）")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print_config()
    
    # 统计
    total_success = 0
    total_fail = 0
    total_started = 0
    batch_num = 1
    batch_count = 0
    
    # 记录
    success_docs = []
    failed_docs = []
    
    # 遍历所有工作空间
    for ws_id, ws_name in workspace_ids:
        print(f"\n正在扫描 [{ws_name}] 的知识库...")
        
        datasets_to_process = []
        other_datasets = []
        
        if ONLY_TARGET_FOLDER and TARGET_FOLDER_PATH:
            # 仅处理 TARGET_FOLDER_PATH 下的文件
            print(f"仅处理目标路径: {TARGET_FOLDER_PATH}")
            try:
                status, all_datasets = dataset_api.list_datasets(ws_id)
                if status == 200:
                    for ds in all_datasets:
                        folder_id = ds.get("folder_id")
                        folder_path = get_folder_path(folder_id)
                        if TARGET_FOLDER_PATH in folder_path:
                            other_datasets.append(ds)
                    print(f"找到 {len(other_datasets)} 个知识库（路径包含 {TARGET_FOLDER_PATH}）")
            except Exception as e:
                print(f"获取知识库列表失败: {e}")
        elif PRIORITY_FOLDER_IDS:
            print(f"优先处理 {len(PRIORITY_FOLDER_IDS)} 个文件夹:")
            
            for folder_id in PRIORITY_FOLDER_IDS:
                priority_folder_path = get_folder_path(folder_id)
                print(f"  - {priority_folder_path} (ID: {folder_id})")
                
                try:
                    status, priority_datasets = dataset_api.list_datasets(ws_id, folder_id=folder_id)
                    if status == 200:
                        datasets_to_process.extend(priority_datasets)
                        print(f"    找到 {len(priority_datasets)} 个知识库")
                except Exception as e:
                    print(f"    获取知识库失败: {e}")
        
        # 如果需要处理其他文件夹（非 ONLY_TARGET_FOLDER 模式时）
        if not ONLY_TARGET_FOLDER and not ONLY_PRIORITY_FOLDER:
            try:
                status, all_datasets = dataset_api.list_datasets(ws_id)
                if status == 200:
                    # 过滤掉已经在优先列表中的知识库
                    priority_dataset_ids = {ds.get("id") for ds in datasets_to_process}
                    for ds in all_datasets:
                        if ds.get("id") not in priority_dataset_ids:
                            folder_id = ds.get("folder_id")
                            folder_path = get_folder_path(folder_id)
                            # 如果设置了TARGET_FOLDER_PATH，需要匹配路径
                            if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                                continue
                            other_datasets.append(ds)
                    print(f"其他文件夹找到 {len(other_datasets)} 个知识库")
            except Exception as e:
                print(f"获取其他知识库列表失败: {e}")
        
        # 合并列表：优先文件夹在前
        all_datasets_list = datasets_to_process + other_datasets
        
        if not all_datasets_list:
            print("没有找到需要处理的知识库")
            continue
        
        print(f"总共需要处理 {len(all_datasets_list)} 个知识库")
        
        for i, ds in enumerate(all_datasets_list):
            dataset_id = ds.get("id")
            dataset_name = ds.get("name")
            folder_id = ds.get("folder_id")
            folder_path = get_folder_path(folder_id)
            
            # 如果设置了TARGET_FOLDER_PATH且不在优先文件夹中，需要匹配路径
            if not PRIORITY_FOLDER_IDS or folder_id not in PRIORITY_FOLDER_IDS:
                if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                    continue
            
            is_priority = folder_id in PRIORITY_FOLDER_IDS if PRIORITY_FOLDER_IDS else False
            prefix = "[优先]" if is_priority else ""
            print(f"\n{prefix}[{i+1}/{len(all_datasets_list)}] 扫描知识库: {dataset_name}")
            
            try:
                status, documents = list_documents_with_retry(dataset_id, ws_id)
                if status != 200:
                    print(f"  获取文档失败")
                    continue
                
                found_count = 0
                skipped_count = 0
                for doc in documents:
                    document_id = doc.get("id")
                    doc_name = doc.get("name", "")
                    doc_type = doc.get("type", "")
                    doc_status, _ = get_doc_status(doc)
                    
                    # 构建路径
                    if folder_path and folder_path != "根目录":
                        full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                    else:
                        full_path = f"{dataset_name}/{doc_name}"
                    
                    # 如果只处理失败记录模式
                    if PROCESS_ONLY_FAILED_RECORD:
                        # 只处理在失败记录中的文档
                        if not is_in_failed_records(document_id):
                            continue
                    else:
                        # 正常模式：检查是否应该跳过
                        if doc_status not in RETRY_STATUS:
                            continue
                        
                        if not should_process_file(doc_type):
                            continue
                        
                        # 超长路径跳过
                        if len(full_path) > MAX_PATH_LENGTH:
                            continue
                        
                        # 如果启用了跳过失败记录，且文档在失败记录中，则跳过
                        if SKIP_RECORDED_FAILED and is_in_failed_records(document_id):
                            skipped_count += 1
                            continue
                    
                    found_count += 1
                    total_started += 1
                    batch_count += 1
                    
                    print(f"\n  [批次{batch_num}][{batch_count}/{BATCH_SIZE}] 启动: {doc_name} [type={doc_type}]")
                    print(f"    路径: {full_path}")
                    
                    # 启动任务
                    success, result = start_task({
                        'dataset_id': dataset_id,
                        'document_id': document_id,
                    }, ws_id)
                    
                    if success:
                        print(f"    ✓ 成功")
                        total_success += 1
                        success_docs.append({
                            'name': doc_name,
                            'path': full_path,
                            'type': doc_type,
                        })
                    else:
                        print(f"    ✗ 失败: {result}")
                        total_fail += 1
                        error_msg = str(result)
                        failed_docs.append({
                            'name': doc_name,
                            'path': full_path,
                            'type': doc_type,
                            'error': error_msg,
                        })
                        # 记录失败
                        if ENABLE_FAILED_RECORD:
                            add_failed_record(document_id, doc_name, full_path, doc_type, error_msg)
                    
                    # 请求间隔
                    time.sleep(REQUEST_INTERVAL)
                    
                    # 批次满了，等待
                    if batch_count >= BATCH_SIZE:
                        print(f"\n{'='*60}")
                        print(f"第 {batch_num} 批完成！成功: {total_success}, 失败: {total_fail}")
                        print(f"等待 {BATCH_WAIT} 秒后继续...")
                        print(f"{'='*60}")
                        time.sleep(BATCH_WAIT)
                        batch_num += 1
                        batch_count = 0
                
                if found_count > 0:
                    if skipped_count > 0:
                        print(f"\n  知识库 [{dataset_name}] 处理了 {found_count} 个文档（跳过已失败 {skipped_count} 个）")
                    else:
                        print(f"\n  知识库 [{dataset_name}] 处理了 {found_count} 个文档")
                else:
                    if skipped_count > 0:
                        print(f"  无需处理（跳过已失败 {skipped_count} 个）")
                    else:
                        print(f"  无需处理")
                    
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
    print(f"  启动任务数: {total_started}")
    print(f"  成功: {total_success}")
    print(f"  失败: {total_fail}")
    if total_started > 0:
        success_rate = total_success / total_started * 100
        print(f"  成功率: {success_rate:.1f}%")
    
    # 显示失败列表
    if failed_docs:
        print(f"\n{'='*60}")
        print(f"失败文档列表 ({len(failed_docs)} 个):")
        print(f"{'='*60}")
        for doc in failed_docs[:50]:
            print(f"  {doc['path']}")
            print(f"    错误: {doc['error']}")
        if len(failed_docs) > 50:
            print(f"  ... 还有 {len(failed_docs) - 50} 个")
    
    print(f"{'='*60}")


def run_polling_mode():
    """轮询模式：边扫描边处理，始终保持N个任务在运行"""
    from datetime import datetime
    
    start_time = datetime.now()
    
    print("="*60)
    print(f"失败/无任务文档重试工具（轮询模式）")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print_config()
    
    print("\n" + "="*60)
    print("边扫描边处理模式")
    print(f"窗口大小: {WINDOW_SIZE}, 轮询间隔: {POLL_INTERVAL}秒")
    print("="*60)
    
    running_tasks = {}  # document_id -> {doc_info, start_time}
    
    total_success = 0
    total_fail = 0
    processed_count = 0
    scanned_datasets = 0
    
    success_docs = []
    failed_docs = []
    
    # 遍历所有工作空间
    for ws_id, ws_name in workspace_ids:
        print(f"\n正在扫描 [{ws_name}] 的知识库...")
        
        datasets_to_process = []
        other_datasets = []
        
        if ONLY_TARGET_FOLDER and TARGET_FOLDER_PATH:
            # 仅处理 TARGET_FOLDER_PATH 下的文件
            print(f"仅处理目标路径: {TARGET_FOLDER_PATH}")
            try:
                status, all_datasets = dataset_api.list_datasets(ws_id)
                if status == 200:
                    for ds in all_datasets:
                        folder_id = ds.get("folder_id")
                        folder_path = get_folder_path(folder_id)
                        if TARGET_FOLDER_PATH in folder_path:
                            other_datasets.append(ds)
                    print(f"找到 {len(other_datasets)} 个知识库（路径包含 {TARGET_FOLDER_PATH}）")
            except Exception as e:
                print(f"获取知识库列表失败: {e}")
        elif PRIORITY_FOLDER_IDS:
            print(f"优先处理 {len(PRIORITY_FOLDER_IDS)} 个文件夹:")
            
            for folder_id in PRIORITY_FOLDER_IDS:
                priority_folder_path = get_folder_path(folder_id)
                print(f"  - {priority_folder_path} (ID: {folder_id})")
                
                try:
                    status, priority_datasets = dataset_api.list_datasets(ws_id, folder_id=folder_id)
                    if status == 200:
                        datasets_to_process.extend(priority_datasets)
                        print(f"    找到 {len(priority_datasets)} 个知识库")
                except Exception as e:
                    print(f"    获取知识库失败: {e}")
        
        # 如果需要处理其他文件夹（非 ONLY_TARGET_FOLDER 模式时）
        if not ONLY_TARGET_FOLDER and not ONLY_PRIORITY_FOLDER:
            try:
                status, all_datasets = dataset_api.list_datasets(ws_id)
                if status == 200:
                    # 过滤掉已经在优先列表中的知识库
                    priority_dataset_ids = {ds.get("id") for ds in datasets_to_process}
                    for ds in all_datasets:
                        if ds.get("id") not in priority_dataset_ids:
                            folder_id = ds.get("folder_id")
                            folder_path = get_folder_path(folder_id)
                            # 如果设置了TARGET_FOLDER_PATH，需要匹配路径
                            if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                                continue
                            other_datasets.append(ds)
                    print(f"其他文件夹找到 {len(other_datasets)} 个知识库")
            except Exception as e:
                print(f"获取其他知识库列表失败: {e}")
        
        # 合并列表：优先文件夹在前
        all_datasets_list = datasets_to_process + other_datasets
        
        if not all_datasets_list:
            print("没有找到需要处理的知识库")
            continue
        
        print(f"总共需要处理 {len(all_datasets_list)} 个知识库")
        
        # 逐个扫描知识库并处理
        for i, ds in enumerate(all_datasets_list):
            dataset_id = ds.get("id")
            dataset_name = ds.get("name")
            folder_id = ds.get("folder_id")
            folder_path = get_folder_path(folder_id)
            
            # 如果设置了TARGET_FOLDER_PATH且不在优先文件夹中，需要匹配路径
            if not PRIORITY_FOLDER_IDS or folder_id not in PRIORITY_FOLDER_IDS:
                if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                    continue
            
            is_priority = folder_id in PRIORITY_FOLDER_IDS if PRIORITY_FOLDER_IDS else False
            prefix = "[优先]" if is_priority else ""
            scanned_datasets += 1
            print(f"\n{prefix}[知识库 {scanned_datasets}/{len(all_datasets_list)}] 扫描: {dataset_name}")
            
            try:
                status, documents = list_documents_with_retry(dataset_id, ws_id)
                if status != 200:
                    print("  获取文档失败")
                    continue
                
                # 收集该知识库中需要处理的文档
                docs_in_dataset = []
                skipped_count = 0
                for doc in documents:
                    document_id = doc.get("id")
                    doc_name = doc.get("name", "")
                    doc_type = doc.get("type", "")
                    doc_status, _ = get_doc_status(doc)
                    
                    # 构建路径
                    if folder_path and folder_path != "根目录":
                        full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                    else:
                        full_path = f"{dataset_name}/{doc_name}"
                    
                    # 如果只处理失败记录模式
                    if PROCESS_ONLY_FAILED_RECORD:
                        # 只处理在失败记录中的文档
                        if not is_in_failed_records(document_id):
                            continue
                    else:
                        # 正常模式：检查是否应该跳过
                        if doc_status not in RETRY_STATUS:
                            continue
                        
                        if not should_process_file(doc_type):
                            continue
                        
                        # 超长路径跳过
                        if len(full_path) > MAX_PATH_LENGTH:
                            continue
                        
                        # 如果启用了跳过失败记录，且文档在失败记录中，则跳过
                        if SKIP_RECORDED_FAILED and is_in_failed_records(document_id):
                            skipped_count += 1
                            continue
                    
                    docs_in_dataset.append({
                        'dataset_id': dataset_id,
                        'document_id': doc.get("id"),
                        'name': doc_name,
                        'type': doc_type,
                        'path': full_path,
                        'workspace_id': ws_id,
                    })
                
                if not docs_in_dataset:
                    if skipped_count > 0:
                        print(f"  无需处理的文档（跳过已失败 {skipped_count} 个）")
                    else:
                        print("  无需处理的文档")
                    continue
                
                if skipped_count > 0:
                    print(f"  发现 {len(docs_in_dataset)} 个待处理文档（跳过已失败 {skipped_count} 个）")
                else:
                    print(f"  发现 {len(docs_in_dataset)} 个待处理文档")
                
                # 逐个启动该知识库的文档，并维护滑动窗口
                for doc in docs_in_dataset:
                    # 填充窗口：如果窗口未满，直接启动
                    while len(running_tasks) >= WINDOW_SIZE:
                        # 窗口已满，等待有任务完成
                        completed_ids = []
                        timeout_ids = []
                        
                        for doc_id, task_info in list(running_tasks.items()):
                            task_doc = task_info['doc']
                            start_time_task = task_info['start_time']
                            elapsed = time.time() - start_time_task
                            
                            # 超时检查
                            if elapsed > MAX_WAIT_TIME:
                                timeout_ids.append(doc_id)
                                print(f"  ⏱ 超时: {task_doc['name']} ({int(elapsed)}秒)")
                                continue
                            
                            # 获取最新状态
                            success_check, doc_info = get_document_info(task_doc['dataset_id'], doc_id)
                            if not success_check:
                                continue
                            
                            doc_status, _ = get_doc_status(doc_info)
                            
                            if doc_status in ["completed", "success"]:
                                completed_ids.append((doc_id, True))
                                print(f"  ✓ 完成: {task_doc['name']} ({int(elapsed)}秒)")
                            elif doc_status in ["failed", "error"]:
                                completed_ids.append((doc_id, False))
                                print(f"  ✗ 失败: {task_doc['name']}")
                        
                        # 处理完成的任务
                        for doc_id, is_success in completed_ids:
                            task_doc = running_tasks[doc_id]['doc']
                            del running_tasks[doc_id]
                            if is_success:
                                total_success += 1
                                success_docs.append({
                                    'name': task_doc['name'],
                                    'path': task_doc['path'],
                                    'type': task_doc['type'],
                                })
                            else:
                                total_fail += 1
                                error_msg = '任务执行失败'
                                failed_docs.append({
                                    'name': task_doc['name'],
                                    'path': task_doc['path'],
                                    'type': task_doc['type'],
                                    'error': error_msg,
                                })
                                # 记录失败
                                if ENABLE_FAILED_RECORD:
                                    add_failed_record(doc_id, task_doc['name'], task_doc['path'], task_doc['type'], error_msg)
                        
                        # 处理超时的任务
                        for doc_id in timeout_ids:
                            task_doc = running_tasks[doc_id]['doc']
                            del running_tasks[doc_id]
                            total_fail += 1
                            error_msg = f'超时({MAX_WAIT_TIME}秒)'
                            failed_docs.append({
                                'name': task_doc['name'],
                                'path': task_doc['path'],
                                'type': task_doc['type'],
                                'error': error_msg,
                            })
                            # 记录失败
                            if ENABLE_FAILED_RECORD:
                                add_failed_record(doc_id, task_doc['name'], task_doc['path'], task_doc['type'], error_msg)
                        
                        # 如果没有任何任务完成或超时，等待一段时间
                        if not completed_ids and not timeout_ids:
                            print(f"  等待窗口释放... 运行中: {len(running_tasks)}")
                            time.sleep(POLL_INTERVAL)
                    
                    # 现在窗口有空位，启动新任务
                    document_id = doc['document_id']
                    processed_count += 1
                    
                    print(f"  [{processed_count}] 启动: {doc['name']} [type={doc['type']}]")
                    
                    success, result = start_task(doc, doc['workspace_id'])
                    
                    if success:
                        running_tasks[document_id] = {
                            'doc': doc,
                            'start_time': time.time()
                        }
                        print(f"    ✓ 已启动，当前运行中: {len(running_tasks)}")
                    else:
                        print(f"    ✗ 启动失败: {result}")
                        total_fail += 1
                        error_msg = str(result)
                        failed_docs.append({
                            'name': doc['name'],
                            'path': doc['path'],
                            'type': doc['type'],
                            'error': error_msg,
                        })
                        # 记录失败
                        if ENABLE_FAILED_RECORD:
                            add_failed_record(document_id, doc['name'], doc['path'], doc['type'], error_msg)
                    
                    time.sleep(REQUEST_INTERVAL)
                
            except Exception as e:
                print(f"  出错: {e}")
                time.sleep(RETRY_DELAY)
    
    # 等待所有剩余任务完成
    print(f"\n{'='*60}")
    print(f"所有知识库已扫描完成，等待剩余 {len(running_tasks)} 个任务完成...")
    print(f"{'='*60}")
    
    while running_tasks:
        completed_ids = []
        timeout_ids = []
        
        for doc_id, task_info in list(running_tasks.items()):
            doc = task_info['doc']
            start_time_task = task_info['start_time']
            elapsed = time.time() - start_time_task
            
            # 超时检查
            if elapsed > MAX_WAIT_TIME:
                timeout_ids.append(doc_id)
                print(f"  ⏱ 超时: {doc['name']} ({int(elapsed)}秒)")
                continue
            
            # 获取最新状态
            success, doc_info = get_document_info(doc['dataset_id'], doc_id)
            if not success:
                continue
            
            doc_status, _ = get_doc_status(doc_info)
            
            if doc_status in ["completed", "success"]:
                completed_ids.append((doc_id, True))
                print(f"  ✓ 完成: {doc['name']} ({int(elapsed)}秒)")
            elif doc_status in ["failed", "error"]:
                completed_ids.append((doc_id, False))
                print(f"  ✗ 失败: {doc['name']}")
        
        # 处理完成的任务
        for doc_id, is_success in completed_ids:
            doc = running_tasks[doc_id]['doc']
            del running_tasks[doc_id]
            if is_success:
                total_success += 1
                success_docs.append({
                    'name': doc['name'],
                    'path': doc['path'],
                    'type': doc['type'],
                })
            else:
                total_fail += 1
                error_msg = '任务执行失败'
                failed_docs.append({
                    'name': doc['name'],
                    'path': doc['path'],
                    'type': doc['type'],
                    'error': error_msg,
                })
                # 记录失败
                if ENABLE_FAILED_RECORD:
                    add_failed_record(doc_id, doc['name'], doc['path'], doc['type'], error_msg)
        
        # 处理超时的任务
        for doc_id in timeout_ids:
            doc = running_tasks[doc_id]['doc']
            del running_tasks[doc_id]
            total_fail += 1
            error_msg = f'超时({MAX_WAIT_TIME}秒)'
            failed_docs.append({
                'name': doc['name'],
                'path': doc['path'],
                'type': doc['type'],
                'error': error_msg,
            })
            # 记录失败
            if ENABLE_FAILED_RECORD:
                add_failed_record(doc_id, doc['name'], doc['path'], doc['type'], error_msg)
        
        # 显示状态
        if running_tasks:
            running = len(running_tasks)
            print(f"  状态: 运行中 {running}, 成功 {total_success}, 失败 {total_fail}")
            time.sleep(POLL_INTERVAL)
    
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
    print(f"  处理文档数: {processed_count}")
    print(f"  成功: {total_success}")
    print(f"  失败: {total_fail}")
    if processed_count > 0:
        success_rate = total_success / processed_count * 100
        print(f"  成功率: {success_rate:.1f}%")
    
    # 显示失败列表
    if failed_docs:
        print(f"\n{'='*60}")
        print(f"失败文档列表 ({len(failed_docs)} 个):")
        print(f"{'='*60}")
        for doc in failed_docs[:50]:
            print(f"  {doc['path']}")
            print(f"    错误: {doc['error']}")
        if len(failed_docs) > 50:
            print(f"  ... 还有 {len(failed_docs) - 50} 个")
    
    print(f"{'='*60}")


def main():
    # 加载失败记录
    load_failed_records()
    
    # 记录启动时的失败数量
    initial_failed_count = len(failed_records)
    
    try:
        if RUN_MODE == 'polling':
            run_polling_mode()
        else:
            run_batch_mode()
    finally:
        # 计算新增失败记录
        new_failed_count = len(failed_records) - initial_failed_count
        
        # 保存失败记录
        if new_failed_count > 0:
            print(f"\n⚠️  本次运行新增 {new_failed_count} 条失败记录")
        
        save_failed_records()


if __name__ == "__main__":
    main()
