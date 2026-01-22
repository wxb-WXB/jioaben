import logging
from pathlib import Path
from typing import List
import os

def collect_files(base_folder):
    file_dict = {}
    for root, _, files in os.walk(base_folder):
        rel_dir = os.path.relpath(root, base_folder)
        rel_dir = "" if rel_dir == "." else rel_dir  # 根目录特殊处理
        for file in files:
            # 拼接相对路径并保证不用前置 "./"
            path = os.path.join(rel_dir, file) if rel_dir else file
            file_dict[file] = path.replace("\\", "/")  # 统一使用正斜杠
    return file_dict


def get_file_relative_dir(file_path, root_dir) -> str:
    """
    传入文件的完整路径和根目录，返回 {文件名: 文件目录的相对路径（以根目录开始，不含文件名）}
    如果文件就在根目录下，相对路径返回空字符串 ''
    """
    # 文件相对于根目录的路径
    rel_path = os.path.relpath(file_path, root_dir)
    # 只保留目录部分
    file_dir = os.path.dirname(rel_path).replace("\\", "/")  # 统一使用正斜杠
    return file_dir


def is_hidden(path: Path) -> bool:
    # 判断路径中任一部分是否以点开头（隐藏文件或隐藏目录）
    return any(part.startswith(".") for part in path.parts)


def list_files(
    root: Path,
    pattern: str = "*",
    absolute: bool = False,
    skip_hidden: bool = False,
    sort_output: bool = True,
) -> List[str]:
    """
    列出文件并返回路径字符串列表。
    - root: Path 对象，目录
    - pattern: glob 模式
    - absolute: 是否返回绝对路径
    - skip_hidden: 是否跳过隐藏文件/目录
    - sort_output: 是否按字典序排序
    返回: List[str] 路径列表（根据文件名去重，不包括后缀）
    """
    if not isinstance(root, Path):
        root = Path(root)

    if not root.exists():
        raise FileNotFoundError(f"路径不存在：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"不是目录：{root}")

    # 使用 rglob 递归按 pattern 搜索
    files = [p for p in root.rglob(pattern) if p.is_file()]

    if skip_hidden:
        files = [p for p in files if not is_hidden(p.relative_to(root))]

    if sort_output:
        files.sort(key=lambda p: p.as_posix())

    # 根据文件名（不包括后缀）去重
    seen_names = {}  # {基础文件名: 文件路径}
    outs: List[str] = []
    for p in files:
        # 获取文件名（不包括后缀）
        base_name = p.stem
        # 如果这个基础文件名还没见过，添加到结果中
        if base_name not in seen_names:
            seen_names[base_name] = True
            out = p.resolve().as_posix() if absolute else p.as_posix()
            outs.append(out)

    return outs

def fileTail2FileType(file_tail: str) -> str:
    """
    根据文件后缀返回文件类型
    """
    file_tail = file_tail.lower()
    if file_tail in [".doc", ".docx", ".pdf", ".txt"]:
        return "document"
    elif file_tail in [".jpg", ".jpeg", ".png", ".bmp", ".gif"]:
        return "image"
    elif file_tail in [".xls", ".xlsx", ".csv"]:
        return "spreadsheet"
    elif file_tail in [".ppt", ".pptx"]:
        return "presentation"


def pdf_has_images(pdf_path: str, method: str = "pymupdf") -> bool:
    """
    判断PDF文件中是否包含图片

    Args:
        pdf_path (str): PDF文件路径
        method (str): 检测方法，可选 "pymupdf" 或 "pypdf"，默认为 "pymupdf"

    Returns:
        bool: 如果PDF包含图片返回True，否则返回False
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在：{pdf_path}")

    if method == "pymupdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("请先安装 PyMuPDF 库：pip install PyMuPDF")

        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                # 获取页面中的所有图像
                image_list = page.get_images()
                if image_list:
                    doc.close()
                    return True
            doc.close()
            return False
        except Exception as e:
            logging.warning(f"使用PyMuPDF检测图片时出错：{str(e)}")
            return False

    elif method == "pypdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("请先安装 pypdf 库：pip install pypdf")

        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                # 检查页面资源中是否包含图像对象
                if "/XObject" in page.get("/Resources", {}):
                    xObject = page["/Resources"]["/XObject"].get_object()
                    for obj in xObject:
                        if xObject[obj]["/Subtype"] == "/Image":
                            return True
            return False
        except Exception as e:
            logging.warning(f"使用pypdf检测图片时出错：{str(e)}")
            return False

    else:
        raise ValueError(f"不支持的方法：{method}，请使用 'pymupdf' 或 'pypdf'")


def pdf_get_image_count(pdf_path: str, method: str = "pymupdf") -> int:
    """
    获取PDF文件中的图片数量

    Args:
        pdf_path (str): PDF文件路径
        method (str): 检测方法，可选 "pymupdf" 或 "pypdf"，默认为 "pymupdf"

    Returns:
        int: PDF中图片的数量
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在：{pdf_path}")

    if method == "pymupdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("请先安装 PyMuPDF 库：pip install PyMuPDF")

        try:
            doc = fitz.open(pdf_path)
            total_images = 0
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                total_images += len(image_list)
            doc.close()
            return total_images
        except Exception as e:
            raise Exception(f"使用PyMuPDF统计图片时出错：{str(e)}")

    elif method == "pypdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("请先安装 pypdf 库：pip install pypdf")

        try:
            reader = PdfReader(pdf_path)
            image_count = 0
            for page in reader.pages:
                if "/XObject" in page.get("/Resources", {}):
                    xObject = page["/Resources"]["/XObject"].get_object()
                    for obj in xObject:
                        if xObject[obj]["/Subtype"] == "/Image":
                            image_count += 1
            return image_count
        except Exception as e:
            raise Exception(f"使用pypdf统计图片时出错：{str(e)}")

    else:
        raise ValueError(f"不支持的方法：{method}，请使用 'pymupdf' 或 'pypdf'")

def is_pdf_file(file_path: str) -> bool:
    """
    判断文件是否为PDF文件
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在：{file_path}")
    return file_path.endswith(".pdf")