from sqlmodel import SQLModel, Session, create_engine

from app.core.config import settings

# 创建数据库引擎
engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI), echo=True)


def create_db_and_tables():
    """创建数据库和表"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """获取数据库会话"""
    with Session(engine) as session:
        yield session
