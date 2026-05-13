"""
消息服务模块。
提供消息的存储、检索、分发等服务。
"""

import logging
import threading
import time
from queue import Empty, Queue
from typing import Callable, Optional
from pathlib import Path
from omni_bot_sdk.services.core.database_service import DatabaseService


class MessageService:
    def __init__(self, message_queue: Queue, db: DatabaseService):
        self.logger = logging.getLogger(__name__)
        self.message_queue = message_queue
        self.db = db
        self.is_running = False
        self.is_paused = False  # 新增：用于标记是否暂停
        self.thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable] = None

    def start(self):
        """启动监听器"""
        if self.is_running:
            self.logger.warning("监听器已经在运行中")
            return False

        self.is_running = True
        self.thread = threading.Thread(target=self._message_loop)
        self.thread.daemon = True
        self.thread.start()
        self.logger.info("监听器已启动")
        return True

    def stop(self):
        """停止监听器"""
        if not self.is_running:
            self.logger.warning("监听器未在运行")
            return False

        self.is_running = False
        if self.thread:
            self.thread.join()
        self.logger.info("监听器已停止")
        return True

    def set_callback(self, callback: Callable):
        """设置消息回调函数"""
        self.callback = callback

    def pause(self):
        """
        暂停消息获取
        """
        if not self.is_running or self.is_paused:
            self.logger.info("消息监听器已暂停或未运行，无需重复暂停。")
            return
        self.is_paused = True
        self.logger.info("消息监听器已暂停。")

    def resume(self):
        """
        恢复消息获取
        """
        if not self.is_running or not self.is_paused:
            self.logger.info("消息监听器未暂停或未运行，无需恢复。")
            return
        self.is_paused = False
        self.logger.info("消息监听器已恢复。")

    def _message_loop(self):
        """监听循环"""
        self.logger.info("[MessageService] 消息监听循环开始")
        loop_count = 0
        while self.is_running:
            if self.is_paused:
                time.sleep(1)
                continue
            try:
                # 只查询最近30分钟的消息，避免加载大量历史消息
                message = self.db.check_new_messages(time_window_minutes=30)
                loop_count += 1
                if loop_count % 20 == 0:  # 每15秒打印一次心跳
                    self.logger.debug(f"[MessageService] 心跳检测中... (队列: {self.message_queue.qsize()})")
                if message:
                    for msg in message:
                        # msg = (table_name, (local_id, server_id, local_type, ...))
                        table_name = msg[0]
                        row_data = msg[1]
                        # 从表名提取联系人名称 (Msg_{md5} -> 联系人wxid)
                        contact_name = table_name.replace("Msg_", "")
                        # 安全获取消息内容预览
                        content_preview = ""
                        if row_data and len(row_data) > 12:
                            content = row_data[12]  # message_content
                            if content:
                                content_preview = str(content)[:50]
                        self.logger.info(
                            f"[MessageService] 新消息插入队列，来自于 {contact_name} : {content_preview}"
                        )
                        self.message_queue.put(msg)
                    self.logger.info(f"[MessageService] 消息队列大小: {self.message_queue.qsize()}")
                    # 保存消息到数据库
                    if self.callback:
                        self.callback(message)
                time.sleep(0.75)
            except Empty:
                # 队列为空，继续下一次循环
                time.sleep(1)  #
                continue
            except Exception as e:
                if self.is_running:  # 忽略超时异常
                    self.logger.error(f"[MessageService] 处理消息时出错: {e}")
                    time.sleep(1)  #

    def get_status(self) -> dict:
        """获取监听器状态"""
        return {"is_running": self.is_running, "queue_size": self.message_queue.qsize()}
