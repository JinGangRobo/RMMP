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

#实现飞书机器人的命令行接口（还未实现qaq）
# --- 命令处理功能 ---
def handle_command(session: Session, user_id: str, command: str, sender_id: dict = None) -> str:
    """
    处理命令
    :param session: 数据库会话
    :param user_id: 用户ID
    :param command: 命令字符串
    :param sender_id: 发送者ID信息
    :return: 处理结果
    """
    import re
    
    if not command.startswith('/'):
        return None  # 不是命令，返回None
    
    # 命令映射
    command_map = {
        'help': _handle_help_command,
        'add': _handle_add_command,
        'del': _handle_del_command,
        'search': _handle_search_command,
        'return': _handle_return_command,
    }
    
    # 解析命令
    parts = command.strip().split()
    if len(parts) < 1:
        return "Error: 无效的命令格式"
    
    cmd = parts[0][1:]  # 去掉开头的'/'
    if cmd not in command_map:
        return f"Error: 未知命令 '{cmd}'，输入 /help 查看帮助"
    
    # 检查权限
    member = session.get(Member, user_id)
    if not member:
        return "Error: 用户不存在"
    
    # 特定命令需要管理员权限
    admin_commands = ['add', 'del']
    if cmd in admin_commands and member.root != 1:
        return "Error: 权限不足"
    
    # 执行命令
    try:
        return command_map[cmd](session, user_id, parts[1:], member)
    except Exception as e:
        return f"Error: 命令执行失败 - {str(e)}"


def _handle_help_command(session: Session, user_id: str, params: list, member: Member) -> str:
    """处理帮助命令"""
    help_text = (
        "机器人命令指南：\n"
        "/help - 查看帮助\n"
        "/search <id> - 搜索ID对应的项\n"
        "/return <id> - 归还ID对应的物品\n"
        "管理员命令：\n"
        "/add <item|list|category> [params] - 添加数据\n"
        "/del <item|list|category> [params] - 删除数据\n"
    )
    return help_text


def _handle_add_command(session: Session, user_id: str, params: list, member: Member) -> str:
    """处理添加命令"""
    if len(params) < 2:
        return "Error: 参数不足，格式: /add <item|list|category> [params]"
    
    obj_type = params[0]
    if obj_type not in ['item', 'list', 'category']:
        return "Error: 对象类型错误，应为 item|list|category"
    
    # 这里需要根据具体参数实现添加逻辑
    # 暂时返回提示信息
    return f"Info: 添加 {obj_type} 功能待实现"


def _handle_del_command(session: Session, user_id: str, params: list, member: Member) -> str:
    """处理删除命令"""
    if len(params) < 2:
        return "Error: 参数不足，格式: /del <item|list|category> [params]"
    
    obj_type = params[0]
    if obj_type not in ['item', 'list', 'category']:
        return "Error: 对象类型错误，应为 item|list|category"
    
    # 这里需要根据具体参数实现删除逻辑
    # 暂时返回提示信息
    return f"Info: 删除 {obj_type} 功能待实现"


def _handle_search_command(session: Session, user_id: str, params: list, member: Member) -> str:
    """处理搜索命令"""
    if len(params) < 1:
        return "Error: 请提供要搜索的ID，格式: /search <id>"
    
    try:
        obj_id = int(params[0])
        # 这里需要根据ID类型返回相应信息
        # 暂时返回提示信息
        return f"Info: 搜索ID {obj_id} 功能待实现"
    except ValueError:
        return "Error: ID必须是数字"


def _handle_return_command(session: Session, user_id: str, params: list, member: Member) -> str:
    """处理归还命令"""
    if len(params) < 1:
        return "Error: 请提供要归还的物品ID，格式: /return <id>"
    
    try:
        obj_id = int(params[0])
        result = return_item(session, obj_id, user_id)
        return result
    except ValueError:
        return "Error: 物品ID必须是数字"


# --- 飞书服务功能 ---
def send_message_to_user(user_id: str, message: str, id_type: str = "open_id"):
    """
    发送消息给指定用户
    :param user_id: 用户ID
    :param message: 消息内容
    :param id_type: ID类型，默认为open_id
    :return: 消息发送结果
    """
    try:
        from app.core.feishu import send_text_message
        result = send_text_message(user_id, message, id_type)
        return result
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"发送消息失败: {e}")
        return None


def send_notification_to_group(chat_id: str, message: str):
    """
    发送通知到群组
    :param chat_id: 群组ID
    :param message: 消息内容
    :return: 消息发送结果
    """
    try:
        from app.core.feishu import send_text_message
        result = send_text_message(chat_id, message, "chat_id")
        return result
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"发送群组消息失败: {e}")
        return None


def get_user_info(user_id: str, id_type: str = "open_id"):
    """
    获取用户信息
    :param user_id: 用户ID
    :param id_type: ID类型
    :return: 用户信息
    """
    try:
        from app.core.feishu import api_client
        from lark_oapi.api.im.v1 import GetUserRequest
        request = GetUserRequest.builder() \
            .user_id_type(id_type) \
            .user_id(user_id) \
            .build()

        response = api_client.contact.v3.user.get(request)

        if response.success():
            return response.data.user
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"获取用户信息失败: {response.code}, {response.msg}")
            return None
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"获取用户信息异常: {e}")
        return None


def create_group_chat(user_ids: list, name: str = ""):
    """
    创建群聊
    :param user_ids: 用户ID列表
    :param name: 群聊名称
    :return: 群聊信息
    """
    try:
        from app.core.feishu import api_client
        from lark_oapi.api.im.v1 import CreateChatRequest, CreateChatRequestBody
        request_body = CreateChatRequestBody.builder() \
            .name(name) \
            .user_ids(user_ids) \
            .build()

        request = CreateChatRequest.builder().request_body(request_body).build()

        response = api_client.im.v1.chat.create(request)

        if response.success():
            return response.data.chat
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"创建群聊失败: {response.code}, {response.msg}")
            return None
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"创建群聊异常: {e}")
        return None