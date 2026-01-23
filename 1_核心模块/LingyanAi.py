import json
import os
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
import logging

log = logging.getLogger("LingyanAi")


class LingyanAi:
    def __init__(self, app_id: str, api_key: str, stream: bool = False):
        self.app_id = app_id
        self.api_key = api_key
        self.stream = stream

    def chat(self, prompt: str, inputs_obj: dict) -> str:
        # 模拟调用大模型接口
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
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def upload_file(self, file_path: str, file_type: str = "app") -> tuple[int, dict]:
        """
        上传文件
        ----
        Args:
            file_path (str): 文件路径
            file_type (str): 文件业务类型
                - app: 应用
                - dataset: 知识库
                - tool: 工具
                - chat: 聊天
                - avatar: 头像
        """
        if file_type not in ["app", "dataset", "tool", "chat", "avatar"]:
            raise ValueError(
                "file_type must be one of ['app', 'dataset', 'tool', 'chat', 'avatar']"
            )

        url = "http://10.4.49.66:18080/api/v1/service/files/upload"

        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "python-requests/2.28.1",
            "Connection": "keep-alive",
            "content-type": "multipart/form-data; boundary=---011000010111000001101001",
        }

        f = open(file_path, "rb")
        encoder = MultipartEncoder(
            fields={
                "file": (os.path.basename(file_path), f, "application/pdf"),
                "biz_type": file_type,
            }
        )

        headers = {**headers, "Content-Type": encoder.content_type}  # 带 boundary

        response = requests.request("POST", url, data=encoder, headers=headers)

        f.close()
        return response.status_code, response.json().get("data")


    def download_file(self, file_id: str):
        url = f"http://10.4.49.66:18080/api/v1/service/files/{file_id}/download"
        response = requests.get(url, headers={"accept": "application/json", "X-API-Key": self.api_key})
        return response.status_code, response.content

