import json
import logging
import os
from LingyanAi import LingyanDataset, LingyanAi, LingyanFile, build_file_info
import pytest

from utils import pdf_has_images


def test_file_upload_and_chat():
    app_id = "5519ec43-13ec-41d5-a25c-e8386f2a613b"
    api_key = "sk-QYeWNYUfA4AWGRJ1v4QZUFG0V8unTwWgGPOG1GNo"
    lingyan_ai = LingyanAi(app_id, api_key)
    lingyanFile = LingyanFile(api_key)

    # 上传文件
    file_info = lingyanFile.upload_file(
        r"D:\新建文件夹\1月新进\安全环保应急部\《施工脚手架通用规范》（GB55023-2022）.pdf",
        file_type="app"
    )

    input_file = build_file_info(file_info)

    chat_result = lingyan_ai.chat(
        "1",
        {
            "file": {
                "id": "86c71e88-72e5-4125-85b8-58d0bf7660f8",
                "name": "附件1.国铁集团关于加强涉铁工程管理的指导意见（铁工电〔2021〕85号）.pdf",
                "size": 479492,
                "extension": "pdf",
                "mime_type": "application/pdf",
                "file_type": "document",
                "url": "http://10.4.49.67:29000/flygpt/chat/dff4e2cb-1be0-4718-b25c-f167c9d55a58/62db60ae-8b8c-4915-bd0a-83bbe484acbb.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=minio%2F20260107%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20260107T035947Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=93e315f1ae45d0f203027bd7952986e3de3413126488e66d680c33a3eb7d0de3",
                "created_by": "dff4e2cb-1be0-4718-b25c-f167c9d55a58",
                "created_at": "2026-01-07T11:59:47.093244+08:00",
            },
            "output_obj": "是",
        },
    )
    format_result = json.loads(chat_result)

def test_list_datasets():
    api_key = "sk-4fMfUijItQbsAsyZJttC31QHp7U77Eso2OqFxlxd"
    fly_dataset = LingyanDataset(api_key)
    datasets = fly_dataset.list_datasets("3472af5f-e1c2-476e-89d6-64dc9d7988cb")
    assert isinstance(datasets, list)
    assert len(datasets) > 0

def test_create_dataset():
    api_key = "sk-4fMfUijItQbsAsyZJttC31QHp7U77Eso2OqFxlxd"
    fly_dataset = LingyanDataset(api_key)
    dataset = fly_dataset.create_dataset(
        workspace_id="3472af5f-e1c2-476e-89d6-64dc9d7988cb",
        name="api测试数据集",
        description="这是一个用于测试的数据集，用于测试服务api",
    )
    assert dataset.get("name") == "api测试数据集"
    assert dataset.get("description") == "这是一个用于测试的数据集，用于测试服务api"

def test_upload_file():
    file_path = "./testBaseFolder/F1/F1-1/16.2地心泵站.pdf"
    workspace_id = "3472af5f-e1c2-476e-89d6-64dc9d7988cb"
    api_key = "sk-4fMfUijItQbsAsyZJttC31QHp7U77Eso2OqFxlxd"

    lingyanFile = LingyanFile(api_key=api_key)
    response_status, response = lingyanFile.upload_file(
        file_path,
        "dataset"
    )
    file_id = response.get("id")
    assert response_status == 200

    assert response.get("name") == "16.2地心泵站.pdf"
    assert file_id is not None
    return file_id, os.path.splitext(response.get("name"))[0]

def test_create_document_for_dataset():
    workspace_id = "3472af5f-e1c2-476e-89d6-64dc9d7988cb"
    dataset_id = "a2ee99ed-0787-4779-baa0-2a021769ce94"  # 知识库id
    # dataset_id = "a2ee99ed-0787-4779-baa0-2a021769ce94"
    api_key = "sk-4fMfUijItQbsAsyZJttC31QHp7U77Eso2OqFxlxd"
    file_id, file_name = test_upload_file()

    lingyanDataset = LingyanDataset(api_key=api_key)
    # 重名检测
    response_status, response, duplicate_count = lingyanDataset.check_file(
        file_name=file_name,
        dataset_id=dataset_id
    )
    assert response_status == 200
    assert duplicate_count == 0

    # 添加文档
    response_status, response = lingyanDataset.create_document(
        dataset_id=dataset_id,
        file_id=file_id
    )
    logging.info(f"状态码{response_status}，响应内容：{response}")
    assert response_status == 200
    assert response

def test_get_all_datasets():
    api_key = "sk-4fMfUijItQbsAsyZJttC31QHp7U77Eso2OqFxlxd"
    workspace_id = "3472af5f-e1c2-476e-89d6-64dc9d7988cb"
    lingyanDataset = LingyanDataset(api_key=api_key)

    response_status, datasets = lingyanDataset.list_datasets(workspace_id=workspace_id)
    assert response_status == 200
    logging.info(f"获取到知识库列表，数量：{len(datasets)}")
    logging.info(datasets)
    pass

def test_create_document_and_task():
    api_key = "sk-4fMfUijItQbsAsyZJttC31QHp7U77Eso2OqFxlxd"
    workspace_id = "3472af5f-e1c2-476e-89d6-64dc9d7988cb"
    dataset_id = "a2ee99ed-0787-4779-baa0-2a021769ce94"
    file_id = test_upload_file()
    lingyanDataset = LingyanDataset(api_key=api_key)
    response_status, response = lingyanDataset.create_document(
        dataset_id=dataset_id,
        file_id=file_id
    )
    document_id = response[0].get("id")
    assert response_status == 200
    assert response

    response_status, response = lingyanDataset.create_task(
        dataset_id=dataset_id,
        document_id=document_id
    )
    assert response_status == 200
    assert response

def test_img_in_file():
    file_path = r"D:\code\code_python\test\分类3\工程设计知识库\前期设计报告\1_分干线管道设计汇报.pdf"
    has_img = pdf_has_images(file_path)
    assert has_img == True