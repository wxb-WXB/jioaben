"""
生成文档摘要脚本
- 扫描知识库中向量化成功的文档
- 调用 API 为每个文档生成摘要
- 详细日志输出
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

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset
from models import FolderMap

# ============== 配置区域 ==============

# API 配置
API_KEY = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMDIzY2EzZDUyY2YwNDY0N2EwM2IyN2JhMWExMmNhMDUiLCJ1c2VybmFtZSI6IjEzNjI0ODM1MTE2IiwiaXNfc3VwZXJ1c2VyIjp0cnVlLCJleHAiOjE3Njk5OTgzODl9.KTzYjw_Q7AvxEkVo56TYghHZT_aCgP7op4TGLotZz8M"

# 工作空间配置
WORKSPACE_ID = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"
WORKSPACE_NAME = "环北工程知识库"

# LLM 配置
LLM_CONFIG = {
    "provider": "langgenius/openai_api_compatible/openai_api_compatible",
    "name": "qwen-turbo",
    "mode": "chat",
    "size": 32768,
    "completion_params": {
        "temperature": 0.2,
        "top_p": 0.75,
        "max_tokens": 512
    }
}

# 处理配置
REQUEST_INTERVAL = 3  # 每个请求成功后等待的时间（秒）
MAX_RETRIES = 3       # 单个文档最大重试次数
RETRY_INTERVAL = 2   # 重试间隔（秒）

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
    """
    从文档的 tasks 字段获取向量化任务状态
    返回: (status, task_type)
    状态值：success/completed=成功, failed/error=失败
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


def is_vector_success(doc):
    """
    判断文档是否向量化成功
    状态为 completed 或 success 都算成功
    """
    doc_status, _ = get_doc_status(doc)
    return doc_status in ["completed", "success"]


def check_doc_has_summary(doc):
    """检查文档是否已有摘要"""
    summary = doc.get("summary", "")
    return summary is not None and len(str(summary).strip()) > 0


