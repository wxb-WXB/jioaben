from peewee import SqliteDatabase, Model, IntegerField, CharField


db = SqliteDatabase('folder.db')

class FolderMap(Model):
    id = CharField(primary_key=True)
    name = CharField()
    folderPath = CharField(unique=True)
    class Meta:
        database = db

db.connect()
db.create_tables([FolderMap])