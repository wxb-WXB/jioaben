"""
数据库模型模块
=============

使用Peewee ORM的SQLite数据库模型。
"""
import os
from peewee import SqliteDatabase, Model, CharField

from ..config import DATA_DIR

# 数据库文件路径
db_path = os.path.join(DATA_DIR, 'folder.db')
db = SqliteDatabase(db_path)


class FolderMap(Model):
    """
    目录映射模型
    
    将远程目录ID映射到本地目录路径。
    
    Attributes:
        id: 目录UUID（主键）
        name: 目录名称
        folderPath: 完整本地路径
    """
    id = CharField(primary_key=True)
    name = CharField()
    folderPath = CharField(unique=True)
    
    class Meta:
        database = db


# 初始化数据库
db.connect()
db.create_tables([FolderMap])
