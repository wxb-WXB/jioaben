# -*- coding: utf-8 -*-
"""
生成分中索引脚本（标题、摘要、问题）

功能：
- 扫描知识库中向量化成功的文档
- 获取每个文档的分段列表
- 为每个分段生成标题、摘要、问题

使用方法：
python scripts/generate/segment_index.py
"""
import sys
import time
import os
import requests
import logging
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
from src.config import (
    API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACE_NAME, LLM_CONFIG,
    PRIORITY_FOLDER_IDS, ONLY_PRIORITY_FOLDER,
    TARGET_FOLDER_PATH, ONLY_TARGET_FOLDER,
    FAILED_RECORDS_DIR,
)
import json

# ============== 配置区域 ==============
# LLM 配置（用于生成标题、摘要、问题）
GENERATE_CONFIG = {
    "title": LLM_CONFIG.copy(),
    "summary": LLM_CONFIG.copy(),
    "question": LLM_CONFIG.copy()
}

# 处理配置
REQUEST_INTERVAL = 2   # 每个分段成功后等待的时间（秒）
MAX_RETRIES = 3        # 单个分段最大重试次数
RETRY_INTERVAL = 10    # 重试间隔（秒）

# 失败记录配置
ENABLE_FAILED_RECORD = True          # 是否启用失败记录功能
SKIP_RECORDED_FAILED = True          # 是否跳过已记录的失败分段
FAILED_RECORD_FILE = os.path.join(FAILED_RECORDS_DIR, "segment_index_failed.json")  # 失败记录文件路径

# 优先处理的文件夹ID配置已移至 src/config.py
# 可通过修改 config.py 中的 PRIORITY_FOLDER_IDS 和 ONLY_PRIORITY_FOLDER 来调整优先级
# ============== 配置结束 ==============

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# 禁用 SSL 警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

dataset_api = LingyanDataset(API_KEY)

# 失败记录缓存（segment_id -> 失败信息）
failed_records = {}


def load_failed_records():
    """加载失败记录"""
    global failed_records
    if not ENABLE_FAILED_RECORD:
        return
    
    if os.path.exists(FAILED_RECORD_FILE):
        try:
            with open(FAILED_RECORD_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                failed_records = data.get('failed_segments', {})
                log.info("=" * 60)
                log.info(f"已加载 {len(failed_records)} 条失败记录")
                if failed_records:
                    updated_at = data.get('updated_at', '未知')
                    log.info(f"最后更新: {updated_at}")
                    log.info(f"失败记录文件: {FAILED_RECORD_FILE}")
                    if SKIP_RECORDED_FAILED:
                        log.info(f"⚠️  这些分段将被跳过，不会重新处理")
                log.info("=" * 60)
        except Exception as e:
            log.error(f"加载失败记录出错: {e}")
            failed_records = {}
    else:
        log.info("未找到失败记录文件，将创建新的记录")
        failed_records = {}


def save_failed_records():
    """保存失败记录（立即保存）"""
    if not ENABLE_FAILED_RECORD:
        return
    
    try:
        os.makedirs(os.path.dirname(FAILED_RECORD_FILE), exist_ok=True)
        with open(FAILED_RECORD_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_failed': len(failed_records),
                'failed_segments': failed_records
            }, f, ensure_ascii=False, indent=2)
        log.info(f"✓ 失败记录已保存: {len(failed_records)} 条")
    except Exception as e:
        log.error(f"保存失败记录出错: {e}")


def is_in_failed_records(segment_id):
    """检查分段是否在失败记录中"""
    return segment_id in failed_records


def add_failed_record(segment_id, doc_name, doc_path, segment_content, error_msg):
    """添加失败记录并立即保存"""
    global failed_records
    failed_records[segment_id] = {
        'document_name': doc_name,
        'document_path': doc_path,
        'segment_content': segment_content[:50],
        'error': error_msg,
        'failed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    # 立即保存，确保即使脚本中断也能记录
    save_failed_records()


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


def is_vector_success(doc):
    """判断文档是否向量化成功"""
    tasks = doc.get("tasks", [])
    for task in tasks:
        if task.get("type") == "normal" and task.get("status") in ["completed", "success"]:
            return True
    return False


def get_document_segments(dataset_id, document_id):
    """获取文档的分段列表"""
    url = f"https://ai.yxgswater.com:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/segments"
    
    all_segments = []
    page = 1
    
    while True:
        params = {
            "dataset_id": dataset_id,
            "document_id": document_id,
            "page": page,
            "page_size": 100
        }
        
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=60, verify=False)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 200:
                    data = result.get("data", {})
                    if isinstance(data, dict):
                        segments = data.get("list", [])
                    elif isinstance(data, list):
                        segments = data
                    else:
                        segments = []
                    
                    if not segments:
                        break
                    
                    valid_segments = [s for s in segments if isinstance(s, dict) and s.get("id")]
                    all_segments.extend(valid_segments)
                    
                    if len(segments) < 100:
                        break
                    
                    page += 1
                else:
                    break
            else:
                break
        except Exception as e:
            log.error(f"获取分段列表失败: {e}")
            break
    
    return all_segments


