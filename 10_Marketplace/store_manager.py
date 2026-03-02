import logging
import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class MarketItem:
    item_id: str
    name: str
    description: str
    author: str
    item_type: str  # "soul" or "tool"
    price_m_token: float
    payload: dict   # The actual SOUL.md content or script logic
    downloads: int = 0

class MTokenWallet:
    """ 虛擬加密代幣 M Token 錢包 (Mock) """
    def __init__(self, initial_balance: float = 100.0):
        self.balance = initial_balance
        logger.info(f"👛 Wallet initialized with {self.balance} M Tokens")
        
    def spend(self, amount: float) -> bool:
        if self.balance >= amount:
            self.balance -= amount
            logger.info(f"💸 Spent {amount} M Tokens. Remaining: {self.balance}")
            return True
        logger.warning(f"❌ 餘額不足。Need {amount}, have {self.balance}")
        return False
        
    def earn(self, amount: float):
        self.balance += amount
        logger.info(f"💰 Earned {amount} M Tokens. Balance: {self.balance}")

class AgentMarketplace:
    """ AgentOS 生態系市集：交易 Souls 和 Tools """
    def __init__(self, wallet: MTokenWallet):
        self.wallet = wallet
        self.inventory: Dict[str, MarketItem] = {}
        # 內建一些 Mock 庫存
        self.publish_item(
            name="Crypto Trader Soul",
            desc="A ruthless daily trader identity.",
            item_type="soul",
            price=2.5,
            payload={"soul_content": "# Crypto Trader\\nYou are a trader..."}
        )
        self.publish_item(
            name="Scrape Hacker Tool",
            desc="Advanced web scraping tool avoiding captchas.",
            item_type="tool",
            price=5.0,
            payload={"tool_code": "def scrape(): pass"}
        )
        
    def publish_item(self, name: str, desc: str, item_type: str, price: float, payload: dict) -> str:
        item_id = str(uuid.uuid4())[:8]
        new_item = MarketItem(
            item_id=item_id, name=name, description=desc, 
            author="AgentOS User", item_type=item_type,
            price_m_token=price, payload=payload
        )
        self.inventory[item_id] = new_item
        logger.info(f"🛒 Published [{item_type.upper()}] {name} for {price} M Tokens (ID: {item_id})")
        return item_id
        
    def browse(self, item_type: Optional[str] = None) -> List[dict]:
        results = []
        for item in self.inventory.values():
            if not item_type or item.item_type == item_type:
                results.append(asdict(item))
        return results
        
    def install_item(self, item_id: str) -> Optional[dict]:
        item = self.inventory.get(item_id)
        if not item:
            logger.error(f"❌ Item {item_id} not found.")
            return None
            
        logger.info(f"🛒 Preparing to install {item.name}. Cost: {item.price_m_token} M Tokens.")
        success = self.wallet.spend(item.price_m_token)
        
        if success:
            item.downloads += 1
            # 實戰中這裡會把 payload 寫入 local 的 SOUL.md 或 Tools 資料夾
            # 並轉帳給 Author
            logger.info(f"✅ Successfully installed {item.name}! (Total downloads: {item.downloads})")
            return item.payload
            
        return None