def build_file_info(file_info):
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
    def __init__(self, api_key: str):
        self.api_key = api_key

    def list_datasets(self, workspace_id: str, folder_id: str | None = None):
        url = "http://10.4.49.66:18080/api/v1/service/datasets"
        datasets = []
        current_page = 1
        while True:
            response = requests.get(
                url,
                params={"workspace_id": workspace_id, "folder_id": folder_id, "page_size": 1000, "page": current_page},
                headers={"accept": "application/json", "X-API-Key": self.api_key},
            )
            if response.status_code != 200:
                return response.status_code, response.json().get("msg")
            data = response.json().get("data")
            if not data or len(data) == 0:
                break
            datasets.extend(data)
            current_page += 1
            log.info(f"获取知识库列表成功，长度 {len(data)}，当前页码 {current_page}")
        return 200, datasets

    def create_dataset(
        self, workspace_id: str, name: str, folder_id: str, description: str = ""
    ):
        # url = "http://10.4.49.66:18080/api/v1/service/datasets"

        # response = requests.post(
        #     url,
        #     json={
        #         "workspace_id": workspace_id,
        #         "name": name,
        #         "description": description,
        #         "folder_id": folder_id,
        #         "embedding_model": {
        #             "provider": "langgenius/openai_api_compatible/openai_api_compatible",
        #             "name": "Qwen3-Embedding-4B",
        #             "size": 4096,
        #         },
        #         "processing_config": {
        #             "chunk_size": 2000,
        #             "overlap": 50,
        #             "chinese_title_enhance": False,
        #             "process_type": "NORMAL",
        #             "separators": "\\n",
        #             "replace_spaces_tabs": False,
        #             "delete_url_email": False,
        #             "parse_enhance": True,
        #             "parse_toc": False,
        #             "index_config": {
        #                 "title": {
        #                     "provider": "langgenius/openai_api_compatible/openai_api_compatible",
        #                     "name": "deepseekv3-0324",
        #                     "mode": "chat",
        #                     "size": 8000,
        #                     "completion_params": {
        #                         "temperature": 0.2,
        #                         "top_p": 0.75,
        #                         "frequency_penalty": 0.5,
        #                         "presence_penalty": 0.5,
        #                         "max_tokens": 2000,
        #                     },
        #                 },
        #                 "summary": {
        #                     "provider": "langgenius/openai_api_compatible/openai_api_compatible",
        #                     "name": "deepseekv3-0324",
        #                     "mode": "chat",
        #                     "size": 8000,
        #                     "completion_params": {
        #                         "temperature": 0.2,
        #                         "top_p": 0.75,
        #                         "frequency_penalty": 0.5,
        #                         "presence_penalty": 0.5,
        #                         "max_tokens": 2000,
        #                     },
        #                 },
        #                 "question": {
        #                     "provider": "langgenius/openai_api_compatible/openai_api_compatible",
        #                     "name": "deepseekv3-0324",
        #                     "mode": "chat",
        #                     "size": 8000,
        #                     "completion_params": {
        #                         "temperature": 0.2,
        #                         "top_p": 0.75,
        #                         "frequency_penalty": 0.5,
        #                         "presence_penalty": 0.5,
        #                         "max_tokens": 2000,
        #                     },
        #                 },
        #             },
        #             "md_split_by_headers": False,
        #             "md_max_header_level": 3,
        #             "doc_summary": True,
        #             "doc_summary_config": {
        #                 "provider": "langgenius/openai_api_compatible/openai_api_compatible",
        #                 "name": "deepseekv3-0324",
        #                 "mode": "chat",
        #                 "size": 32768,
        #                 "completion_params": {
        #                     "temperature": 0.2,
        #                     "top_p": 0.75,
        #                     "frequency_penalty": 0.5,
        #                     "presence_penalty": 0.5,
        #                     "max_tokens": 2000,
        #                 },
        #             },
        #         },
        #     },
        #     headers={
        #         "accept": "application/json",
        #         "X-API-Key": self.api_key,
        #         "Content-Type": "application/json",
        #     },
        # )

        # if response.status_code != 200:
        #     return response.status_code, response.json().get("msg")
        return 200, ""

    def update_dataset(
        self,
        new_dataset:dict
    ):
        url = "http://10.4.49.66:18080/api/v1/service/datasets"
        headers = {
            "accept": "application/json",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        response = requests.put(url, json=new_dataset, headers=headers)

        if response.status_code != 200:
            return response.status_code, response.json().get("msg")
        return 200, response.json().get("data")

    def create_document(self, dataset_id: str, file_id: str):
        """
        创建文档
        ----
        Args:
            dataset_id (str): 知识库ID
            file_id (str): 文件ID
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents"
        payload = {
            "dataset_id": dataset_id,
            "file_ids": [file_id],
            "processing_config": {},
        }
        response = requests.post(
            url,
            json=payload,
            headers={
                "accept": "application/json",
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            return response.status_code, response.json().get("msg")
        return 200, response.json().get("data")

    def create_task(
        self,
        dataset_id,
        document_id,
        split_mode="semantic",
        task_type="normal",
        image_task=False,
        parse_enhance=True,
    ):
        """
        创建文档任务
        ----
        Args:
            dataset_id (str): 知识库ID
            file_id (str): 文件ID
            split_mode (str): 切分模式
                - auto: 自动切分
                - semantic: 语义化切分
            task_type (str): 任务类型
                - normal: 普通任务
                - image: 图片任务
            image_task (bool): 是否添加图片索引
            parse_enhance (bool): 是否增强解析
                - True: 精准解析
                - False: 目录解析
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents/{document_id}/tasks"

        payload = {
            "dataset_id": dataset_id,
            "document_id": document_id,
            "splitter_mode": split_mode,
            "type": task_type,
            # "processing_config": {
            #     "chunk_size": 2000,
            #     "overlap": 50,
            #     "chinese_title_enhance": False,
            #     "process_type": "NORMAL",
            #     "separators": "\\n",
            #     "replace_spaces_tabs": False,
            #     "delete_url_email": False,
            #     "parse_enhance": parse_enhance,
            #     "parse_toc": not parse_enhance,
            #     "index_config": {
            #         "title": {
            #             "provider": "langgenius/openai_api_compatible/openai_api_compatible",
            #             "name": "deepseekv3-0324",
            #             "mode": "chat",
            #             "size": 8000,
            #             "completion_params": {
            #                 "temperature": 0.2,
            #                 "top_p": 0.75,
            #                 "frequency_penalty": 0.5,
            #                 "presence_penalty": 0.5,
            #                 "max_tokens": 2000,
            #             },
            #         },
            #         "summary": {
            #             "provider": "langgenius/openai_api_compatible/openai_api_compatible",
            #             "name": "deepseekv3-0324",
            #             "mode": "chat",
            #             "size": 8000,
            #             "completion_params": {
            #                 "temperature": 0.2,
            #                 "top_p": 0.75,
            #                 "frequency_penalty": 0.5,
            #                 "presence_penalty": 0.5,
            #                 "max_tokens": 2000,
            #             },
            #         },
            #         "question": {
            #             "provider": "langgenius/openai_api_compatible/openai_api_compatible",
            #             "name": "deepseekv3-0324",
            #             "mode": "chat",
            #             "size": 8000,
            #             "completion_params": {
            #                 "temperature": 0.2,
            #                 "top_p": 0.75,
            #                 "frequency_penalty": 0.5,
            #                 "presence_penalty": 0.5,
            #                 "max_tokens": 2000,
            #             },
            #         },
            #     },
            #     "md_split_by_headers": False,
            #     "md_max_header_level": 3,
            #     "doc_summary": True,
            #     "doc_summary_config": {
            #         "provider": "langgenius/openai_api_compatible/openai_api_compatible",
            #         "name": "deepseekv3-0324",
            #         "mode": "chat",
            #         "size": 32768,
            #         "completion_params": {
            #             "temperature": 0.2,
            #             "top_p": 0.75,
            #             "frequency_penalty": 0.5,
            #             "presence_penalty": 0.5,
            #             "max_tokens": 2000,
            #         },
            #     },
            # },
        }

        # 如果是图片任务，则需要添加图片索引
        if image_task:
            payload["processing_config"]["index_config"]["image"] = {
                "provider": "langgenius/openai_api_compatible/openai_api_compatible",
                "name": "qwen2.5-vl-7b-instruct",
                "mode": "chat",
                "size": 8192,
                "completion_params": {
                    "temperature": 0.2,
                    "top_p": 0.75,
                    "max_tokens": 8192,
                },
            }

        response = requests.post(
            url,
            json=payload,
            headers={
                "accept": "application/json",
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            return response.status_code, response.json().get("msg")
        return 200, response.json().get("data")

    def check_file(self, file_name: str, dataset_id: str):
        """
        重名检测
        ----
        Args:
            file_name (str): 文件名
            dataset_id (str): 知识库ID
        Returns:
            status_code (int): 状态码
            data (dict): 数据
            duplicate_count (int): 重复数量
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents/check-names"
        payload = {
            "names": [file_name],
            "dataset_id": dataset_id,
        }
        response = requests.post(
            url,
            json=payload,
            headers={"accept": "application/json", "X-API-Key": self.api_key},
        )
        return (
            response.status_code,
            response.json().get("data"),
            response.json().get("data").get("duplicate_count"),
        )

    def list_documents(self, dataset_id: str):
        """
        获取文档列表
        ----
        Args:
            dataset_id (str): 知识库ID
        Returns:
            status_code (int): 状态码
            data (list): 数据
        """
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents"
        documents = []
        current_page = 1
        while True:
            response = requests.get(
                url,
                headers={"accept": "application/json", "X-API-Key": self.api_key},
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

    def delete_document(self, dataset_id: str, document_id: str, max_retries: int = 3):
        """
        删除文档
        ----
        Args:
            dataset_id (str): 知识库ID
            document_id (str): 文档ID
            max_retries (int): 最大重试次数，默认3次
        Returns:
            status_code (int): 状态码
            data (dict): 响应数据
        """
        import time
        
        url = f"http://10.4.49.66:18080/api/v1/service/datasets/{dataset_id}/documents/{document_id}"
        
        for attempt in range(max_retries):
            try:
                response = requests.delete(
                    url,
                    headers={"accept": "application/json", "X-API-Key": self.api_key},
                    timeout=60  # 60秒超时
                )
                if response.status_code != 200:
                    return response.status_code, response.json().get("msg")
                return 200, response.json().get("data")
            except requests.exceptions.RequestException as e:
                log.warning(f"删除文档请求失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # 等待2秒后重试
                else:
                    return 500, f"请求失败: {str(e)}"

    def delete_documents_by_types(self, dataset_id: str, file_types: list[str] = None):
        """
        删除知识库中指定类型的文档
        ----
        Args:
            dataset_id (str): 知识库ID
            file_types (list[str]): 要删除的文件类型列表，默认为 ["png", "zip", "jpg", "jpeg"]
                                    注意：类型不带点，如 "png" 而不是 ".png"
        Returns:
            status_code (int): 状态码
            deleted_count (int): 删除的文档数量
            failed_list (list): 删除失败的文档列表
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

        return 200, deleted_count, failed_list

    def delete_documents_global(self, workspace_id: str, file_types: list[str] = None, folder_id: str = None):
        """
        全局删除所有知识库中指定类型的文档
        ----
        Args:
            workspace_id (str): 工作空间ID
            file_types (list[str]): 要删除的文件类型列表，默认为 ["png", "zip", "jpg", "jpeg"]
            folder_id (str): 文件夹ID，可选
        Returns:
            total_deleted (int): 总共删除的文档数量
            total_failed (list): 所有删除失败的文档列表
            dataset_results (list): 每个知识库的删除结果
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