import os
import requests

from LingyanAi import LingyanDataset, LingyanFile
from utils import is_pdf_file, list_files, pdf_has_images

dataset_id = "eb0f701a-de5c-4b95-b8d9-31d9c67c7bc2"
api_key = "sk-mZaD8UalsAxMa9E87rn2zmptaeu0XW2wH7LkcKxS"

lingyanDataset = LingyanDataset(api_key)
lingyanFile = LingyanFile(api_key)

upload_folder = "download"

all_file_paths = list_files(
    root=upload_folder,
    pattern="*",
    absolute=False,
    skip_hidden=True,
)

for file_path in all_file_paths:
    # 重名检测
    file_name = os.path.basename(file_path)
    response_code, response, duplicate_count = lingyanDataset.check_file(file_name, dataset_id)
    if response_code != 200:
        print(f"重名检测失败: {response_code}, {response}")
        continue
    if duplicate_count > 0:
        print(f"重名文件: {file_path}")
        continue

    # 上传文件
    status_code, response = lingyanFile.upload_file(file_path, "dataset")
    if status_code != 200:
        print(f"上传文件失败: {status_code}, {response}")
        continue
    print(f"上传文件成功: {file_path}")

    file_id = response.get("id")
    # 创建文档
    response_code, response = lingyanDataset.create_document(dataset_id, file_id)
    if response_code != 200:
        print(f"创建文档失败: {response_code}, {response}")
        continue
    print(f"创建文档成功: {file_path}")

    document_id = response[0].get("id")

    # 查看文件是否有图片
    is_pdf = is_pdf_file(file_path)
    if is_pdf:
        has_image = pdf_has_images(file_path)
    else:
        has_image = False

    # 创建任务
    response_code, response = lingyanDataset.create_task(dataset_id, document_id, image_task=has_image)
    if response_code != 200:
        print(f"创建任务失败: {response_code}, {response}")
        continue
    print(f"创建任务成功: {file_path}")
