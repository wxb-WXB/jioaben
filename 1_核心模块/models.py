import os
from peewee import SqliteDatabase, Model, IntegerField, CharField

# 数据库文件放在项目根目录（1_核心模块的上一级目录）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(project_root, 'folder.db')
db = SqliteDatabase(db_path)

class FolderMap(Model):
    id = CharField(primary_key=True)
    name = CharField()
    folderPath = CharField(unique=True)
    class Meta:
        database = db

db.connect()
db.create_tables([FolderMap])