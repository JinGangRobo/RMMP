import logging

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, \
    CreateMessageRequestBody, P2ImMessageReceiveV1

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


def send_text_message(receive_id: str, content: str,
                      receive_id_type: str = "open_id"):
    """
    示例：主动发送文本消息
    :param receive_id: 接收者ID (open_id, user_id, union_id, email, chat_id)
    :param content: 消息内容
    :param receive_id_type: ID类型，默认 open_id
    """
    # 1. 构建请求体 (Builder 模式)
    request_body = CreateMessageRequestBody.builder() \
        .receive_id(receive_id) \
        .msg_type("text") \
        .content(lark.JSON.marshal({"text": content})) \
        .build()

    # 2. 构建请求对象
    request = CreateMessageRequest.builder() \
        .receive_id_type(receive_id_type) \
        .request_body(request_body) \
        .build()

    # 3. 发送请求 (使用全局 api_client)
    response = api_client.im.v1.message.create(request)

    # 4. 处理响应
    if not response.success():
        logger.error(
            f"发送消息失败: code={response.code}, msg={response.msg}, log_id={response.get_log_id()}")
        return None

    logger.info(f"消息发送成功: message_id={response.data.message_id}")
    return response.data


# ==========================================
# WebSocket 客户端 (用于被动接收事件)
# ==========================================

def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    """处理接收到的消息事件"""
    # 解析消息内容
    content_json = data.event.message.content
    chat_id = data.event.message.chat_id

    logger.info(f"收到消息: {content_json}")

    # 【示例】收到消息后，自动回复一条消息
    # 注意：这里直接调用了上面定义的发送函数
    send_text_message(chat_id, "我收到了你的消息！",
                      receive_id_type="chat_id")


event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
    .build()


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
