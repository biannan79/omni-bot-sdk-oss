"""
消息工厂服务模块。
提供消息工厂相关的服务接口。
"""

import logging

from omni_bot_sdk.models import UserInfo
from omni_bot_sdk.services.core.database_service import DatabaseService
from omni_bot_sdk.weixin.message_classes import Message, MessageType
from omni_bot_sdk.weixin.message_factory import FACTORY_REGISTRY


class MessageFactoryService:
    def __init__(self, user_info: UserInfo, db: DatabaseService):
        self.logger = logging.getLogger(__name__)
        self.user_info = user_info
        self.db = db

    def create_message(self, message: tuple) -> Message:
        """将消息转换为Message对象"""
        # TODO 加缓存，考虑到复杂程度，先不加了，腾讯在sqlite中索引加的不少，测试直接查询速度不慢
        table_name, msg_with_db = message
        type_ = msg_with_db[2]
        self.logger.info(f"消息类型: {MessageType.name(type_)}")
        room = self.db.get_room_by_md5(table_name.replace("Msg_", ""))
        if type_ not in FACTORY_REGISTRY:
            self.logger.warning(f"未知消息类型: {type_}，使用 UnknownMessageFactory")
            type_ = -1

        # 获取联系人信息
        sender_id = msg_with_db[4]
        message_db_path = msg_with_db[17] if len(msg_with_db) > 17 else ""

        # 传递所有参数，包括 table_name 用于 fallback
        contact = self.db.get_contact_by_sender_id(sender_id, message_db_path, table_name)

        if not contact:
            self.logger.debug(f"未找到联系人: sender_id={sender_id}, table={table_name}, 使用 table fallback")
            # 尝试直接通过表名查找
            contact = self.db.get_contact_by_table_md5(table_name.replace("Msg_", ""))
            # TODO 有些消息是允许没有发送人的？这个时候怎么搞？是不是把他当作系统呢？
        msg = FACTORY_REGISTRY[type_].create(
            msg_with_db, self.user_info, self.db, contact, room
        )
        msg.room = room
        if contact:
            msg.contact = contact
        return msg
