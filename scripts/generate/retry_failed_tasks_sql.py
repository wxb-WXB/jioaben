# -*- coding: utf-8 -*-
"""
失败文档重试脚本（SQL版本）
===========================

功能：
- 直接查询PostgreSQL数据库，获取失败/无任务的文档
- 支持两种模式：批次模式 和 轮询模式
- 相比API版本，查询速度更快，性能更好

使用方法：
python scripts/generate/retry_failed_tasks_sql.py
"""
import sys
import time
import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

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
from src.config import API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACES

# ============================================================
# 数据库配置
# ============================================================
DB_CONFIG = {
    'host': '10.4.49.67',
    'port': 15432,
    'user': 'postgres',
    'password': 'qFVkMSfTzL2c',
    'database': 'flygpt'
}

# ============================================================
# 配置参数 - 修改这里来控制脚本行为
# ============================================================

# workspace ID 配置
# 只使用环北知识库
workspace_ids = [("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库")]

# 只处理指定目录下的知识库（为空则处理所有目录）
TARGET_FOLDER_PATH = "环北"

# ------------------------------
# 运行模式
# ------------------------------
# 'batch'   - 批次模式：启动N个任务，等待一段时间，继续下一批
# 'polling' - 轮询模式：始终保持N个任务在运行，完成一个立即补充一个
RUN_MODE = 'polling'

# ------------------------------
# 批次模式配置
# ------------------------------
BATCH_SIZE = 40          # 每批启动的任务数
BATCH_WAIT = 120         # 每批完成后等待时间（秒）
REQUEST_INTERVAL = 0.4   # 每次启动任务之间的间隔（秒）

# ------------------------------
# 轮询模式配置
# ------------------------------
WINDOW_SIZE = 30         # 同时运行的任务数量（滑动窗口大小）
POLL_INTERVAL = 5        # 检查任务状态的间隔（秒）
MAX_WAIT_TIME = 3600     # 单个任务最大等待时间（秒），超时则跳过

# ------------------------------
# 网络重试控制
# ------------------------------
MAX_RETRIES = 3          # 网络错误最大重试次数
RETRY_DELAY = 5          # 重试间隔（秒）

# ------------------------------
# 文件类型过滤（基于数据库的type字段）
# ------------------------------
INCLUDE_FILE_TYPES = {'doc', 'docx', 'txt', 'md', 'wps'}
# INCLUDE_FILE_TYPES = {'pdf'}
# INCLUDE_FILE_TYPES = None  # 处理所有类型

EXCLUDE_FILE_TYPES = None

# ------------------------------
# 文档状态过滤
# ------------------------------
RETRY_STATUS = ['error', 'failed', 'cancelled']  # no_task 会通过SQL的NOT EXISTS查询

# ------------------------------
# 向量化任务配置
# ------------------------------
SPLIT_MODE = 'common'    # 'common'(普通切割) 或 'semantic'(语义切割)
PARSE_ENHANCE = False    # 是否开启精准解析
IMAGE_TASK = False       # 是否处理图片任务

# ============================================================
# 以下为脚本逻辑
# ============================================================

# 禁用 SSL 警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

dataset_api = LingyanDataset(API_KEY)

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


