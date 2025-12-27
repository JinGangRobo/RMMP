import time
from typing import List, Optional

from sqlmodel import Session, func, select

from app.models.models import ItemCategory, ItemInfo, ItemList, ItemStatus, \
    Log, Member


# --- 辅助逻辑 ---
def sync_item_counts(session: Session, list_id: int):
    """
    重新计算指定物品列表及其父分类的 total/free/broken 数量
    替代原有的 MySQL 触发器逻辑
    """
    # 1. 统计 ItemInfo
    stmt_total = select(func.count(ItemInfo.id)).where(
        ItemInfo.father == list_id)
    stmt_free = select(func.count(ItemInfo.id)).where(
        ItemInfo.father == list_id,
        ItemInfo.useable == ItemStatus.AVAILABLE)
    stmt_broken = select(func.count(ItemInfo.id)).where(
        ItemInfo.father == list_id,
        ItemInfo.useable == ItemStatus.SCRAPPED)

    total = session.exec(stmt_total).one() or 0
    free = session.exec(stmt_free).one() or 0
    broken = session.exec(stmt_broken).one() or 0

    # 2. 更新 ItemList
    item_list = session.get(ItemList, list_id)
    if item_list:
        item_list.total = total
        item_list.free = free
        item_list.broken = broken
        session.add(item_list)

        # 3. 更新 ItemCategory (父级)
        category_id = item_list.father
        stmt_cat_total = select(func.sum(ItemList.total)).where(
            ItemList.father == category_id)
        cat_total = session.exec(stmt_cat_total).one() or 0

        category = session.get(ItemCategory, category_id)
        if category:
            category.total = cat_total
            session.add(category)

        session.commit()


# --- 业务逻辑 ---

def get_categories(session: Session) -> List[dict]:
    """获取所有分类"""
    cats = session.exec(select(ItemCategory)).all()
    return [{"id": c.id, "name": c.name, "total": c.total} for c in cats]


def add_category(session: Session, name: str) -> int:
    """添加分类"""
    existing = session.exec(
        select(ItemCategory).where(ItemCategory.name == name)).first()
    if existing:
        return existing.id

    # 计算新ID (模拟原有逻辑: max_id + 1)
    max_id = session.exec(select(func.max(ItemCategory.id))).one() or 0
    new_cat = ItemCategory(id=max_id + 1, name=name)
    session.add(new_cat)
    session.commit()
    session.refresh(new_cat)
    return new_cat.id


def add_list(session: Session, name: str, category_id: int) -> int:
    """添加物品列表定义 (如: '电机')"""
    existing = session.exec(
        select(ItemList).where(ItemList.name == name)).first()
    if existing:
        return existing.id

    # 计算新ID: (1000 * category_id) + (当前该分类下最大后缀 + 1)
    # 原逻辑: int(self_recoder[-1][0])%1000 + 1
    # 对应 SQLModel 查询:
    sub_items = session.exec(
        select(ItemList).where(ItemList.father == category_id)).all()

    if sub_items:
        last_id = sub_items[-1].id  # 假设按插入顺序或ID排序
        suffix = (last_id % 1000) + 1
    else:
        suffix = 1

    new_id = (1000 * category_id) + suffix

    new_list = ItemList(id=new_id, father=category_id, name=name)
    session.add(new_list)
    session.commit()
    return new_id


def add_item(
        session: Session,
        name_id: int,  # ItemList 的 ID
        num: int = 1,
        num_broken: int = 0,
        wis: str = "未知",
        do: str = "无"
):
    """
    添加具体物品实体
    """
    # 获取当前该列表下已有的物品，用于生成 ID
    existing_items = session.exec(
        select(ItemInfo).where(ItemInfo.father == name_id).order_by(
            ItemInfo.id.desc())).all()

    base_suffix = 1
    if existing_items:
        # 原逻辑: int(self_recoder[-1][0])%1000 + 1
        base_suffix = (existing_items[0].id % 1000) + 1

    for i in range(num):
        # 构造 ID: name_id * 1000 + count
        # 注意: 这种 ID 生成方式在当物品数量超过 999 时会溢出冲突，但为了保持兼容这里沿用
        new_item_id = (name_id * 1000) + base_suffix + i

        # 判断是否是损坏的
        status = ItemStatus.SCRAPPED if i < num_broken else ItemStatus.AVAILABLE

        item = ItemInfo(
            id=new_item_id,
            father=name_id,
            useable=status,
            wis=wis,
            do=do
        )
        session.add(item)

    session.commit()
    # 触发统计更新
    sync_item_counts(session, name_id)


def get_item_detail(session: Session, oid: int) -> Optional[dict]:
    """获取单个物品详情"""
    item = session.get(ItemInfo, oid)
    if not item:
        return None

    # 加载关联的 ItemList 以获取名称
    # 由于定义了 Relationship，SQLModel 会自动处理延迟加载，
    # 但为了性能最好使用 select(ItemInfo).options(selectinload(ItemInfo.item_list))...
    # 这里简单处理
    item_list_name = item.item_list.name if item.item_list else "未知"

    return {
        "name": item_list_name,
        "id": item.id,
        "father": item.father,
        "useable": item.status_str,
        "wis": item.wis or "未知",
        "do": item.do or "无"
    }


def apply_item(session: Session, oid: int, user_id: str, do: str):
    """申请物品"""
    return set_item_state(session, oid, user_id, "APPLY",
                          ItemStatus.APPLYING, do=do)


def return_item(session: Session, oid: int, user_id: str) -> str:
    """归还物品"""
    item = session.get(ItemInfo, oid)
    if not item:
        return f"Error: 无法找到物品 {oid}"

    member = session.get(Member, user_id)
    if not member:
        return f"Error: 用户 {user_id} 不存在"

    if item.useable == ItemStatus.SCRAPPED:
        return "Error: 它已经报废了"

    if item.useable == ItemStatus.APPLYING:
        return "Error: 该物品正在申请中"

    # 权限检查
    if item.wis != member.name and member.root != 1:
        return "Error: 你不是该物品的持有者"

    set_item_state(
        session,
        oid,
        user_id,
        "RETURN",
        ItemStatus.AVAILABLE,
        wis="仓库",
        do="null"
    )

    is_helper = member.root == 1
    item_name = item.item_list.name if item.item_list else ""
    return f'你{"帮忙" if is_helper else ""}归还了物品 {item_name} oid:{oid}'


def set_item_state(
        session: Session,
        oid: int,
        user_id: str,
        operation: str,
        useable: int,
        wis: Optional[str] = None,
        do: Optional[str] = None
):
    """底层状态更新函数"""
    # 记录日志
    log = Log(
        time=int(time.time() * 1000),
        userId=user_id,
        operation=operation,
        object=oid,
        do=do
    )
    session.add(log)

    # 更新物品
    item = session.get(ItemInfo, oid)
    if item:
        item.useable = useable
        if wis is not None:
            item.wis = wis
        session.add(item)
        session.commit()
        # 更新统计
        sync_item_counts(session, item.father)
