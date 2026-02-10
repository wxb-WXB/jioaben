# -*- coding: utf-8 -*-
"""
生成文档摘要脚本

功能：
- 扫描知识库中向量化成功的文档
- 调用 API 为每个文档生成摘要
- 自动跳过超过模型上下文限制的文档

使用方法：
python scripts/generate/doc_summary.py
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
from src.config import API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACE_NAME, LLM_CONFIG

# ============== 配置区域 ==============
# 处理配置
REQUEST_INTERVAL = 3  # 每个请求成功后等待的时间（秒）
MAX_RETRIES = 1       # 单个文档最大重试次数
RETRY_INTERVAL = 2    # 重试间隔（秒）
SEGMENT_CHECK_INTERVAL = 0.5  # 每次检查分段之间的间隔（秒）

# 优先处理的文件夹ID（直接指定folder_id，优先处理该文件夹下的知识库）
# 如果设置了此值，会优先处理该文件夹下的知识库，然后再处理其他文件夹
# 示例: PRIORITY_FOLDER_ID = "d9632972-a447-4dea-be8b-bb959e883ee5"
PRIORITY_FOLDER_ID = "10aab4f5-3191-4e12-a11c-2f3c4efb8204"  # 09正式稿设计图纸汇总至20260114

# 是否只处理优先文件夹（如果为True，只处理PRIORITY_FOLDER_ID指定的文件夹）
ONLY_PRIORITY_FOLDER = True
# ============== 配置结束 ==============

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

dataset_api = LingyanDataset(API_KEY)


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


def check_doc_has_summary(doc):
    """检查文档是否已有摘要"""
    summary = doc.get("summary", "")
    return summary is not None and len(str(summary).strip()) > 0


# 不可重试的错误关键词（遇到这些错误直接跳过，不重试）
SKIP_ERROR_KEYWORDS = [
    "上下文",
    "context",
    "token",
    "exceed",
    "too long",
    "maximum",
    "limit",
]


def is_skip_error(error_msg):
    """检查错误是否应该跳过（不重试）"""
    error_lower = error_msg.lower()
    for keyword in SKIP_ERROR_KEYWORDS:
        if keyword.lower() in error_lower:
            return True
    return False


def get_document_segments_count(dataset_id, document_id):
    """获取文档的分段数量"""
    url = f"https://ai.yxgswater.com:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/segments"
    
    params = {
        "dataset_id": dataset_id,
        "document_id": document_id,
        "page": 1,
        "page_size": 1  # 只需要获取total，不需要全部数据
    }
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "X-Workspace-Id": WORKSPACE_ID,
        "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                data = result.get("data", {})
                if isinstance(data, dict):
                    return data.get("total", 0)
                elif isinstance(data, list):
                    return len(data)
        return 0
    except Exception as e:
        log.warning(f"获取分段数量失败: {e}")
        return 0


def generate_summary(dataset_id, document_id, document_name):
    """调用 API 生成文档摘要"""
    url = f"https://ai.yxgswater.com:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/generate-doc-summary"
    
    params = {
        "dataset_id": dataset_id,
        "document_id": document_id
    }
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
        "X-Workspace-Id": WORKSPACE_ID,
        "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "llm_config": LLM_CONFIG
    }
    
    try:
        response = requests.post(url, params=params, headers=headers, json=payload, timeout=120, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                summary = result.get("data", {}).get("summary", "")
                if summary:
                    return True, f"摘要生成成功", summary, False
                else:
                    return False, "生成的摘要为空", "", False
            else:
                error_msg = result.get('msg', '')
                should_skip = is_skip_error(error_msg)
                return False, f"API返回错误: code={result.get('code')}, msg={error_msg}", "", should_skip
        else:
            try:
                error_detail = response.json()
                error_msg = str(error_detail)
                should_skip = is_skip_error(error_msg)
                return False, f"https {response.status_code}: {error_detail}", "", should_skip
            except:
                error_msg = response.text[:200]
                should_skip = is_skip_error(error_msg)
                return False, f"https {response.status_code}: {error_msg}", "", should_skip
            
    except requests.exceptions.Timeout:
        return False, "请求超时", "", False
    except requests.exceptions.RequestException as e:
        return False, f"请求异常: {str(e)}", "", False
    except Exception as e:
        return False, f"未知错误: {str(e)}", "", False


def save_summary(dataset_id, document_id, document_name, summary):
    """调用 API 保存文档摘要"""
    url = f"https://ai.yxgswater.com:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/update-doc-summary"
    
    params = {
        "dataset_id": dataset_id,
        "document_id": document_id
    }
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
        "X-Workspace-Id": WORKSPACE_ID,
        "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "title": document_name,
        "summary": summary
    }
    
    try:
        response = requests.post(url, params=params, headers=headers, json=payload, timeout=60, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                return True, "摘要保存成功"
            else:
                return False, f"保存失败: code={result.get('code')}, msg={result.get('msg')}"
        else:
            return False, f"https状态码: {response.status_code}"
            
    except Exception as e:
        return False, f"保存异常: {str(e)}"


def generate_and_save_summary(dataset_id, document_id, document_name):
    """生成并保存文档摘要（两步操作）"""
    success, message, summary, should_skip = generate_summary(dataset_id, document_id, document_name)
    if not success:
        return False, f"生成失败: {message}", should_skip
    
    log.info(f"      摘要内容: {summary[:80]}..." if len(summary) > 80 else f"      摘要内容: {summary}")
    
    save_success, save_message = save_summary(dataset_id, document_id, document_name, summary)
    if not save_success:
        return False, f"保存失败: {save_message}", False
    
    return True, "生成并保存成功", False


def scan_and_generate(workspace_id, workspace_name):
    """扫描知识库，为向量化成功的文档生成摘要"""
    log.info(f"正在扫描 [{workspace_name}] 的知识库...")
    
    # 如果指定了优先文件夹，先处理优先文件夹
    datasets_to_process = []
    other_datasets = []
    
    if PRIORITY_FOLDER_ID:
        priority_folder_path = get_folder_path(PRIORITY_FOLDER_ID)
        log.info(f"优先处理文件夹: {priority_folder_path} (ID: {PRIORITY_FOLDER_ID})")
        
        try:
            status, priority_datasets = dataset_api.list_datasets(workspace_id, folder_id=PRIORITY_FOLDER_ID)
            if status == 200:
                datasets_to_process.extend(priority_datasets)
                log.info(f"优先文件夹下找到 {len(priority_datasets)} 个知识库")
            else:
                log.error(f"获取优先文件夹知识库失败: {priority_datasets}")
        except Exception as e:
            log.error(f"获取优先文件夹知识库失败: {e}")
    
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
        return 0, 0, 0
    
    log.info(f"总共需要处理 {len(all_datasets_list)} 个知识库")
    log.info("=" * 60)
    
    total_success = 0
    total_fail = 0
    total_skip = 0
    
    for i, ds in enumerate(all_datasets_list):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        is_priority = folder_id == PRIORITY_FOLDER_ID if PRIORITY_FOLDER_ID else False
        prefix = "[优先]" if is_priority else ""
        log.info(f"\n{prefix}[{i+1}/{len(all_datasets_list)}] 扫描知识库: {dataset_name}")
        log.info(f"  目录路径: {folder_path}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id)
            if status != 200:
                log.error(f"  获取文档失败")
                continue
            
            docs_to_process = []
            ds_skip = 0
            
            for doc in documents:
                vector_success = is_vector_success(doc)
                has_summary = check_doc_has_summary(doc)
                
                if vector_success and not has_summary:
                    docs_to_process.append({
                        "dataset_id": dataset_id,
                        "dataset_name": dataset_name,
                        "document_id": doc.get("id"),
                        "document_name": doc.get("name"),
                        "folder_path": folder_path
                    })
                elif vector_success and has_summary:
                    ds_skip += 1
            
            total_skip += ds_skip
            
            if len(docs_to_process) == 0:
                if ds_skip > 0:
                    log.info(f"  向量化成功: {ds_skip} 个(已有摘要), 无需处理")
                else:
                    log.info(f"  无向量化成功的文档")
                continue
            
            log.info(f"  发现 {len(docs_to_process)} 个需要生成摘要, {ds_skip} 个已有摘要")
            log.info("-" * 50)
            
            for idx, doc_info in enumerate(docs_to_process, 1):
                log.info(f"  [{idx}/{len(docs_to_process)}] [{folder_path}] {doc_info['document_name']}")
                log.info(f"    知识库: {dataset_name} | 文档ID: {doc_info['document_id']}")
                
                # 检查文档是否有分段
                segment_count = get_document_segments_count(
                    doc_info['dataset_id'],
                    doc_info['document_id']
                )
                time.sleep(SEGMENT_CHECK_INTERVAL)
                if segment_count == 0:
                    log.warning(f"    [跳过] 文档没有任何分段，无法生成摘要")
                    total_skip += 1
                    continue
                
                for attempt in range(1, MAX_RETRIES + 1):
                    success, message, should_skip = generate_and_save_summary(
                        doc_info['dataset_id'],
                        doc_info['document_id'],
                        doc_info['document_name']
                    )
                    
                    if success:
                        log.info(f"    [成功] {message}")
                        total_success += 1
                        break
                    elif should_skip:
                        log.warning(f"    [跳过] 文档过大或超过模型上下文限制: {message}")
                        total_skip += 1
                        break
                    else:
                        log.warning(f"    [失败] 第{attempt}次尝试: {message}")
                        if attempt < MAX_RETRIES:
                            log.info(f"    等待 {RETRY_INTERVAL} 秒后重试...")
                            time.sleep(RETRY_INTERVAL)
                        else:
                            log.error(f"    [最终失败] 已达最大重试次数({MAX_RETRIES})")
                            total_fail += 1
                
                if idx < len(docs_to_process):
                    time.sleep(REQUEST_INTERVAL)
            
            log.info("-" * 50)
            log.info(f"  知识库 [{dataset_name}] 处理完成")
            log.info(f"  当前总计: 成功 {total_success}, 失败 {total_fail}, 已有摘要 {total_skip}")
                
        except Exception as e:
            log.error(f"  出错: {e}")
    
    return total_success, total_fail, total_skip


def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    log.info("=" * 60)
    log.info("文档摘要生成工具")
    log.info(f"模式: 逐个处理（成功一个再下一个）")
    log.info(f"每个成功后间隔: {REQUEST_INTERVAL} 秒")
    log.info(f"失败重试次数: {MAX_RETRIES}, 重试间隔: {RETRY_INTERVAL} 秒")
    
    if PRIORITY_FOLDER_ID:
        priority_folder_path = get_folder_path(PRIORITY_FOLDER_ID)
        log.info(f"优先文件夹: {priority_folder_path}")
        log.info(f"优先文件夹ID: {PRIORITY_FOLDER_ID}")
        log.info(f"只处理优先文件夹: {'是' if ONLY_PRIORITY_FOLDER else '否'}")
    
    log.info("=" * 60)
    
    start_time = datetime.now()
    
    success, fail, skip = scan_and_generate(WORKSPACE_ID, WORKSPACE_NAME)
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    log.info("")
    log.info("=" * 60)
    log.info("全部完成！")
    log.info(f"成功: {success}, 失败: {fail}, 跳过(已有摘要): {skip}")
    log.info(f"总耗时: {duration}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
