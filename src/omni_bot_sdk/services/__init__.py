"""
服务层包初始化文件。
包含数据库、消息、RPA、微信等核心服务模块。
"""

# 延迟导入，避免 sqlcipher DLL 问题
NewFriendCheckService = None

def get_new_friend_check_service():
    """延迟导入 NewFriendCheckService"""
    global NewFriendCheckService
    if NewFriendCheckService is None:
        try:
            from omni_bot_sdk.services.functional.new_friend_check_service import (
                NewFriendCheckService as _NewFriendCheckService,
            )
            NewFriendCheckService = _NewFriendCheckService
        except Exception as e:
            import logging
            logging.warning(f"NewFriendCheckService 导入失败: {e}")
    return NewFriendCheckService

__all__ = ["NewFriendCheckService", "get_new_friend_check_service"]
