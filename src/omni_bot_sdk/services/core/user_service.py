"""
用户服务模块。
提供用户相关的服务接口。
"""

import json
import os
from pathlib import Path
from typing import Optional

from omni_bot_sdk.models import UserInfo
from omni_bot_sdk.utils.fuck_zxl import WeChatDumper


def _detect_wechat_data_dir() -> Optional[str]:
    """
    自动检测微信 4.0 数据目录 - 选择最近活跃的账号

    微信 4.0 的数据目录结构:
    - Windows: C:/Users/{username}/xwechat_files/{wxid}_{hash}/

    Returns:
        数据目录路径 (不含 db_storage)，如果未找到返回 None
    """
    # 优先使用主项目 WeChatDecryptor 检测到的目录
    try:
        import sys
        project_root = Path(__file__).parent.parent.parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from src.services.wechat_decryptor import get_decryptor
        decryptor = get_decryptor()
        if decryptor and decryptor.db_dir and decryptor.db_dir.exists():
            # decryptor.db_dir 是 db_storage 目录，需要取父目录
            account_dir = decryptor.db_dir.parent
            if account_dir.exists():
                return str(account_dir)
    except Exception:
        pass

    try:
        user_home = Path.home()
        xwechat_dir = user_home / "xwechat_files"

        if not xwechat_dir.exists():
            return None

        # 查找所有账号目录并按 contact.db 修改时间排序
        account_dirs = []
        for item in xwechat_dir.iterdir():
            if item.is_dir() and item.name.startswith("wxid_"):
                db_storage = item / "db_storage" / "contact" / "contact.db"
                if db_storage.exists():
                    account_dirs.append((item, db_storage.stat().st_mtime))

        if not account_dirs:
            return None

        # 按最后修改时间排序，选择最近活跃的账号
        account_dirs.sort(key=lambda x: x[1], reverse=True)
        return str(account_dirs[0][0])

    except Exception:
        return None


class UserService:
    """
    用户服务类。
    管理用户信息和授权信息。
    """

    def __init__(self, dbkey: str = None):
        """
        初始化用户服务。

        Args:
            dbkey: 数据库键。如果为空，后续数据库解密会失败。
        """
        self.dbkey = dbkey or ""
        self.user_info: UserInfo = None
        self.wxdump = WeChatDumper()
        wechat_info = self.wxdump.find_and_dump()
        if wechat_info:
            # 如果 WeChatDumper 返回的 data_dir 是 "Unknown"，尝试自动检测
            data_dir = wechat_info.data_dir
            if data_dir == "Unknown" or not data_dir:
                detected_dir = _detect_wechat_data_dir()
                if detected_dir:
                    data_dir = detected_dir

            self.user_info = UserInfo(
                pid=wechat_info.pid,
                version=wechat_info.version,
                account=wechat_info.account,
                alias=wechat_info.alias,
                nickname=wechat_info.nickname,
                phone=wechat_info.phone,
                data_dir=data_dir,
                dbkey=self.dbkey,
                raw_keys={},
                dat_key="",
                dat_xor_key=-1,
                avatar_url=wechat_info.avatar_url,
            )
        else:
            raise Exception("未找到微信主窗口，请确保微信已登录")

    def get_user_info(self):
        """
        获取当前用户信息。

        Returns:
            用户信息。
        """
        return self.user_info

    def set_user_info(self, user_info: UserInfo):
        """
        更新用户信息。

        Args:
            user_info: 新的用户信息。
        """
        self.user_info = user_info

    def update_raw_key(self, key: str, value: str):
        """
        更新原始密钥。

        Args:
            key: 密钥名称。
            value: 密钥值。
        """
        self.user_info.raw_keys[key] = value

    def get_raw_key(self, key: str) -> Optional[str]:
        """
        获取原始密钥。

        Args:
            key: 密钥名称。

        Returns:
            密钥值，如果不存在则返回None。
        """
        return self.user_info.raw_keys.get(key, None)

    def dump_to_file(self):
        """
        将当前用户信息写入到Windows用户目录下，文件名为account.json，使用pathlib实现。
        """
        if not self.user_info:
            raise Exception("用户信息未初始化")
        # 获取用户目录
        user_home = Path.home()
        # 构造文件路径
        file_path = user_home / f"{self.user_info.account}.json"
        # 转为dict并写入json
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.user_info.to_dict(), f, ensure_ascii=False, indent=4)
