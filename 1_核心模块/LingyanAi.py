"""
灵眼AI核心模块
================

本模块封装了灵燕AI平台的核心API接口，提供以下功能：

1. LingyanAi - 对话服务：与大模型进行对话交互
2. LingyanFile - 文件服务：文件上传、下载
3. LingyanDataset - 知识库服务：知识库管理、文档管理、任务管理

使用示例：
--------
    # 对话服务
    ai = LingyanAi(app_id="xxx", api_key="xxx")
    status, answer = ai.chat(prompt="你好", inputs_obj={})

    # 文件服务
    file_service = LingyanFile(api_key="xxx")
    status, data = file_service.upload_file("test.pdf", "dataset")

    # 知识库服务
    dataset_service = LingyanDataset(api_key="xxx")
    status, datasets = dataset_service.list_datasets(workspace_id="xxx")

API基础地址: http://10.4.49.66:18080/api/v1/service/
"""

import json
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests_toolbelt.multipart.encoder import MultipartEncoder
import logging

log = logging.getLogger("LingyanAi")

# 创建带重试机制的Session
def create_session_with_retry(retries=5, backoff_factor=1.5, status_forcelist=(500, 502, 503, 504)):
    """
    创建带自动重试机制的requests Session
    
    Args:
        retries: 重试次数（增加到5次以应对不稳定连接）
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
        raise_on_status=False,  # 不抛出异常，让我们可以检查响应
        other=retries,  # 对其他类型的错误也重试
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# 全局Session（带重试机制）
_session = None

def get_session():
    """获取全局Session（懒加载）"""
    global _session
    if _session is None:
        _session = create_session_with_retry()
    return _session

# 默认请求超时时间（秒）
DEFAULT_TIMEOUT = 60


class LingyanAi:
    """
    灵眼AI对话服务类
    
    用于与灵眼AI大模型进行对话交互，支持chatflow应用的调用。
    
    Attributes:
        app_id (str): 应用ID
        api_key (str): API密钥
        stream (bool): 是否使用流式输出（暂未实现）
    """
    
    def __init__(self, app_id: str, api_key: str, stream: bool = False):
        """
        初始化对话服务
        
        Args:
            app_id (str): chatflow应用的ID
            api_key (str): API访问密钥
            stream (bool): 是否使用流式输出，默认False
        """
        self.app_id = app_id
        self.api_key = api_key
        self.stream = stream

    def chat(self, prompt: str, inputs_obj: dict) -> tuple[int, str]:
        """
        与大模型进行对话
        
        Args:
            prompt (str): 用户输入的提示词
            inputs_obj (dict): 输入参数对象，用于传递给chatflow的变量
            
        Returns:
            tuple[int, str]: (状态码, 回答内容)
                - 200: 成功
                - 其他: 失败
        """
        url = f"http://10.4.49.66:18080/api/v1/service/apps/chatflow/{self.app_id}/chat-messages"

        payload = {
            "query": "string",
            "conversation_id": "ab48a7e9-8cf3-412a-80d5-642128b24203",
            "inputs": inputs_obj,
            "stream": False,
        }
        headers = {
            "accept": "application/json",
            "X-API-Key": f"{self.api_key}",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "PostmanRuntime-ApipostRuntime/1.1.0",
            "Connection": "keep-alive",
        }

        response = requests.request(
            "POST", url, data=json.dumps(payload), headers=headers
        )

        return response.status_code, response.json().get("data").get("data").get(
            "outputs"
        ).get("answer")


class LingyanFile:
    """
    灵眼AI文件服务类
    
    用于文件的上传和下载操作，支持多种业务类型的文件管理。
    
    Attributes:
        api_key (str): API密钥
    """
    
    def __init__(self, api_key: str) -> None:
        """
        初始化文件服务
        
        Args:
            api_key (str): API访问密钥
        """
        self.api_key = api_key

    def upload_file(self, file_path: str, file_type: str = "app", max_retries: int = 3) -> tuple[int, dict]:
        """
        上传文件（带重试机制）
        ----
        Args:
            file_path (str): 文件路径
            file_type (str): 文件业务类型
                - app: 应用
                - dataset: 知识库
                - tool: 工具
                - chat: 聊天
                - avatar: 头像
            max_retries (int): 最大重试次数，默认3次
        """
        if file_type not in ["app", "dataset", "tool", "chat", "avatar"]:
            raise ValueError(
                "file_type must be one of ['app', 'dataset', 'tool', 'chat', 'avatar']"
            )

        url = "http://10.4.49.66:18080/api/v1/service/files/upload"
        
        # 根据文件大小动态设置超时时间
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        # 基础60秒 + 每MB增加2秒，最少60秒，最多600秒（10分钟）
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
                
                # 每次请求使用新的session，避免连接池问题
                session = requests.Session()
                request_headers = {
                    "accept": "application/json",
                    "X-API-Key": self.api_key,
                    "Content-Type": encoder.content_type,
                    "Connection": "close",  # 上传完成后关闭连接
                }

                response = session.post(url, data=encoder, headers=request_headers, timeout=timeout)
                f.close()
                session.close()  # 显式关闭session
                return response.status_code, response.json().get("data")
            except requests.exceptions.ReadTimeout as e:
                # 读取超时：服务器处理时间过长，等待后重试
                if f:
                    f.close()
                last_error = e
                if attempt < max_retries:
                    delay = 10 * (attempt + 1)  # 10, 20, 30 秒
                    log.warning(f"文件上传读取超时({timeout}秒)，{delay}秒后重试 ({attempt + 1}/{max_retries}): {os.path.basename(file_path)}")
                    time.sleep(delay)
                else:
                    log.error(f"文件上传超时，已达最大重试次数: {os.path.basename(file_path)}")
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                if f:
                    f.close()
                last_error = e
                if attempt < max_retries:
                    delay = 5 * (attempt + 1)  # 5, 10, 15 秒
                    log.warning(f"文件上传连接错误，{delay}秒后重试 ({attempt + 1}/{max_retries}): {os.path.basename(file_path)}")
                    time.sleep(delay)
                else:
                    log.error(f"文件上传失败，已达最大重试次数: {os.path.basename(file_path)}")
            except requests.exceptions.RequestException as e:
                if f:
                    f.close()
                log.error(f"文件上传请求失败: {str(e)}")
                return 500, f"请求失败: {str(e)}"
        
        # 所有重试都失败了
        return 500, f"请求失败（重试{max_retries}次后）: {str(last_error)}"


    def download_file(self, file_id: str) -> tuple[int, bytes]:
        """
        下载文件
        
        Args:
            file_id (str): 文件ID
            
        Returns:
            tuple[int, bytes]: (状态码, 文件二进制内容)
        """
        url = f"http://10.4.49.66:18080/api/v1/service/files/{file_id}/download"
        response = requests.get(url, headers={"accept": "application/json", "X-API-Key": self.api_key})
        return response.status_code, response.content

def build_file_info(file_info: dict) -> dict:
    """
    构建文件信息对象
    
    将上传返回的文件信息转换为标准格式，用于后续API调用。
    
    Args:
        file_info (dict): 上传文件后返回的文件信息
            - name: 文件名
            - size: 文件大小
            - file_type: 文件类型
            - mime_type: MIME类型
            - url: 远程URL
            
    Returns:
        dict: 标准化的文件信息对象
    """
    input_file = {
        "id": None,
        "filename": file_info.get("name"),
        "size": file_info.get("size"),
        "type": file_info.get("file_type"),
        "mime_type": file_info.get("mime_type"),
        "remote_url": file_info.get("url"),
        "tenant_id": "00000000-0000-0000-0000-000000000000",
    }

    return input_file


class LingyanDataset:
    """
    灵燕AI知识库服务类
    
    提供知识库的完整生命周期管理，包括：
    - 知识库的创建、查询、更新
    - 文档的上传、查询、删除
    - 文档处理任务的创建和管理
    - 批量操作支持
    
    Attributes:
        api_key (str): API密钥
        
    典型工作流程:
        1. 创建知识库 (create_dataset)
        2. 上传文件到知识库 (create_document)
        3. 创建处理任务 (create_task)
        4. 等待任务完成
    """
    
    def __init__(self, api_key: str):
        """
        初始化知识库服务
        
        Args:
            api_key (str): API访问密钥
        """
        self.api_key = api_key

    def list_datasets(self, workspace_id: str, folder_id: str | None = None) -> tuple[int, list | str]:
        """
        获取知识库列表
        
        支持分页自动加载，会获取所有知识库数据。
        
        Args:
            workspace_id (str): 工作空间ID
            folder_id (str | None): 文件夹ID，可选，用于筛选特定文件夹下的知识库
            
        Returns:
            tuple[int, list | str]: (状态码, 知识库列表或错误信息)
                - 200: 成功，返回知识库列表
                - 其他: 失败，返回错误信息
        """
        url = "http://10.4.49.66:18080/api/v1/service/datasets"
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

    def create_dataset(
        self, workspace_id: str, name: str, folder_id: str, description: str = ""
    ) -> tuple[int, str]:
        """
        创建知识库
        
        使用预设的配置创建新的知识库，包括：
        - 嵌入模型: Qwen3-Embedding-4B
        - 切片大小: 2000
        - 重叠: 50
        - 索引配置: deepseekv3-0324
        
        Args:
            workspace_id (str): 工作空间ID
            name (str): 知识库名称
            folder_id (str): 存放的文件夹ID
            description (str): 知识库描述，默认为空
            
        Returns:
            tuple[int, str]: (状态码, 错误信息)
                - 200: 成功
                - 其他: 失败，返回错误信息
        """
        url = "http://10.4.49.66:18080/api/v1/service/datasets"
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
                            "title": {
                                "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                                "name": "deepseekv3-0324",
                                "mode": "chat",
                                "size": 8000,
                                "completion_params": {
                                    "temperature": 0.2,
                                    "top_p": 0.75,
                                    "frequency_penalty": 0.5,
                                    "presence_penalty": 0.5,
                                    "max_tokens": 2000,
                                },
                            },
                            "summary": {
                                "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                                "name": "deepseekv3-0324",
                                "mode": "chat",
                                "size": 8000,
                                "completion_params": {
                                    "temperature": 0.2,
                                    "top_p": 0.75,
                                    "frequency_penalty": 0.5,
                                    "presence_penalty": 0.5,
                                    "max_tokens": 2000,
                                },
                            },
                            "question": {
                                "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                                "name": "deepseekv3-0324",
                                "mode": "chat",
                                "size": 8000,
                                "completion_params": {
                                    "temperature": 0.2,
                                    "top_p": 0.75,
                                    "frequency_penalty": 0.5,
                                    "presence_penalty": 0.5,
                                    "max_tokens": 2000,
                                },
                            },
                        },
                        "md_split_by_headers": False,
                        "md_max_header_level": 3,
                        "doc_summary": True,
                        "doc_summary_config": {
                            "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                            "name": "deepseekv3-0324",
                            "mode": "chat",
                            "size": 32768,
                            "completion_params": {
                                "temperature": 0.2,
                                "top_p": 0.75,
                                "frequency_penalty": 0.5,
                                "presence_penalty": 0.5,
                                "max_tokens": 2000,
                            },
                        },
                    },
                },
                headers={
                    "accept": "application/json",
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=DEFAULT_TIMEOUT,
            )

            if response.status_code != 200:
                return response.status_code, response.json().get("msg")
            return 200, response.json().get("data", "")
        except requests.exceptions.RequestException as e:
            log.error(f"创建知识库请求失败: {str(e)}")
            return 500, f"请求失败: {str(e)}"

    def update_dataset(
        self,
        new_dataset: dict,
        workspace_id: str = None
    ) -> tuple[int, dict | str]:
        """
        更新知识库配置（使用 service API）
        
        Args:
            new_dataset (dict): 知识库配置数据，需包含知识库ID等必要字段
            workspace_id (str): 工作空间ID（可选，用于请求头认证）
            
        Returns:
            tuple[int, dict | str]: (状态码, 更新后的数据或错误信息)
                - 200: 成功，返回更新后的知识库数据
                - 其他: 失败，返回错误信息
        """
        url = "http://10.4.49.66:18080/api/v1/service/datasets"
        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if workspace_id:
            headers["X-Workspace-Id"] = workspace_id
            headers["x-fly-tenantid"] = "00000000-0000-0000-0000-000000000000"

        response = requests.put(url, json=new_dataset, headers=headers)

        if response.status_code != 200:
            return response.status_code, response.json().get("msg")
        return 200, response.json().get("data")

    def create_document(self, dataset_id: str, file_id: str) -> tuple[int, dict | str]:
        """
        创建文档
        
        将已上传的文件添加到知识库中，创建对应的文档记录。
        创建文档后需要调用 create_task 来处理文档内容。
        
        Args:
            dataset_id (str): 目标知识库ID
            file_id (str): 已上传文件的ID（通过 LingyanFile.upload_file 获取）
            
        Returns:
            tuple[int, dict | str]: (状态码, 文档数据或错误信息)
                - 200: 成功，返回创建的文档信息
                - 其他: 失败，返回错误信息
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents"
        payload = {
            "dataset_id": dataset_id,
            "file_ids": [file_id],
            "processing_config": {},
        }
        try:
            session = get_session()
            response = session.post(
                url,
                json=payload,
                headers={
                    "accept": "application/json",
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
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
        """
        创建文档处理任务（使用 service API）
        
        对文档进行切片、索引等处理。任务为异步执行，创建后会在后台处理。
        
        处理配置说明：
        - 切片大小: 2000
        - 重叠: 30
        - 索引模型: qwen-turbo
        - 支持标题、摘要、问题索引
        - 可选图片索引（使用 qwen2.5-vl-7b-instruct）
        
        Args:
            dataset_id (str): 知识库ID
            document_id (str): 文档ID
            split_mode (str): 切分模式
                - "auto": 自动切分
                - "semantic": 语义化切分（默认，推荐）
                - "common": 普通切分
            task_type (str): 任务类型
                - "normal": 普通任务（默认）
                - "image": 图片任务
            image_task (bool): 是否添加图片索引，默认False
                - True: 使用视觉模型处理图片内容
            parse_enhance (bool): 是否增强解析，默认True
                - True: 精准解析（推荐，解析效果更好）
                - False: 目录解析（速度更快）
            workspace_id (str): 工作空间ID（可选，用于请求头认证）
            
        Returns:
            tuple[int, dict | str]: (状态码, 任务数据或错误信息)
                - 200: 成功，返回任务信息
                - 其他: 失败，返回错误信息
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents/{document_id}/tasks"

        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
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
                    "title": {
                        "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                        "name": "deepseekv3-0324",
                        "mode": "chat",
                        "size": 32768,
                        "completion_params": {
                            "temperature": 0.2,
                            "top_p": 0.75,
                            "max_tokens": 8000,
                        },
                    },
                    "summary": {
                        "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                        "name": "deepseekv3-0324",
                        "mode": "chat",
                        "size": 32768,
                        "completion_params": {
                            "temperature": 0.2,
                            "top_p": 0.75,
                            "max_tokens": 8000,
                        },
                    },
                    "question": {
                        "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                        "name": "deepseekv3-0324",
                        "mode": "chat",
                        "size": 32768,
                        "completion_params": {
                            "temperature": 0.2,
                            "top_p": 0.75,
                            "max_tokens": 8000,
                        },
                    },
                },
                "md_split_by_headers": False,
                "md_max_header_level": 3,
                "doc_summary": True,
                "doc_summary_config": {
                    "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                    "name": "deepseekv3-0324",
                    "mode": "chat",
                    "size": 32768,
                    "completion_params": {
                        "temperature": 0.2,
                        "top_p": 0.75,
                        "max_tokens": 8000,
                    },
                },
            },
        }

        # 如果是图片任务，则需要添加图片索引
        if image_task:
            payload["processing_config"]["index_config"]["image"] = {
                "provider": "langgenius/tongyi/tongyi",
                "name": "qwen2.5-vl-7b-instruct",
                "mode": "chat",
                "completion_params": {
                    "temperature": 0.2,
                    "top_p": 0.75,
                    "max_tokens": 8192,
                    "seed": 1234,
                    "repetition_penalty": 1.1,
                },
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
        """
        文件重名检测
        
        在上传文件前检查知识库中是否已存在同名文件，避免重复上传。
        
        Args:
            file_name (str): 要检查的文件名
            dataset_id (str): 目标知识库ID
            
        Returns:
            tuple[int, dict, int]: (状态码, 检测结果数据, 重复数量)
                - duplicate_count > 0 表示存在重名文件
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents/check-names"
        payload = {
            "names": [file_name],
            "dataset_id": dataset_id,
        }
        try:
            session = get_session()
            response = session.post(
                url,
                json=payload,
                headers={"accept": "application/json", "X-API-Key": self.api_key},
                timeout=DEFAULT_TIMEOUT,
            )
            return (
                response.status_code,
                response.json().get("data"),
                response.json().get("data").get("duplicate_count"),
            )
        except requests.exceptions.RequestException as e:
            log.error(f"文件重名检测请求失败: {str(e)}")
            return 500, {"error": str(e)}, 0

    def list_documents(self, dataset_id: str, workspace_id: str = None) -> tuple[int, list | str]:
        """
        获取文档列表（使用 service API）
        
        支持分页自动加载，会获取知识库中所有文档。
        兼容两种API返回格式（列表或带list字段的对象）。
        
        Args:
            dataset_id (str): 知识库ID
            workspace_id (str): 工作空间ID（可选，用于请求头认证）
            
        Returns:
            tuple[int, list | str]: (状态码, 文档列表或错误信息)
                - 200: 成功，返回文档列表
                - 其他: 失败，返回错误信息
                
        文档对象包含字段：
            - id: 文档ID
            - name: 文档名称
            - type: 文件类型
            - status: 处理状态
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents"
        documents = []
        current_page = 1
        
        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
        }
        if workspace_id:
            headers["X-Workspace-Id"] = workspace_id
            headers["x-fly-tenantid"] = "00000000-0000-0000-0000-000000000000"
        
        while True:
            response = requests.get(
                url,
                headers=headers,
                params={"page_size": 1000, "page": current_page},
            )

            if response.status_code != 200:
                return response.status_code, response.json().get("msg")
            
            response_data = response.json().get("data")
            # 兼容两种返回格式：data 是列表或 data.list 是列表
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
        """
        删除文档（带增强重试机制）
        
        删除知识库中的指定文档，支持自动重试和指数退避。
        删除操作会同时删除文档的所有切片和索引数据。
        
        Args:
            dataset_id (str): 知识库ID
            document_id (str): 要删除的文档ID
            max_retries (int): 最大重试次数，默认5次（指数退避）
            
        Returns:
            tuple[int, dict | str]: (状态码, 响应数据或错误信息)
                - 200: 成功删除
                - 500: 请求失败（网络错误等）
                - 其他: API返回的错误
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents/{document_id}"
        
        last_error = None
        for attempt in range(max_retries):
            try:
                # 使用带重试机制的session
                session = get_session()
                response = session.delete(
                    url,
                    headers={"accept": "application/json", "X-API-Key": self.api_key},
                    timeout=DEFAULT_TIMEOUT
                )
                if response.status_code != 200:
                    return response.status_code, response.json().get("msg")
                return 200, response.json().get("data")
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 3 * (2 ** attempt)  # 指数退避: 3, 6, 12, 24, 48 秒
                    log.warning(f"删除文档连接错误，{delay}秒后重试 ({attempt + 1}/{max_retries}): {str(e)}")
                    time.sleep(delay)
                else:
                    log.error(f"删除文档失败，已达最大重试次数: {str(e)}")
            except requests.exceptions.RequestException as e:
                log.error(f"删除文档请求失败: {str(e)}")
                return 500, f"请求失败: {str(e)}"
        
        # 所有重试都失败了
        return 500, f"请求失败（重试{max_retries}次后）: {str(last_error)}"

    def delete_documents_by_types(self, dataset_id: str, file_types: list[str] = None) -> tuple[int, int, list]:
        """
        删除知识库中指定类型的文档
        
        批量删除指定文件类型的所有文档，适用于清理非文档文件（如图片、压缩包等）。
        
        Args:
            dataset_id (str): 知识库ID
            file_types (list[str]): 要删除的文件类型列表
                - 默认: ["png", "zip", "jpg", "jpeg"]
                - 注意：类型不带点，如 "png" 而不是 ".png"
                - 大小写不敏感
                
        Returns:
            tuple[int, int, list]: (状态码, 删除成功数量, 删除失败列表)
                - 失败列表包含: name, id, type, error 字段
        """
        if file_types is None:
            file_types = ["png", "zip", "jpg", "jpeg"]
        
        # 统一转为小写，去掉可能的点
        file_types = [t.lower().lstrip(".") for t in file_types]
        
        # 获取文档列表
        status_code, documents = self.list_documents(dataset_id)
        if status_code != 200:
            return status_code, 0, []

        deleted_count = 0
        failed_list = []

        for doc in documents:
            doc_name = doc.get("name", "")
            doc_type = doc.get("type", "").lower()
            # 检查文档类型是否在要删除的类型列表中
            if doc_type in file_types:
                doc_id = doc.get("id")
                log.info(f"正在删除文档: {doc_name} (类型: {doc_type}, ID: {doc_id})")
                del_status, del_result = self.delete_document(dataset_id, doc_id)
                if del_status == 200:
                    deleted_count += 1
                    log.info(f"成功删除文档: {doc_name}")
                else:
                    failed_list.append({"name": doc_name, "id": doc_id, "type": doc_type, "error": del_result})
                    log.error(f"删除文档失败: {doc_name}, 错误: {del_result}")
                # 每次删除后等待1秒，避免请求过快导致服务器拒绝连接
                time.sleep(1)

        return 200, deleted_count, failed_list

    def delete_documents_global(self, workspace_id: str, file_types: list[str] = None, folder_id: str = None) -> tuple[int, list, list]:
        """
        全局删除所有知识库中指定类型的文档
        
        遍历工作空间（或指定文件夹）下的所有知识库，批量删除指定类型的文件。
        适用于大规模清理操作。
        
        ⚠️ 警告：此操作会影响多个知识库，请谨慎使用！
        
        Args:
            workspace_id (str): 工作空间ID
            file_types (list[str]): 要删除的文件类型列表
                - 默认: ["png", "zip", "jpg", "jpeg"]
            folder_id (str): 文件夹ID（可选，限定清理范围）
            
        Returns:
            tuple[int, list, list]: (总删除数量, 所有失败记录, 各知识库结果)
                - total_failed: 包含 dataset_name 字段标识来源
                - dataset_results: 每个知识库的 dataset_id, dataset_name, 
                                   deleted_count, failed_count
        """
        if file_types is None:
            file_types = ["png", "zip", "jpg", "jpeg"]

        # 获取所有知识库
        status_code, datasets = self.list_datasets(workspace_id, folder_id)
        if status_code != 200:
            log.error(f"获取知识库列表失败: {datasets}")
            return 0, [], []

        total_deleted = 0
        total_failed = []
        dataset_results = []

        log.info(f"开始全局删除，共找到 {len(datasets)} 个知识库，要删除的文件类型: {file_types}")

        for dataset in datasets:
            dataset_id = dataset.get("id")
            dataset_name = dataset.get("name")
            log.info(f"正在处理知识库: {dataset_name} (ID: {dataset_id})")

            status, deleted_count, failed_list = self.delete_documents_by_types(dataset_id, file_types)
            
            if deleted_count > 0 or len(failed_list) > 0:
                dataset_results.append({
                    "dataset_id": dataset_id,
                    "dataset_name": dataset_name,
                    "deleted_count": deleted_count,
                    "failed_count": len(failed_list),
                })
                total_deleted += deleted_count
                total_failed.extend([{**f, "dataset_name": dataset_name} for f in failed_list])
                log.info(f"知识库 {dataset_name}: 删除 {deleted_count} 个文档，失败 {len(failed_list)} 个")

        log.info(f"全局删除完成，总共删除 {total_deleted} 个文档，失败 {len(total_failed)} 个")
        return total_deleted, total_failed, dataset_results

    def parse_excel_sheets(self, file_id: str, workspace_id: str) -> tuple[int, list | str]:
        """
        解析Excel工作表列表
        
        获取Excel文件中的所有工作表（sheet）信息，用于后续选择要处理的工作表。
        
        Args:
            file_id (str): 已上传的Excel文件ID
            workspace_id (str): 工作空间ID
            
        Returns:
            tuple[int, list | str]: (状态码, 工作表列表或错误信息)
                - 200: 成功，返回工作表列表，每个元素包含 name, index 等信息
                - 其他: 失败，返回错误信息
        """
        url = "http://10.4.49.66:18080/api/v1/console/datasets/parse-excel-sheets"
        
        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "X-Workspace-Id": workspace_id,
            "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
        }
        
        payload = {"file_id": file_id}
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            return response.status_code, response.json().get("msg", response.text)
        return 200, response.json().get("data", [])

    def parse_excel_headers(
        self, 
        file_id: str, 
        workspace_id: str,
        sheet_index: int = 0,
        header_row: list = None
    ) -> tuple[int, list | str]:
        """
        解析Excel表头
        
        获取指定工作表中的表头列信息，用于创建文档处理任务。
        
        Args:
            file_id (str): 已上传的Excel文件ID
            workspace_id (str): 工作空间ID
            sheet_index (int): 工作表索引，默认0（第一个工作表）
            header_row (list): 表头行范围，默认[1, 1]表示第1行为表头
            
        Returns:
            tuple[int, list | str]: (状态码, 表头列列表或错误信息)
                - 200: 成功，返回列信息列表，每个元素包含 name, dataType 等
                - 其他: 失败，返回错误信息
        """
        if header_row is None:
            header_row = [1, 1]
            
        url = "http://10.4.49.66:18080/api/v1/console/datasets/parse-excel-headers"
        
        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "X-Workspace-Id": workspace_id,
            "x-fly-tenantid": "00000000-0000-0000-0000-000000000000",
        }
        
        payload = {
            "file_id": file_id,
            "sheet_index": sheet_index,
            "header_row": header_row
        }
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            return response.status_code, response.json().get("msg", response.text)
        return 200, response.json().get("data", [])

    def create_excel_task(
        self,
        dataset_id: str,
        document_id: str,
        sheet_name: str,
        table_columns: list,
        header_range: list = None,
        workspace_id: str = None,
    ) -> tuple[int, dict | str]:
        """
        创建Excel文档处理任务
        
        专门用于处理Excel文件的任务创建，需要传入工作表名称和表头列信息。
        
        Args:
            dataset_id (str): 知识库ID
            document_id (str): 文档ID
            sheet_name (str): 工作表名称
            table_columns (list): 表头列信息列表，每个元素包含:
                - name: 列名
                - describe: 列描述（可选，默认空字符串）
                - dataType: 数据类型（可选，默认"String"）
            header_range (list): 表头行范围，默认[1, 1]
            workspace_id (str): 工作空间ID（可选，用于请求头认证）
            
        Returns:
            tuple[int, dict | str]: (状态码, 任务数据或错误信息)
                - 200: 成功，返回任务信息
                - 其他: 失败，返回错误信息
        """
        if header_range is None:
            header_range = [1, 1]
            
        # 使用 console API 创建任务
        url = f"http://10.4.49.66:18080/api/v1/console/datasets/{dataset_id}/documents/{document_id}/tasks"

        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if workspace_id:
            headers["X-Workspace-Id"] = workspace_id
            headers["x-fly-tenantid"] = "00000000-0000-0000-0000-000000000000"

        # 格式化表头列信息
        formatted_columns = []
        for i, col in enumerate(table_columns):
            formatted_columns.append({
                "name": col.get("name", f"列{i+1}"),
                "describe": col.get("describe", ""),
                "dataType": col.get("dataType", "String"),
            })

        payload = {
            "dataset_id": dataset_id,
            "document_id": document_id,
            "type": "normal",
            "splitter_mode": "common",
            "processing_config": {
                "chunk_size": 200,
                "overlap": 50,
                "chinese_title_enhance": False,
                "process_type": "NORMAL",
                "separators": "\\n",
                "replace_spaces_tabs": True,
                "delete_url_email": True,
                "parse_enhance": False,
                "parse_toc": False,
                "header_range": header_range,
                "sheet_name": sheet_name,
                "table_columns": formatted_columns,
            },
        }

        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            return response.status_code, response.json().get("msg", response.text)
        return 200, response.json().get("data")