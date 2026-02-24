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
from src.config import (
    API_KEY, AUTH_TOKEN, WORKSPACE_ID, WORKSPACE_NAME, LLM_CONFIG,
    PRIORITY_FOLDER_IDS, ONLY_PRIORITY_FOLDER,
    TARGET_FOLDER_PATH, ONLY_TARGET_FOLDER,
    FAILED_RECORDS_DIR,
)
import json

# ============== 配置区域 ==============
# 处理配置
REQUEST_INTERVAL = 3  # 每个请求成功后等待的时间（秒）
MAX_RETRIES = 1       # 单个文档最大重试次数
RETRY_INTERVAL = 2    # 重试间隔（秒）
SEGMENT_CHECK_INTERVAL = 0.5  # 每次检查分段之间的间隔（秒）

# 失败记录配置
ENABLE_FAILED_RECORD = True          # 是否启用失败记录功能
SKIP_RECORDED_FAILED = True          # 是否跳过已记录的失败文档
FAILED_RECORD_FILE = os.path.join(FAILED_RECORDS_DIR, "doc_summary_failed.json")  # 失败记录文件路径

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

dataset_api = LingyanDataset(API_KEY)

# 失败记录缓存（document_id -> 失败信息）
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
                failed_records = data.get('failed_docs', {})
                log.info("=" * 60)
                log.info(f"已加载 {len(failed_records)} 条失败记录")
                if failed_records:
                    updated_at = data.get('updated_at', '未知')
                    log.info(f"最后更新: {updated_at}")
                    log.info(f"失败记录文件: {FAILED_RECORD_FILE}")
                    if SKIP_RECORDED_FAILED:
                        log.info(f"⚠️  这些文档将被跳过，不会重新处理")
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
                'failed_docs': failed_records
            }, f, ensure_ascii=False, indent=2)
        log.info(f"✓ 失败记录已保存: {len(failed_records)} 条")
    except Exception as e:
        log.error(f"保存失败记录出错: {e}")


def is_in_failed_records(document_id):
    """检查文档是否在失败记录中"""
    return document_id in failed_records


def add_failed_record(doc_id, doc_name, doc_path, error_msg):
    """添加失败记录并立即保存"""
    global failed_records
    failed_records[doc_id] = {
        'name': doc_name,
        'path': doc_path,
        'error': error_msg,
        'failed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    # 立即保存，确保即使脚本中断也能记录
    save_failed_records()



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
        
        is_priority = folder_id in PRIORITY_FOLDER_IDS if PRIORITY_FOLDER_IDS else False
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
            ds_failed_skip = 0
            
            for doc in documents:
                document_id = doc.get("id")
                vector_success = is_vector_success(doc)
                has_summary = check_doc_has_summary(doc)
                
                # 如果在失败记录中，跳过
                if SKIP_RECORDED_FAILED and is_in_failed_records(document_id):
                    ds_failed_skip += 1
                    continue
                
                if vector_success and not has_summary:
                    doc_name = doc.get("name")
                    # 构建完整路径
                    if folder_path and folder_path != "根目录":
                        full_path = f"{folder_path}/{dataset_name}/{doc_name}"
                    else:
                        full_path = f"{dataset_name}/{doc_name}"
                    
                    docs_to_process.append({
                        "dataset_id": dataset_id,
                        "dataset_name": dataset_name,
                        "document_id": document_id,
                        "document_name": doc_name,
                        "folder_path": folder_path,
                        "full_path": full_path
                    })
                elif vector_success and has_summary:
                    ds_skip += 1
            
            total_skip += ds_skip
            
            if len(docs_to_process) == 0:
                if ds_skip > 0 or ds_failed_skip > 0:
                    skip_msg = f"  向量化成功: {ds_skip} 个(已有摘要)"
                    if ds_failed_skip > 0:
                        skip_msg += f", {ds_failed_skip} 个(已记录失败)"
                    log.info(skip_msg + ", 无需处理")
                else:
                    log.info(f"  无向量化成功的文档")
                continue
            
            info_msg = f"  发现 {len(docs_to_process)} 个需要生成摘要, {ds_skip} 个已有摘要"
            if ds_failed_skip > 0:
                info_msg += f", {ds_failed_skip} 个已记录失败"
            log.info(info_msg)
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
                    error_msg = "文档没有任何分段"
                    log.warning(f"    [跳过] {error_msg}")
                    total_skip += 1
                    # 记录失败
                    if ENABLE_FAILED_RECORD:
                        add_failed_record(
                            doc_info['document_id'],
                            doc_info['document_name'],
                            doc_info['full_path'],
                            error_msg
                        )
                    continue
                
                final_success = False
                for attempt in range(1, MAX_RETRIES + 1):
                    success, message, should_skip = generate_and_save_summary(
                        doc_info['dataset_id'],
                        doc_info['document_id'],
                        doc_info['document_name']
                    )
                    
                    if success:
                        log.info(f"    [成功] {message}")
                        total_success += 1
                        final_success = True
                        break
                    elif should_skip:
                        log.warning(f"    [跳过] 文档过大或超过模型上下文限制: {message}")
                        total_skip += 1
                        # 记录失败
                        if ENABLE_FAILED_RECORD:
                            add_failed_record(
                                doc_info['document_id'],
                                doc_info['document_name'],
                                doc_info['full_path'],
                                f"超过限制: {message}"
                            )
                        break
                    else:
                        log.warning(f"    [失败] 第{attempt}次尝试: {message}")
                        if attempt < MAX_RETRIES:
                            log.info(f"    等待 {RETRY_INTERVAL} 秒后重试...")
                            time.sleep(RETRY_INTERVAL)
                        else:
                            log.error(f"    [最终失败] 已达最大重试次数({MAX_RETRIES})")
                            total_fail += 1
                            # 记录失败
                            if ENABLE_FAILED_RECORD:
                                add_failed_record(
                                    doc_info['document_id'],
                                    doc_info['document_name'],
                                    doc_info['full_path'],
                                    message
                                )
                
                if final_success and idx < len(docs_to_process):
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
    
    # 加载失败记录
    load_failed_records()
    
    # 记录启动时的失败数量
    initial_failed_count = len(failed_records)
    
    log.info("=" * 60)
    log.info("文档摘要生成工具")
    log.info(f"模式: 逐个处理（成功一个再下一个）")
    log.info(f"每个成功后间隔: {REQUEST_INTERVAL} 秒")
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
        success, fail, skip = scan_and_generate(WORKSPACE_ID, WORKSPACE_NAME)
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
    log.info(f"成功: {success}, 失败: {fail}, 跳过(已有摘要): {skip}")
    if new_failed_count > 0:
        log.info(f"⚠️  本次运行新增 {new_failed_count} 条失败记录")
    log.info(f"总耗时: {duration}")
    log.info("=" * 60)
    
    # 最终保存
    if new_failed_count > 0:
        log.info(f"\n失败记录文件: {FAILED_RECORD_FILE}")
        log.info(f"下次启动时将自动跳过这些失败的文档")


if __name__ == "__main__":
    main()
