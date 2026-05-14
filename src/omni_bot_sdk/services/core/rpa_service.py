"""
RPA 服务模块。
提供 RPA 相关的服务接口。
"""

import logging
import threading
import time
from queue import Empty, Queue
from typing import Any, Optional

from omni_bot_sdk.rpa.action_handlers import RPAAction

# 导入依赖的类型，用于类型提示
from omni_bot_sdk.rpa.controller import RPAController


class RPAService:
    """
    RPA服务【任务消费者】。
    它作为一个后台服务，在独立的线程中运行。
    其唯一职责是从RPA任务队列中按顺序取出任务，并将其交给RPAController执行。
    """

    def __init__(self, rpa_task_queue: Queue, rpa_controller: RPAController):
        """
        【轻量级初始化】只接收并保存已创建好的依赖项。

        Args:
            rpa_task_queue (Queue[RPAAction]): 用于接收RPA任务的队列。
            rpa_controller (RPAController): 负责实际执行RPA操作的控制器实例。
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        # --- 1. 保存注入的依赖 ---
        self.task_queue: Queue = rpa_task_queue
        self.controller: RPAController = rpa_controller

        # --- 2. 初始化自身状态 ---
        self.is_running: bool = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """
        启动RPA服务的后台线程。
        由Bot的生命周期管理器调用。
        """
        if self.is_running:
            self.logger.warning("RPAService is already running.")
            return

        self.logger.info("Starting RPAService...")
        self.is_running = True
        self.thread = threading.Thread(
            target=self._execute_loop, name="RPAWorkerThread"
        )
        self.thread.daemon = True
        self.thread.start()
        self.logger.info("RPAService has started.")

    def stop(self):
        """
        停止RPA服务的后台线程。
        由Bot的生命周期管理器调用。
        """
        if not self.is_running:
            self.logger.warning("RPAService is not running.")
            return

        self.logger.info("Stopping RPAService...")
        self.is_running = False
        if self.thread and self.thread.is_alive():
            # 等待线程自然结束，可以设置一个超时
            self.thread.join(timeout=5.0)
            if self.thread.is_alive():
                self.logger.warning("RPAWorkerThread did not terminate gracefully.")
        self.thread = None
        self.logger.info("RPAService has stopped.")

    def _execute_loop(self):
        """
        执行循环。这是运行在后台线程中的核心逻辑。
        """
        self.logger.info("RPA worker loop started.")
        while self.is_running:
            try:
                # 从队列中阻塞式地获取任务，设置超时以响应停止信号
                task = self.task_queue.get(block=True, timeout=1.0)

                if task:
                    self.logger.debug(f"Processing RPA action: {task.action_type.name}")
                    # 将任务交给RPAController执行
                    success = self.controller.execute_action(task)
                    self.task_queue.task_done()

                    # 发送完成后通知 webhook
                    self._notify_message_sent(task, success)

            except Empty:
                # 队列为空是正常情况，继续循环以检查 is_running 状态
                continue
            except Exception as e:
                self.logger.error(
                    f"An unhandled exception occurred in RPA worker loop: {e}",
                    exc_info=True,
                )
                # 发生错误时等待一小段时间，避免CPU空转
                time.sleep(1)
        self.logger.info("RPA worker loop finished.")

    def _notify_message_sent(self, task, success: bool):
        """
        通知 FastAPI 消息发送结果

        Args:
            task: RPA 任务对象
            success: 是否发送成功
        """
        try:
            # 只处理发送消息类型的任务
            if not hasattr(task, 'is_send_message') or not task.is_send_message:
                return

            from omni_bot_sdk.webhook import get_webhook_client
            import time as time_module

            client = get_webhook_client()
            if not client or not client.is_connected:
                return  # 未连接，跳过

            # 获取 correlation_id
            correlation_id = getattr(task, 'correlation_id', None)
            if not correlation_id:
                # 如果没有 correlation_id，生成一个
                correlation_id = f"{int(time_module.time())}_{task.target}"

            # 异步推送
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        client.push_message_sent(
                            correlation_id=correlation_id,
                            target=task.target,
                            content=getattr(task, 'content', ''),
                            success=success
                        )
                    )
            except RuntimeError:
                pass  # 没有运行中的事件循环

        except ImportError:
            pass  # webhook 模块不可用
        except Exception as e:
            self.logger.debug(f"通知 webhook 失败: {e}")

    # 移除了 submit_task 方法，因为任务提交的职责现在完全由Bot类承担，
    # Bot会直接访问它持有的 rpa_task_queue 来提交任务。
    # 这确保了任务提交的入口是唯一的。

    # get_status 方法可以保留，用于监控
    def get_status(self) -> dict:
        """
        获取RPA服务的当前状态。
        """
        status = {
            "is_running": self.is_running,
            "queue_size": self.task_queue.qsize(),
        }
        # 如果RPAController有get_status方法，也可以在这里调用
        if hasattr(self.controller, "get_status"):
            status.update(self.controller.get_status())
        return status
