import logging
import json
from datetime import datetime, timezone, timedelta

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, \
    CreateMessageRequestBody, P2ImMessageReceiveV1
from lark_oapi.api.application.v6 import *
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# ==========================================
# 全局 API 客户端 (用于主动发送请求)
# ==========================================

# 初始化全局 Client，它会自动管理 Token
api_client = lark.Client.builder() \
    .app_id(settings.FEISHU_APP_ID) \
    .app_secret(settings.FEISHU_APP_SECRET) \
    .log_level(lark.LogLevel.DEBUG) \
    .build()

def send_message(receive_id_type, receive_id, msg_type, content):
    """
    发送消息的通用方法
    :param receive_id_type: 接收者ID类型 (open_id, user_id, union_id, email, chat_id)
    :param receive_id: 接收者ID
    :param msg_type: 消息类型 (text, image, file, interactive 等)
    :param content: 消息内容，根据消息类型不同格式也不同
    """
    request = (
        CreateMessageRequest.builder()
        .receive_id_type(receive_id_type)
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type(msg_type)
            .content(content)
            .build()
        )
        .build()
    )

    response = api_client.im.v1.message.create(request)
    if not response.success():
        logger.error(
            f"发送消息失败: code={response.code}, msg={response.msg}, log_id={response.get_log_id()}"
        )
        raise Exception(
            f"api_client.im.v1.message.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
        )
    return response

def send_text_message(receive_id: str, text: str, receive_id_type: str = "open_id"):
    """
    发送文本消息
    :param receive_id: 接收者ID
    :param text: 文本内容
    :param receive_id_type: ID类型，默认 open_id
    """
    content = json.dumps({"text": text})
    return send_message(receive_id_type, receive_id, "text", content)

#发送物资卡片
def send_Allince_card(open_id):
    content = json.dumps(
        {
            "type": "template",
            "data": {
                "template_id": settings.ALLIANCE_CARD_ID,  # 使用配置中的卡片ID
                "template_variable": {"open_id": open_id},
            },
        }
    )
    return send_message("open_id", open_id, "interactive", content)
def do_p2_application_bot_menu_v6(data: P2ApplicationBotMenuV6) -> None:
    """
    处理用户点击机器人菜单事件
    :param data: 事件数据
    """
    logger.info(f"[用户点击机器人菜单事件] data: {data}")
    open_id = data.event.operator.operator_id.open_id
    event_key = data.event.event_key

    # 通过菜单 event_key 区分不同菜单。 你可以在开发者后台配置菜单的event_key
    if event_key == "send_welcome":
        send_Allince_card(open_id)

# 处理用户发送的消息（包括单聊和群聊）
def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    """
    接收用户发送的消息（包括单聊和群聊），根据消息内容执行相应操作
    :param data: 事件数据
    """
    logger.info(f"[用户消息接收事件] data: {data}")
    chat_type = data.event.message.chat_type
    chat_id = data.event.message.chat_id
    open_id = data.event.sender.sender_id.open_id
    
    # 解析消息内容
    try:
        # 获取消息内容
        content_json = data.event.message.content
        content_dict = json.loads(content_json)
        text_content = content_dict.get("text", "").strip()
        
        # 检查是否是命令
        if text_content.startswith('/'):
            from app.core.database import get_session
            from app.services.services import handle_command
            
            # 从请求上下文中获取会话，或创建新会话
            # 由于不能直接获取session，这里使用with语句创建
            from app.core.database import engine
            from sqlmodel import Session
            with Session(engine) as session:
                result = handle_command(session, open_id, text_content)
                if result:
                    # 发送命令执行结果
                    send_text_message(open_id, result, "open_id")
        else:
            # 非命令消息的处理
            if chat_type == "group":
                send_Allince_card(open_id)
            elif chat_type == "p2p":
                send_Allince_card(open_id)
    except Exception as e:
        logger.error(f"处理消息时出错: {e}")
        # 发送错误信息给用户
        send_text_message(open_id, f"处理您的消息时出现错误: {str(e)}", "open_id")

# 处理卡片交互事件
def do_p2_card_action_trigger(data: P2CardActionTrigger) -> None:
    """
    处理卡片交互事件
    :param data: 事件数据
    """
    logger.info(f"[卡片交互事件] data: {data}")
    # 这里需要根据实际需求实现卡片交互逻辑
    # 目前为空实现，后续可以扩展
    pass
# 处理用户进入机器人单聊事件
def do_p2_im_chat_access_event_bot_p2p_chat_entered_v1(
    data: P2ImChatAccessEventBotP2pChatEnteredV1,
) -> None:
    """
    处理用户进入机器人单聊事件
    :param data: 事件数据
    """
    logger.info(f"[用户进入机器人单聊事件] data: {data}")
    open_id = data.event.operator_id.open_id
    send_Allince_card(open_id)


# ==========================================
# WebSocket 客户端 (用于被动接收事件)
# ==========================================


# 注册事件回调
# Register event handler.
# 注册事件回调
# Register event handler.
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(
        do_p2_im_chat_access_event_bot_p2p_chat_entered_v1
    )
    .register_p2_application_bot_menu_v6(do_p2_application_bot_menu_v6)
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .register_p2_card_action_trigger(do_p2_card_action_trigger)
    .build()
)

def start_feishu_ws_client():
    """启动 WebSocket (阻塞式)"""
    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        logger.warning("未配置飞书凭证，跳过 WebSocket 启动")
        return

    logger.info("正在连接飞书 WebSocket...")
    try:
        # 注意：这里是 ws.Client，与上面的 api_client 不同
        ws_client = lark.ws.Client(
            settings.FEISHU_APP_ID,
            settings.FEISHU_APP_SECRET,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )
        ws_client.start()
    except Exception as e:
        logger.error(f"飞书 WebSocket 连接失败: {e}")