def get_segment_index_tasks(dataset_id, document_id):
    """获取分段索引任务状态"""
    url = f"https://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/segment-index-tasks"
    
    params = {
        "dataset_id": dataset_id,
        "document_id": document_id,
        "page": 1,
        "page_size": 1000
    }
    
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=60, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                data = result.get("data", [])
                
                status_map = {}
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    
                    seg_id = item.get("segment_id")
                    if not seg_id:
                        continue
                    
                    tasks = item.get("tasks", [])
                    if not isinstance(tasks, list):
                        continue
                    
                    task_status = {}
                    for task in tasks:
                        if isinstance(task, dict):
                            task_type = task.get("type")
                            task_stat = task.get("status")
                            if task_type:
                                task_status[task_type] = task_stat
                    
                    status_map[seg_id] = task_status
                
                return True, status_map
    except Exception as e:
        log.error(f"获取分段索引任务状态失败: {e}")
        return False, str(e)
    
    return False, "获取失败"


def regenerate_segment_index(dataset_id, document_id, segment_id):
    """为单个分段生成索引（标题、摘要、问题）"""
    url = f"https://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/segments/{segment_id}/indexes/regenerate"
    
    params = {
        "dataset_id": dataset_id,
        "document_id": document_id,
        "segment_id": segment_id
    }
    
    payload = {
        "dataset_id": dataset_id,
        "document_id": document_id,
        "segment_id": segment_id,
        "generate_config": GENERATE_CONFIG
    }
    
    try:
        response = requests.post(url, params=params, headers=HEADERS, json=payload, timeout=120, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                data = result.get("data", [])
                generated = []
                for item in data:
                    item_type = item.get("type")
                    content = item.get("content", "")
                    if content:
                        generated.append(item_type)
                
                return True, f"生成成功: {', '.join(generated)}"
            else:
                return False, f"API错误: {result.get('msg')}"
        else:
            return False, f"https {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "请求超时"
    except Exception as e:
        return False, f"异常: {str(e)}"


def process_document_segments(dataset_id, document_id, document_name, folder_path):
    """处理单个文档的所有分段"""
    try:
        segments = get_document_segments(dataset_id, document_id)
        
        if not segments:
            return 0, 0, "无分段"
        
        success, status_map = get_segment_index_tasks(dataset_id, document_id)
        if not success:
            status_map = {}
        
        total_success = 0
        total_fail = 0
        total_skip = 0
        total_failed_skip = 0
        
        # 构建完整路径
        full_path = f"{folder_path}/{document_name}" if folder_path and folder_path != "根目录" else document_name
        
        log.info(f"      文件夹: {folder_path}")
        log.info(f"      文档: {document_name}")
        log.info(f"      共 {len(segments)} 个分段")
        
        for idx, segment in enumerate(segments, 1):
            if not isinstance(segment, dict):
                continue
            
            segment_id = segment.get("id")
            if not segment_id:
                continue
            
            # 如果在失败记录中，跳过
            if SKIP_RECORDED_FAILED and is_in_failed_records(segment_id):
                total_failed_skip += 1
                continue
            
            segment_content = str(segment.get("content", ""))[:30]
            
            seg_status = status_map.get(segment_id, {}) if isinstance(status_map, dict) else {}
            title_status = seg_status.get("title", "")
            summary_status = seg_status.get("summary", "")
            question_status = seg_status.get("question", "")
            
            all_success = (
                title_status == "success" and
                summary_status == "success" and
                question_status == "success"
            )
            
            if all_success:
                total_skip += 1
                continue
            
            status_info = []
            if title_status and title_status != "success":
                status_info.append(f"标题:{title_status}")
            if summary_status and summary_status != "success":
                status_info.append(f"摘要:{summary_status}")
            if question_status and question_status != "success":
                status_info.append(f"问题:{question_status}")
            
            if status_info:
                log.info(f"      [{idx}/{len(segments)}] [{folder_path}] 重新生成({', '.join(status_info)}): {segment_content}...")
            else:
                log.info(f"      [{idx}/{len(segments)}] [{folder_path}] 生成索引: {segment_content}...")
            
            final_success = False
            final_error_msg = ""
            for attempt in range(1, MAX_RETRIES + 1):
                gen_success, message = regenerate_segment_index(dataset_id, document_id, segment_id)
                
                if gen_success:
                    log.info(f"        [成功] {message}")
                    total_success += 1
                    final_success = True
                    break
                else:
                    final_error_msg = message
                    log.warning(f"        [失败] 第{attempt}次: {message}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_INTERVAL)
                    else:
                        log.error(f"        [失败] 已达最大重试次数")
                        total_fail += 1
            
            # 如果最终失败，记录
            if not final_success and ENABLE_FAILED_RECORD:
                add_failed_record(
                    segment_id,
                    document_name,
                    full_path,
                    segment_content,
                    final_error_msg
                )
            
            time.sleep(REQUEST_INTERVAL)
        
        skip_msg = f"跳过(已有索引): {total_skip}"
        if total_failed_skip > 0:
            skip_msg += f", 跳过(已记录失败): {total_failed_skip}"
        return total_success, total_fail, skip_msg
    
    except Exception as e:
        log.error(f"处理文档分段出错: {e}")
        return 0, 0, f"出错: {e}"


def scan_and_generate(workspace_id, workspace_name):
    """扫描知识库，为向量化成功的文档生成分段索引"""
    log.info(f"正在扫描 [{workspace_name}] 的知识库...")
    
    datasets_to_process = []
    other_datasets = []
    
    if ONLY_TARGET_FOLDER and TARGET_FOLDER_PATH:
        # 仅处理 TARGET_FOLDER_PATH 下的文件
        log.info(f"仅处理目标路径: {TARGET_FOLDER_PATH}")
        try:
            status, all_datasets = dataset_api.list_datasets(workspace_id)
            if status == 200:
                for ds in all_datasets:
                    folder_id = ds.get("folder_id")
                    folder_path = get_folder_path(folder_id)
                    if TARGET_FOLDER_PATH in folder_path:
                        other_datasets.append(ds)
                log.info(f"找到 {len(other_datasets)} 个知识库（路径包含 {TARGET_FOLDER_PATH}）")
            else:
                log.error(f"获取知识库列表失败: {all_datasets}")
        except Exception as e:
            log.error(f"获取知识库列表失败: {e}")
    elif PRIORITY_FOLDER_IDS:
        log.info(f"优先处理 {len(PRIORITY_FOLDER_IDS)} 个文件夹:")
        
        for folder_id in PRIORITY_FOLDER_IDS:
            priority_folder_path = get_folder_path(folder_id)
            log.info(f"  - {priority_folder_path} (ID: {folder_id})")
            
            try:
                status, priority_datasets = dataset_api.list_datasets(workspace_id, folder_id=folder_id)
                if status == 200:
                    datasets_to_process.extend(priority_datasets)
                    log.info(f"    找到 {len(priority_datasets)} 个知识库")
                else:
                    log.error(f"    获取知识库失败: {priority_datasets}")
            except Exception as e:
                log.error(f"    获取知识库失败: {e}")
    
    # 如果需要处理其他文件夹（非 ONLY_TARGET_FOLDER 模式时）
    if not ONLY_TARGET_FOLDER and not ONLY_PRIORITY_FOLDER:
        try:
            status, all_datasets = dataset_api.list_datasets(workspace_id)
            if status == 200:
                # 过滤掉已经在优先列表中的知识库
                priority_dataset_ids = {ds.get("id") for ds in datasets_to_process}
                for ds in all_datasets:
                    if ds.get("id") not in priority_dataset_ids:
                        other_datasets.append(ds)
                log.info(f"其他文件夹找到 {len(other_datasets)} 个知识库")
            else:
                log.error(f"获取其他知识库列表失败: {all_datasets}")
        except Exception as e:
            log.error(f"获取其他知识库列表失败: {e}")
    
    # 合并列表：优先文件夹在前
    all_datasets_list = datasets_to_process + other_datasets
    
    if not all_datasets_list:
        log.warning("没有找到需要处理的知识库")
        return 0, 0
    
    log.info(f"总共需要处理 {len(all_datasets_list)} 个知识库")
    log.info("=" * 60)
    
    total_success = 0
    total_fail = 0
    
    for i, ds in enumerate(all_datasets_list):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        is_priority = folder_id in PRIORITY_FOLDER_IDS if PRIORITY_FOLDER_IDS else False
        prefix = "[优先]" if is_priority else ""
        log.info(f"\n{prefix}[{i+1}/{len(all_datasets_list)}] 扫描知识库: {dataset_name}")
        log.info(f"  目录路径: {folder_path}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id)
            if status != 200:
                log.error(f"  获取文档失败")
                continue
            
            success_docs = [doc for doc in documents if is_vector_success(doc)]
            
            if not success_docs:
                log.info(f"  无向量化成功的文档")
                continue
            
            log.info(f"  发现 {len(success_docs)} 个向量化成功的文档")
            log.info("-" * 50)
            
            for idx, doc in enumerate(success_docs, 1):
                doc_id = doc.get("id")
                doc_name = doc.get("name")
                
                log.info(f"    [{idx}/{len(success_docs)}] 文档: [{folder_path}] {doc_name}")
                
                seg_success, seg_fail, msg = process_document_segments(dataset_id, doc_id, doc_name, folder_path)
                total_success += seg_success
                total_fail += seg_fail
                
                if seg_success > 0 or seg_fail > 0:
                    log.info(f"      结果: 成功 {seg_success}, 失败 {seg_fail}, {msg}")
            
            log.info("-" * 50)
            log.info(f"  知识库 [{dataset_name}] 处理完成")
            log.info(f"  当前总计: 成功 {total_success}, 失败 {total_fail}")
                
        except Exception as e:
            log.error(f"  出错: {e}")
    
    return total_success, total_fail


def main():
    # 加载失败记录
    load_failed_records()
    
    # 记录启动时的失败数量
    initial_failed_count = len(failed_records)
    
    log.info("=" * 60)
    log.info("分段索引生成工具（标题、摘要、问题）")
    log.info(f"模式: 逐个处理（成功一个再下一个）")
    log.info(f"每个分段成功后间隔: {REQUEST_INTERVAL} 秒")
    log.info(f"失败重试次数: {MAX_RETRIES}, 重试间隔: {RETRY_INTERVAL} 秒")
    log.info(f"失败记录: {'启用' if ENABLE_FAILED_RECORD else '关闭'}")
    if ENABLE_FAILED_RECORD:
        log.info(f"  - 跳过已失败: {'是' if SKIP_RECORDED_FAILED else '否'}")
        log.info(f"  - 失败立即保存: 是")
    
    if ONLY_TARGET_FOLDER and TARGET_FOLDER_PATH:
        log.info(f"仅处理目标路径: {TARGET_FOLDER_PATH}")
    elif PRIORITY_FOLDER_IDS:
        log.info(f"优先文件夹数量: {len(PRIORITY_FOLDER_IDS)}")
        for folder_id in PRIORITY_FOLDER_IDS:
            priority_folder_path = get_folder_path(folder_id)
            log.info(f"  - {priority_folder_path} (ID: {folder_id})")
        log.info(f"只处理优先文件夹: {'是' if ONLY_PRIORITY_FOLDER else '否'}")
        if TARGET_FOLDER_PATH:
            log.info(f"路径过滤: {TARGET_FOLDER_PATH}")
    else:
        if TARGET_FOLDER_PATH:
            log.info(f"目标文件夹路径: {TARGET_FOLDER_PATH}")
        else:
            log.info(f"目标文件夹路径: 全部")
    
    log.info("=" * 60)
    
    start_time = datetime.now()
    
    try:
        success, fail = scan_and_generate(WORKSPACE_ID, WORKSPACE_NAME)
    except KeyboardInterrupt:
        log.warning("\n检测到中断信号，正在保存失败记录...")
        save_failed_records()
        log.info("失败记录已保存，程序退出")
        return
    except Exception as e:
        log.error(f"程序异常: {e}")
        save_failed_records()
        raise
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    # 计算新增失败记录
    new_failed_count = len(failed_records) - initial_failed_count
    
    log.info("")
    log.info("=" * 60)
    log.info("全部完成！")
    log.info(f"成功: {success}, 失败: {fail}")
    if new_failed_count > 0:
        log.info(f"⚠️  本次运行新增 {new_failed_count} 条失败记录")
    log.info(f"总耗时: {duration}")
    log.info("=" * 60)
    
    # 最终保存
    if new_failed_count > 0:
        log.info(f"\n失败记录文件: {FAILED_RECORD_FILE}")
        log.info(f"下次启动时将自动跳过这些失败的分段")


if __name__ == "__main__":
    main()
