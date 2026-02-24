"""
灵燕AI核心API模块
================

本模块封装了AI平台的核心API接口，提供以下功能：

1. LingyanFile - 文件服务：文件上传、下载
2. LingyanDataset - 知识库服务：知识库管理、文档管理、任务管理

使用示例：
--------
    from src.core import LingyanDataset, LingyanFile
    
    # 文件服务
    file_service = LingyanFile(api_key="xxx")
    status, data = file_service.upload_file("test.pdf", "dataset")
    
    # 知识库服务
    dataset_service = LingyanDataset(api_key="xxx")
    status, datasets = dataset_service.list_datasets(workspace_id="xxx")
"""

import json
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests_toolbelt.multipart.encoder import MultipartEncoder
import logging

from ..config import API_HOST, LLM_CONFIG

log = logging.getLogger("LingyanAi")

# 默认请求超时时间（秒）
DEFAULT_TIMEOUT = 60


def create_session_with_retry(retries=5, backoff_factor=1.5, status_forcelist=(500, 502, 503, 504)):
    """
    创建带自动重试机制的requests Session
    
    Args:
        retries: 重试次数
        backoff_factor: 退避因子，重试间隔 = backoff_factor * (2 ** retry_count)
        status_forcelist: 需要重试的HTTP状态码
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
        raise_on_status=False,
        other=retries,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# 全局Session（延迟加载）
_session = None


def get_session():
    """获取全局Session（延迟加载）"""
    global _session
    if _session is None:
        _session = create_session_with_retry()
    return _session


class LingyanFile:
    """
    灵燕AI文件服务类
    
    提供文件上传和下载操作。
    
    Attributes:
        api_key (str): API密钥
    """
    
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def upload_file(self, file_path: str, file_type: str = "app", max_retries: int = 3) -> tuple[int, dict]:
        """
        上传文件（带重试机制）
        
        Args:
            file_path (str): 文件路径
            file_type (str): 文件业务类型 (app/dataset/tool/chat/avatar)
            max_retries (int): 最大重试次数
            
        Returns:
            tuple[int, dict]: (状态码, 响应数据)
        """
        if file_type not in ["app", "dataset", "tool", "chat", "avatar"]:
            raise ValueError("file_type must be one of ['app', 'dataset', 'tool', 'chat', 'avatar']")

        url = f"{API_HOST}/api/v1/service/files/upload"
        
        # Dynamic timeout based on file size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        timeout = min(max(60, int(60 + file_size_mb * 2)), 600)

        last_error = None
        for attempt in range(max_retries + 1):
            f = None
            try:
                f = open(file_path, "rb")
                encoder = MultipartEncoder(
                    fields={
                        "file": (os.path.basename(file_path), f, "application/pdf"),
                        "biz_type": file_type,
                    }
                )
                
                session = requests.Session()
                request_headers = {
                    "accept": "application/json",
                    "X-API-Key": self.api_key,
                    "Content-Type": encoder.content_type,
                    "Connection": "close",
                }

                response = session.post(url, data=encoder, headers=request_headers, timeout=timeout)
                f.close()
                session.close()
                return response.status_code, response.json().get("data")
            except requests.exceptions.ReadTimeout as e:
                if f:
                    f.close()
                last_error = e
                if attempt < max_retries:
                    delay = 10 * (attempt + 1)
                    log.warning(f"上传读取超时({timeout}秒)，{delay}秒后重试 ({attempt + 1}/{max_retries}): {os.path.basename(file_path)}")
                    time.sleep(delay)
                else:
                    log.error(f"上传超时，已达最大重试次数: {os.path.basename(file_path)}")
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                if f:
                    f.close()
                last_error = e
                if attempt < max_retries:
                    delay = 5 * (attempt + 1)
                    log.warning(f"上传连接错误，{delay}秒后重试 ({attempt + 1}/{max_retries}): {os.path.basename(file_path)}")
                    time.sleep(delay)
                else:
                    log.error(f"上传失败，已达最大重试次数: {os.path.basename(file_path)}")
            except requests.exceptions.RequestException as e:
                if f:
                    f.close()
                log.error(f"上传请求失败: {str(e)}")
                return 500, f"请求失败: {str(e)}"
        
        return 500, f"请求失败（重试{max_retries}次后）: {str(last_error)}"

    def download_file(self, file_id: str) -> tuple[int, bytes]:
        """根据文件ID下载文件"""
        url = f"{API_HOST}/api/v1/service/files/{file_id}/download"
        response = requests.get(url, headers={"accept": "application/json", "X-API-Key": self.api_key})
        return response.status_code, response.content


class LingyanDataset:
    """
    灵眼AI知识库服务类
    
    提供知识库的完整生命周期管理：
    - 创建、查询、更新知识库
    - 上传、查询、删除文档
    - 创建和管理处理任务
    
    Attributes:
        api_key (str): API密钥
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key

    def list_datasets(self, workspace_id: str, folder_id: str | None = None) -> tuple[int, list | str]:
        """获取知识库列表（自动分页加载所有数据）"""
        url = f"{API_HOST}/api/v1/service/datasets"
        datasets = []
        current_page = 1
        session = get_session()
        
        while True:
            try:
                response = session.get(
                    url,
                    params={"workspace_id": workspace_id, "folder_id": folder_id, "page_size": 1000, "page": current_page},
                    headers={"accept": "application/json", "X-API-Key": self.api_key},
                    timeout=DEFAULT_TIMEOUT,
                )
                if response.status_code != 200:
                    return response.status_code, response.json().get("msg")
                data = response.json().get("data")
                if not data or len(data) == 0:
                    break
                datasets.extend(data)
                current_page += 1
                log.info(f"获取知识库列表成功，长度 {len(data)}，当前页码 {current_page}")
            except requests.exceptions.RequestException as e:
                log.error(f"获取知识库列表请求失败: {str(e)}")
                return 500, f"请求失败: {str(e)}"
        return 200, datasets

    def create_dataset(self, workspace_id: str, name: str, folder_id: str, description: str = "") -> tuple[int, str]:
        """创建新的知识库"""
        url = f"{API_HOST}/api/v1/service/datasets"
        session = get_session()

        try:
            response = session.post(
                url,
                json={
                    "workspace_id": workspace_id,
                    "name": name,
                    "description": description,
                    "folder_id": folder_id,
                    "embedding_model": {
                        "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                        "name": "Qwen3-Embedding-4B",
                        "size": 4096,
                    },
                    "processing_config": {
                        "chunk_size": 2000,
                        "overlap": 30,
                        "chinese_title_enhance": False,
                        "process_type": "NORMAL",
                        "separators": "\\n",
                        "replace_spaces_tabs": False,
                        "delete_url_email": False,
                        "parse_enhance": True,
                        "parse_toc": False,
                        "index_config": {
                            "title": {**LLM_CONFIG, "size": 8000, "completion_params": {**LLM_CONFIG["completion_params"], "max_tokens": 2000}},
                            "summary": {**LLM_CONFIG, "size": 8000, "completion_params": {**LLM_CONFIG["completion_params"], "max_tokens": 2000}},
                            "question": {**LLM_CONFIG, "size": 8000, "completion_params": {**LLM_CONFIG["completion_params"], "max_tokens": 2000}},
                        },
                        "md_split_by_headers": False,
                        "md_max_header_level": 3,
                        "doc_summary": True,
                        "doc_summary_config": LLM_CONFIG,
                    },
                },
                headers={"accept": "application/json", "X-API-Key": self.api_key, "Content-Type": "application/json"},
                timeout=DEFAULT_TIMEOUT,
            )

            if response.status_code != 200:
                return response.status_code, response.json().get("msg")
            return 200, response.json().get("data", "")
        except requests.exceptions.RequestException as e:
            log.error(f"创建知识库请求失败: {str(e)}")
            return 500, f"请求失败: {str(e)}"

    def create_document(self, dataset_id: str, file_id: str) -> tuple[int, dict | str]:
        """在知识库中创建文档"""
        url = f"{API_HOST}/api/v1/service/datasets/{dataset_id}/documents"
        payload = {"dataset_id": dataset_id, "file_ids": [file_id], "processing_config": {}}
        
        try:
            session = get_session()
            response = session.post(
                url,
                json=payload,
                headers={"accept": "application/json", "X-API-Key": self.api_key, "Content-Type": "application/json"},
                timeout=DEFAULT_TIMEOUT,
            )
            if response.status_code != 200:
                return response.status_code, response.json().get("msg")
            return 200, response.json().get("data")
        except requests.exceptions.RequestException as e:
            log.error(f"创建文档请求失败: {str(e)}")
            return 500, f"请求失败: {str(e)}"

    def create_task(
        self,
        dataset_id: str,
        document_id: str,
        split_mode: str = "semantic",
        task_type: str = "normal",
        image_task: bool = False,
        parse_enhance: bool = True,
        workspace_id: str = None,
    ) -> tuple[int, dict | str]:
        """创建文档处理任务"""
        url = f"{API_HOST}/api/v1/service/datasets/{dataset_id}/documents/{document_id}/tasks"

        headers = {"accept": "application/json", "X-API-Key": self.api_key, "Content-Type": "application/json"}
        if workspace_id:
            headers["X-Workspace-Id"] = workspace_id
            headers["x-fly-tenantid"] = "00000000-0000-0000-0000-000000000000"

        payload = {
            "dataset_id": dataset_id,
            "document_id": document_id,
            "splitter_mode": split_mode,
            "type": task_type,
            "processing_config": {
                "chunk_size": 2000,
                "overlap": 30,
                "chinese_title_enhance": False,
                "process_type": "NORMAL",
                "separators": "\\n",
                "replace_spaces_tabs": "1",
                "delete_url_email": "1",
                "parse_enhance": parse_enhance,
                "parse_toc": not parse_enhance,
                "index_config": {
                    "title": LLM_CONFIG,
                    "summary": LLM_CONFIG,
                    "question": LLM_CONFIG,
                },
                "md_split_by_headers": False,
                "md_max_header_level": 3,
                "doc_summary": True,
                "doc_summary_config": LLM_CONFIG,
            },
        }

        if image_task:
            payload["processing_config"]["index_config"]["image"] = {
                "provider": "langgenius/tongyi/tongyi",
                "name": "qwen2.5-vl-7b-instruct",
                "mode": "chat",
                "completion_params": {"temperature": 0.2, "top_p": 0.75, "max_tokens": 8192, "seed": 1234, "repetition_penalty": 1.1},
            }

        try:
            session = get_session()
            response = session.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
            if response.status_code != 200:
                return response.status_code, response.json().get("msg")
            return 200, response.json().get("data")
        except requests.exceptions.RequestException as e:
            log.error(f"创建任务请求失败: {str(e)}")
            return 500, f"请求失败: {str(e)}"

    def check_file(self, file_name: str, dataset_id: str) -> tuple[int, dict, int]:
        """文件重名检测"""
        url = f"{API_HOST}/api/v1/service/datasets/{dataset_id}/documents/check-names"
        payload = {"names": [file_name], "dataset_id": dataset_id}
        
        try:
            session = get_session()
            response = session.post(
                url,
                json=payload,
                headers={"accept": "application/json", "X-API-Key": self.api_key},
                timeout=DEFAULT_TIMEOUT,
            )
            return (response.status_code, response.json().get("data"), response.json().get("data").get("duplicate_count"))
        except requests.exceptions.RequestException as e:
            log.error(f"文件重名检测请求失败: {str(e)}")
            return 500, {"error": str(e)}, 0

    def get_folder_tree(self, workspace_id: str) -> tuple[int, dict | str]:
        """获取文件夹树结构"""
        from src.config import AUTH_TOKEN
        
        url = f"{API_HOST}/api/v1/console/datasets/folders/tree"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "X-Workspace-Id": workspace_id,
            "x-fly-tenantid": "00000000-0000-0000-0000-000000000000"
        }
        
        try:
            session = get_session()
            response = session.get(
                url,
                params={"workspace_id": workspace_id},
                headers=headers,
                timeout=DEFAULT_TIMEOUT
            )
            if response.status_code != 200:
                return response.status_code, response.json().get("msg", "Unknown error")
            return 200, response.json().get("data", {})
        except requests.exceptions.RequestException as e:
            log.error(f"获取文件夹树失败: {str(e)}")
            return 500, f"请求失败: {str(e)}"

    def list_documents(self, dataset_id: str, workspace_id: str = None, max_retries: int = 3) -> tuple[int, list | str]:
        """获取文档列表（自动分页加载所有数据，带重试机制）"""
        url = f"{API_HOST}/api/v1/service/datasets/{dataset_id}/documents"
        documents = []
        current_page = 1
        
        headers = {"accept": "application/json", "X-API-Key": self.api_key}
        if workspace_id:
            headers["X-Workspace-Id"] = workspace_id
            headers["x-fly-tenantid"] = "00000000-0000-0000-0000-000000000000"
        
        session = get_session()
        
        while True:
            last_error = None
            for attempt in range(max_retries):
                try:
                    response = session.get(
                        url, headers=headers,
                        params={"page_size": 1000, "page": current_page},
                        timeout=DEFAULT_TIMEOUT,
                    )
                    break
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = 3 * (2 ** attempt)
                        log.warning(f"获取文档列表连接错误(page={current_page})，{delay}秒后重试 ({attempt + 1}/{max_retries}): {str(e)}")
                        time.sleep(delay)
                    else:
                        log.error(f"获取文档列表失败(page={current_page})，已达最大重试次数: {str(e)}")
                        return 500, f"请求失败（重试{max_retries}次后）: {str(last_error)}"

            if response.status_code != 200:
                return response.status_code, response.json().get("msg")
            
            response_data = response.json().get("data")
            if isinstance(response_data, list):
                data = response_data
            elif isinstance(response_data, dict):
                data = response_data.get("list", [])
            else:
                data = []
            
            if not data or len(data) == 0:
                break
            documents.extend(data)
            current_page += 1
            log.info(f"获取文档列表成功，长度 {len(data)}，当前页码 {current_page}")
        return 200, documents

    def delete_document(self, dataset_id: str, document_id: str, max_retries: int = 5) -> tuple[int, dict | str]:
        """删除文档（带重试机制）"""
        url = f"{API_HOST}/api/v1/service/datasets/{dataset_id}/documents/{document_id}"
        
        last_error = None
        for attempt in range(max_retries):
            try:
                session = get_session()
                response = session.delete(
                    url,
                    headers={"accept": "application/json", "X-API-Key": self.api_key},
                    timeout=DEFAULT_TIMEOUT
                )
                if response.status_code != 200:
                    return response.status_code, response.json().get("msg")
                return 200, response.json().get("data")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 3 * (2 ** attempt)
                    log.warning(f"删除文档连接错误，{delay}秒后重试 ({attempt + 1}/{max_retries}): {str(e)}")
                    time.sleep(delay)
                else:
                    log.error(f"删除文档失败，已达最大重试次数: {str(e)}")
            except requests.exceptions.RequestException as e:
                log.error(f"删除文档请求失败: {str(e)}")
                return 500, f"请求失败: {str(e)}"
        
        return 500, f"请求失败（重试{max_retries}次后）: {str(last_error)}"
