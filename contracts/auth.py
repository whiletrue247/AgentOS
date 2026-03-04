from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseAuth(ABC):
    """
    未來 SSO (OIDC) 與 RBAC 權限體系的基礎抽象類別。
    """

    @abstractmethod
    async def authenticate(self, token: str) -> Optional[Dict[str, Any]]:
        """
        驗證 Token 並返回使用者 Profile。
        """
        pass

    @abstractmethod
    def has_permission(self, user_role: str, resource: str, action: str) -> bool:
        """
        檢查該角色是否對資源有操作權限。
        """
        pass

class MockAuth(BaseAuth):
    """
    開源版預設的無身分驗證實作，皆返回具有最高權限的 Default User。
    """
    async def authenticate(self, token: str) -> Optional[Dict[str, Any]]:
        return {"uid": "default", "role": "admin"}

    def has_permission(self, user_role: str, resource: str, action: str) -> bool:
        return True

