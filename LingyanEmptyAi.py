import json
import os
import uuid
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder


class LingyanAi:
    def __init__(self, app_id: str, api_key: str, stream: bool = False):
        self.app_id = app_id
        self.api_key = api_key
        self.stream = stream

    def chat(self, prompt: str, inputs_obj: dict) -> str:
        # 模拟返回，用于本地测试
        return 200, "模拟的AI回答"


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
        # 模拟返回，用于本地测试
        return 200, {"id": str(uuid.uuid4())}


def build_file_info(file_info):
    # 模拟返回，用于本地测试
    return {
        "id": None,
        "filename": file_info.get("name") if file_info else None,
        "size": file_info.get("size") if file_info else None,
        "type": file_info.get("file_type") if file_info else None,
        "mime_type": file_info.get("mime_type") if file_info else None,
        "remote_url": file_info.get("url") if file_info else None,
        "tenant_id": "00000000-0000-0000-0000-000000000000",
    }


class LingyanDataset:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def list_datasets(self, workspace_id: str, folder_id: str | None = None):
        # 模拟返回，用于本地测试
        return 200, []

    def create_dataset(
        self, workspace_id: str, name: str, folder_id: str, description: str = ""
    ):
        # 模拟返回，用于本地测试
        return 200, {"name": name, "id": str(uuid.uuid4())}

    def create_document(self, dataset_id: str, file_id: str):
        """
        创建文档
        ----
        Args:
            dataset_id (str): 知识库ID
            file_id (str): 文件ID
        """
        # 模拟返回，用于本地测试
        return 200, [{"id": str(uuid.uuid4())}]

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
        # 模拟返回，用于本地测试
        return 200, {"id": str(uuid.uuid4()), "status": "pending"}

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
        # 模拟返回，用于本地测试（默认无重名）
        return 200, {"duplicate_count": 0}, 0
