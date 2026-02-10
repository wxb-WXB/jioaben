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
from src.config import API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACE_NAME, LLM_CONFIG, PRIORITY_FOLDER_IDS, ONLY_PRIORITY_FOLDER

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
        
        log.info(f"      文件夹: {folder_path}")
        log.info(f"      文档: {document_name}")
        log.info(f"      共 {len(segments)} 个分段")
        
        for idx, segment in enumerate(segments, 1):
            if not isinstance(segment, dict):
                continue
            
            segment_id = segment.get("id")
            if not segment_id:
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
            
            for attempt in range(1, MAX_RETRIES + 1):
                gen_success, message = regenerate_segment_index(dataset_id, document_id, segment_id)
                
                if gen_success:
                    log.info(f"        [成功] {message}")
                    total_success += 1
                    break
                else:
                    log.warning(f"        [失败] 第{attempt}次: {message}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_INTERVAL)
                    else:
                        log.error(f"        [失败] 已达最大重试次数")
                        total_fail += 1
            
            time.sleep(REQUEST_INTERVAL)
        
        return total_success, total_fail, f"跳过(已有索引): {total_skip}"
    
    except Exception as e:
        log.error(f"处理文档分段出错: {e}")
        return 0, 0, f"出错: {e}"


def scan_and_generate(workspace_id, workspace_name):
    """扫描知识库，为向量化成功的文档生成分段索引"""
    log.info(f"正在扫描 [{workspace_name}] 的知识库...")
    
    # 如果指定了优先文件夹，先处理优先文件夹
    datasets_to_process = []
    other_datasets = []
    
    if PRIORITY_FOLDER_IDS:
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
    
    # 如果需要处理其他文件夹
    if not ONLY_PRIORITY_FOLDER:
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
    log.info("=" * 60)
    log.info("分段索引生成工具（标题、摘要、问题）")
    log.info(f"模式: 逐个处理（成功一个再下一个）")
    log.info(f"每个分段成功后间隔: {REQUEST_INTERVAL} 秒")
    log.info(f"失败重试次数: {MAX_RETRIES}, 重试间隔: {RETRY_INTERVAL} 秒")
    
    if PRIORITY_FOLDER_IDS:
        log.info(f"优先文件夹数量: {len(PRIORITY_FOLDER_IDS)}")
        for folder_id in PRIORITY_FOLDER_IDS:
            priority_folder_path = get_folder_path(folder_id)
            log.info(f"  - {priority_folder_path} (ID: {folder_id})")
        log.info(f"只处理优先文件夹: {'是' if ONLY_PRIORITY_FOLDER else '否'}")
    
    log.info("=" * 60)
    
    start_time = datetime.now()
    
    success, fail = scan_and_generate(WORKSPACE_ID, WORKSPACE_NAME)
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    log.info("")
    log.info("=" * 60)
    log.info("全部完成！")
    log.info(f"成功: {success}, 失败: {fail}")
    log.info(f"总耗时: {duration}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