def generate_summary(dataset_id, document_id, document_name):
    """
    调用 API 生成文档摘要
    返回: (success: bool, message: str, summary: str)
    """
    url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/generate-doc-summary"
    
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
        response = requests.post(
            url,
            params=params,
            headers=headers,
            json=payload,
            timeout=120,
            verify=False
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                summary = result.get("data", {}).get("summary", "")
                if summary:
                    return True, f"摘要生成成功", summary
                else:
                    return False, "生成的摘要为空", ""
            else:
                return False, f"API返回错误: code={result.get('code')}, msg={result.get('msg')}", ""
        else:
            # 尝试获取错误详情
            try:
                error_detail = response.json()
                return False, f"HTTP {response.status_code}: {error_detail}", ""
            except:
                return False, f"HTTP {response.status_code}: {response.text[:200]}", ""
            
    except requests.exceptions.Timeout:
        return False, "请求超时", ""
    except requests.exceptions.RequestException as e:
        return False, f"请求异常: {str(e)}", ""
    except Exception as e:
        return False, f"未知错误: {str(e)}", ""


def save_summary(dataset_id, document_id, document_name, summary):
    """
    调用 API 保存文档摘要
    返回: (success: bool, message: str)
    """
    url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/update-doc-summary"
    
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
        response = requests.post(
            url,
            params=params,
            headers=headers,
            json=payload,
            timeout=60,
            verify=False
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                return True, "摘要保存成功"
            else:
                return False, f"保存失败: code={result.get('code')}, msg={result.get('msg')}"
        else:
            return False, f"HTTP状态码: {response.status_code}"
            
    except Exception as e:
        return False, f"保存异常: {str(e)}"


def generate_and_save_summary(dataset_id, document_id, document_name):
    """
    生成并保存文档摘要（两步操作）
    返回: (success: bool, message: str)
    """
    # 第一步：生成摘要
    success, message, summary = generate_summary(dataset_id, document_id, document_name)
    if not success:
        return False, f"生成失败: {message}"
    
    log.info(f"      摘要内容: {summary[:80]}..." if len(summary) > 80 else f"      摘要内容: {summary}")
    
    # 第二步：保存摘要
    save_success, save_message = save_summary(dataset_id, document_id, document_name, summary)
    if not save_success:
        return False, f"保存失败: {save_message}"
    
    return True, "生成并保存成功"


def process_single_doc(doc_info, doc_index, total_docs):
    """
    处理单个文档，支持重试
    成功后才继续下一个
    """
    log.info(f"[{doc_index}/{total_docs}] 生成摘要: {doc_info['document_name']}")
    log.info(f"  目录路径: {doc_info['folder_path']}")
    log.info(f"  知识库: {doc_info['dataset_name']}")
    log.info(f"  文档ID: {doc_info['document_id']}")
    
    for attempt in range(1, MAX_RETRIES + 1):
        success, message = generate_summary(
            doc_info['dataset_id'],
            doc_info['document_id'],
            doc_info['document_name']
        )
        
        if success:
            log.info(f"  [成功] {message}")
            return True
        else:
            log.warning(f"  [失败] 第{attempt}次尝试失败: {message}")
            if attempt < MAX_RETRIES:
                log.info(f"  等待 {RETRY_INTERVAL} 秒后重试...")
                time.sleep(RETRY_INTERVAL)
    
    log.error(f"  [失败] 已达最大重试次数({MAX_RETRIES})，跳过此文档")
    return False


def scan_and_generate(workspace_id, workspace_name):
    """
    扫描知识库，为向量化成功的文档生成摘要
    逻辑：扫描一个知识库 → 立即处理该知识库的文档 → 再扫描下一个
    """
    log.info(f"正在扫描 [{workspace_name}] 的知识库...")
    status, datasets = dataset_api.list_datasets(workspace_id)
    
    if status != 200:
        log.error(f"获取知识库列表失败: {datasets}")
        return 0, 0, 0
    
    log.info(f"找到 {len(datasets)} 个知识库")
    log.info("=" * 60)
    
    total_success = 0
    total_fail = 0
    total_skip = 0
    
    for i, ds in enumerate(datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name")
        folder_id = ds.get("folder_id")
        folder_path = get_folder_path(folder_id)
        
        log.info(f"\n[{i+1}/{len(datasets)}] 扫描知识库: {dataset_name}")
        log.info(f"  目录路径: {folder_path}")
        
        try:
            status, documents = dataset_api.list_documents(dataset_id)
            if status != 200:
                log.error(f"  获取文档失败")
                continue
            
            # 收集该知识库中向量化成功且无摘要的文档
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
            
            # 立即处理这个知识库的文档
            for idx, doc_info in enumerate(docs_to_process, 1):
                log.info(f"  [{idx}/{len(docs_to_process)}] 处理文档: {doc_info['document_name']}")
                log.info(f"    文档ID: {doc_info['document_id']}")
                
                # 调用 API 生成并保存摘要
                for attempt in range(1, MAX_RETRIES + 1):
                    success, message = generate_and_save_summary(
                        doc_info['dataset_id'],
                        doc_info['document_id'],
                        doc_info['document_name']
                    )
                    
                    if success:
                        log.info(f"    [成功] {message}")
                        total_success += 1
                        break
                    else:
                        log.warning(f"    [失败] 第{attempt}次尝试: {message}")
                        if attempt < MAX_RETRIES:
                            log.info(f"    等待 {RETRY_INTERVAL} 秒后重试...")
                            time.sleep(RETRY_INTERVAL)
                        else:
                            log.error(f"    [最终失败] 已达最大重试次数({MAX_RETRIES})")
                            log.error(f"    ├─ 目录路径: {folder_path}")
                            log.error(f"    ├─ 知识库: {dataset_name}")
                            log.error(f"    ├─ 文档名: {doc_info['document_name']}")
                            log.error(f"    └─ 文档ID: {doc_info['document_id']}")
                            total_fail += 1
                
                # 成功后等待再处理下一个
                if idx < len(docs_to_process):
                    time.sleep(REQUEST_INTERVAL)
            
            log.info("-" * 50)
            log.info(f"  知识库 [{dataset_name}] 处理完成")
            log.info(f"  当前总计: 成功 {total_success}, 失败 {total_fail}, 已有摘要 {total_skip}")
                
        except Exception as e:
            log.error(f"  出错: {e}")
    
    return total_success, total_fail, total_skip


def main():
    # 禁用 SSL 警告
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    log.info("=" * 60)
    log.info("文档摘要生成工具")
    log.info(f"模式: 逐个处理（成功一个再下一个）")
    log.info(f"每个成功后间隔: {REQUEST_INTERVAL} 秒")
    log.info(f"失败重试次数: {MAX_RETRIES}, 重试间隔: {RETRY_INTERVAL} 秒")
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
