from enum import IntEnum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


# 物品状态枚举
class ItemStatus(IntEnum):
    AVAILABLE = 1  # 可用
    LENT = 0  # 已借出
    REPAIRING = 2  # 维修中
    SCRAPPED = 3  # 报废
    APPLYING = 4  # 申请中
    UNKNOWN = 5  # 未知


# 物品分类表 (item_category)
class ItemCategory(SQLModel, table=True):
    __tablename__ = "item_category"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    total: int = Field(default=0)

    # 关系: 一个分类包含多个物品列表
    item_lists: List["ItemList"] = Relationship(back_populates="category")


# 物品列表表 (item_list)
class ItemList(SQLModel, table=True):
    __tablename__ = "item_list"

    # 注意: 原逻辑中 ID 是手动计算生成的 (1000*category_id + x)，所以这里不用自增
    id: int = Field(primary_key=True)
    father: int = Field(foreign_key="item_category.id")
    name: str = Field(index=True)
    total: int = Field(default=0)
    free: int = Field(default=0)
    broken: int = Field(default=0)

    # 关系
    category: Optional[ItemCategory] = Relationship(
        back_populates="item_lists")
    items: List["ItemInfo"] = Relationship(back_populates="item_list")


# 物品详情表 (item_info)
class ItemInfo(SQLModel, table=True):
    __tablename__ = "item_info"

    # 注意: 原逻辑 ID 也是手动生成的
    id: int = Field(primary_key=True)
    father: int = Field(foreign_key="item_list.id")
    useable: int = Field(default=ItemStatus.AVAILABLE)  # 对应 ItemStatus
    wis: Optional[str] = Field(default=None)  # 位置/持有者
    do: Optional[str] = Field(default=None)  # 备注
    purpose: Optional[str] = Field(default=None)

    # 关系
    item_list: Optional[ItemList] = Relationship(back_populates="items")

    @property
    def status_str(self) -> str:
        """获取中文状态描述"""
        try:
            # 映射 IntEnum 到原有的中文字符串
            mapping = {
                1: '可用', 0: '已借出', 2: '维修中',
                3: '报废', 4: '申请中', 5: '未知'
            }
            return mapping.get(self.useable, '未知')
        except:
            return '未知'


# 用户表 (members)
class Member(SQLModel, table=True):
    __tablename__ = "members"

    user_id: str = Field(primary_key=True)
    open_id: Optional[str] = Field(default=None)
    union_id: Optional[str] = Field(default=None)
    name: str
    root: int = Field(default=0)  # 0:无权限, 1:管理员
    card_message_id: Optional[str] = Field(default=None)
    card_message_create_time: Optional[str] = Field(default=None)


# 日志表 (logs)
class Log(SQLModel, table=True):
    __tablename__ = "logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    # 建议迁移时改为 BigInt 存储毫秒级时间戳，或改为 DateTime
    time: int
    userId: str
    operation: str
    object: Optional[int] = Field(default=None)
    do: Optional[str] = Field(default="")