def get_db_connection():
    """获取数据库连接"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return None


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


def should_process_file(doc_type):
    """判断是否应该处理该文件类型"""
    if EXCLUDE_FILE_TYPES and doc_type in EXCLUDE_FILE_TYPES:
        return False
    if INCLUDE_FILE_TYPES:
        return doc_type in INCLUDE_FILE_TYPES
    return True


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
    url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                return True, result.get("data", {})
    except:
        pass
    return False, None


def get_doc_status_from_db(doc):
    """从数据库查询结果获取任务状态"""
    # 如果有task_status字段，说明有任务
    if doc.get('task_status'):
        return doc['task_status'], doc.get('task_type')
    return 'no_task', None


def get_doc_status_from_api(doc_info):
    """从API返回的文档信息获取任务状态"""
    tasks = doc_info.get("tasks", [])
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


def print_config():
    """打印当前配置"""
    print("="*60)
    print("当前配置:")
    print("="*60)
    print(f"  数据源: PostgreSQL 数据库")
    print(f"  数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    
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
    
    print(f"  切割模式: {SPLIT_MODE}")
    print(f"  精准解析: {'开启' if PARSE_ENHANCE else '关闭'}")
    
    if INCLUDE_FILE_TYPES:
        print(f"  处理文件类型: {', '.join(sorted(INCLUDE_FILE_TYPES))}")
    else:
        print(f"  处理文件类型: 全部")
    
    print(f"  重试状态: {', '.join(RETRY_STATUS)} + no_task")
    print("="*60)


def collect_all_docs_from_db():
    """从数据库收集所有需要处理的文档"""
    conn = get_db_connection()
    if not conn:
        return []
    
    all_docs = []
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        for ws_id, ws_name in workspace_ids:
            print(f"\n正在从数据库查询 [{ws_name}] 的失败文档...")
            
            # 构建文件类型过滤条件
            type_filter = ""
            if INCLUDE_FILE_TYPES:
                types_str = "', '".join(INCLUDE_FILE_TYPES)
                type_filter = f"AND doc.type IN ('{types_str}')"
            elif EXCLUDE_FILE_TYPES:
                types_str = "', '".join(EXCLUDE_FILE_TYPES)
                type_filter = f"AND doc.type NOT IN ('{types_str}')"
            
            # 构建状态过滤条件
            status_filter = ""
            if RETRY_STATUS:
                statuses_str = "', '".join(RETRY_STATUS)
                status_filter = f"AND task.status IN ('{statuses_str}')"
            
            # SQL查询：查找失败的文档和无任务的文档
            sql = f"""
            -- 查询有失败任务的文档
            SELECT DISTINCT
                ds.id as dataset_id,
                ds.name as dataset_name,
                ds.folder_id,
                doc.id as document_id,
                doc.name as doc_name,
                doc.type as doc_type,
                task.status as task_status,
                task.type as task_type
            FROM datasets ds
            INNER JOIN documents doc ON doc.dataset_id = ds.id
            INNER JOIN document_tasks task ON task.document_id = doc.id AND task.type = 'normal'
            WHERE ds.tenant_id = '{ws_id}'
                AND doc.deleted_at IS NULL
                AND ds.deleted_at IS NULL
                {type_filter}
                {status_filter}
            
            UNION
            
            -- 查询没有normal任务的文档
            SELECT DISTINCT
                ds.id as dataset_id,
                ds.name as dataset_name,
                ds.folder_id,
                doc.id as document_id,
                doc.name as doc_name,
                doc.type as doc_type,
                NULL as task_status,
                NULL as task_type
            FROM datasets ds
            INNER JOIN documents doc ON doc.dataset_id = ds.id
            WHERE ds.tenant_id = '{ws_id}'
                AND doc.deleted_at IS NULL
                AND ds.deleted_at IS NULL
                {type_filter}
                AND NOT EXISTS (
                    SELECT 1 FROM document_tasks task
                    WHERE task.document_id = doc.id
                    AND task.type = 'normal'
                )
            
            ORDER BY dataset_name, doc_name
            """
            
            cursor.execute(sql)
            results = cursor.fetchall()
            
            print(f"查询到 {len(results)} 条记录")
            
            # 处理查询结果
            for row in results:
                dataset_name = row['dataset_name']
                folder_id = row['folder_id']
                doc_name = row['doc_name']
                doc_type = row['doc_type']
                
                # 获取文件夹路径
                folder_path = get_folder_path(folder_id)
                
                # 目录过滤
                if TARGET_FOLDER_PATH and TARGET_FOLDER_PATH not in folder_path:
                    continue
                
                # 构建完整路径
                if folder_path and folder_path != "根目录":
                    full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                else:
                    full_path = f"{dataset_name}/{doc_name}"
                
                all_docs.append({
                    'dataset_id': row['dataset_id'],
                    'document_id': row['document_id'],
                    'name': doc_name,
                    'type': doc_type,
                    'path': full_path,
                    'workspace_id': ws_id,
                    'status': row['task_status'] or 'no_task',
                    'dataset_name': dataset_name,
                })
        
        cursor.close()
        
    except Exception as e:
        print(f"数据库查询错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
    
    return all_docs


def run_batch_mode():
    """批次模式：启动N个任务，等待一段时间，继续下一批"""
    from datetime import datetime
    
    start_time = datetime.now()
    
    print("="*60)
    print(f"失败/无任务文档重试工具（批次模式 - SQL版）")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print_config()
    
    # 从数据库收集文档
    print("\n" + "="*60)
    print("从数据库收集需要处理的文档")
    print("="*60)
    
    all_docs = collect_all_docs_from_db()
    
    if not all_docs:
        print("\n没有需要处理的文档")
        return
    
    print(f"\n共收集到 {len(all_docs)} 个需要处理的文档")
    
    # 按数据集分组显示统计
    from collections import Counter
    dataset_counter = Counter([doc['dataset_name'] for doc in all_docs])
    status_counter = Counter([doc['status'] for doc in all_docs])
    
    print(f"\n状态分布:")
    for status, count in status_counter.most_common():
        print(f"  {status}: {count}")
    
    print(f"\n数据集分布 (Top 10):")
    for ds_name, count in dataset_counter.most_common(10):
        print(f"  {ds_name}: {count}")
    
    # 统计
    total_success = 0
    total_fail = 0
    total_started = 0
    batch_num = 1
    batch_count = 0
    
    # 记录
    success_docs = []
    failed_docs = []
    
    print("\n" + "="*60)
    print("开始批次处理")
    print("="*60)
    
    for doc in all_docs:
        total_started += 1
        batch_count += 1
        
        print(f"\n[批次{batch_num}][{batch_count}/{BATCH_SIZE}] 启动: {doc['name']} [type={doc['type']}, status={doc['status']}]")
        print(f"  路径: {doc['path']}")
        
        # 启动任务
        success, result = start_task(doc, doc['workspace_id'])
        
        if success:
            print(f"  ✓ 成功")
            total_success += 1
            success_docs.append(doc)
        else:
            print(f"  ✗ 失败: {result}")
            total_fail += 1
            doc['error'] = str(result)
            failed_docs.append(doc)
        
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
    """轮询模式：始终保持N个任务在运行，完成一个立即补充一个"""
    from datetime import datetime
    
    start_time = datetime.now()
    
    print("="*60)
    print(f"失败/无任务文档重试工具（轮询模式 - SQL版）")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print_config()
    
    # 从数据库收集文档
    print("\n" + "="*60)
    print("从数据库收集需要处理的文档")
    print("="*60)
    
    all_docs = collect_all_docs_from_db()
    
    if not all_docs:
        print("\n没有需要处理的文档")
        return
    
    print(f"\n共收集到 {len(all_docs)} 个需要处理的文档")
    
    # 按数据集分组显示统计
    from collections import Counter
    dataset_counter = Counter([doc['dataset_name'] for doc in all_docs])
    status_counter = Counter([doc['status'] for doc in all_docs])
    
    print(f"\n状态分布:")
    for status, count in status_counter.most_common():
        print(f"  {status}: {count}")
    
    print(f"\n数据集分布 (Top 10):")
    for ds_name, count in dataset_counter.most_common(10):
        print(f"  {ds_name}: {count}")
    
    # 第二阶段：滑动窗口处理
    print("\n" + "="*60)
    print("开始滑动窗口处理")
    print(f"窗口大小: {WINDOW_SIZE}, 轮询间隔: {POLL_INTERVAL}秒")
    print("="*60)
    
    running_tasks = {}  # document_id -> {doc_info, start_time}
    pending_docs = list(all_docs)
    
    total_success = 0
    total_fail = 0
    processed_count = 0
    total_docs = len(all_docs)
    
    success_docs = []
    failed_docs = []
    
    while pending_docs or running_tasks:
        # 填充窗口
        while len(running_tasks) < WINDOW_SIZE and pending_docs:
            doc = pending_docs.pop(0)
            document_id = doc['document_id']
            
            processed_count += 1
            print(f"\n[{processed_count}/{total_docs}] 启动: {doc['name']} [type={doc['type']}, status={doc['status']}]")
            print(f"  路径: {doc['path']}")
            
            success, result = start_task(doc, doc['workspace_id'])
            
            if success:
                running_tasks[document_id] = {
                    'doc': doc,
                    'start_time': time.time()
                }
                print(f"  ✓ 已启动，当前运行中: {len(running_tasks)}")
            else:
                print(f"  ✗ 启动失败: {result}")
                total_fail += 1
                doc['error'] = str(result)
                failed_docs.append(doc)
            
            time.sleep(REQUEST_INTERVAL)
        
        if not running_tasks:
            break
        
        # 检查运行中的任务
        completed_ids = []
        timeout_ids = []
        
        for doc_id, task_info in running_tasks.items():
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
            
            doc_status, _ = get_doc_status_from_api(doc_info)
            
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
                success_docs.append(doc)
            else:
                total_fail += 1
                doc['error'] = '任务执行失败'
                failed_docs.append(doc)
        
        # 处理超时的任务
        for doc_id in timeout_ids:
            doc = running_tasks[doc_id]['doc']
            del running_tasks[doc_id]
            total_fail += 1
            doc['error'] = f'超时({MAX_WAIT_TIME}秒)'
            failed_docs.append(doc)
        
        # 显示状态
        if running_tasks:
            remaining = len(pending_docs)
            running = len(running_tasks)
            print(f"\n  状态: 运行中 {running}, 待处理 {remaining}, 成功 {total_success}, 失败 {total_fail}")
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
    print(f"  处理文档数: {total_docs}")
    print(f"  成功: {total_success}")
    print(f"  失败: {total_fail}")
    if total_docs > 0:
        success_rate = total_success / total_docs * 100
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
    # 测试数据库连接
    print("测试数据库连接...")
    conn = get_db_connection()
    if not conn:
        print("数据库连接失败，请检查配置！")
        return
    print("数据库连接成功！")
    conn.close()
    
    # 运行主程序
    if RUN_MODE == 'polling':
        run_polling_mode()
    else:
        run_batch_mode()


if __name__ == "__main__":
    main()
