"""
核心觀念：API 上下文不是無底洞，而是一個精密的「滑動視窗」與「垃圾回收」機制。

這個模組展示了 SOTA Agent 如何聰明地管理「系統預設 Prompt + 外部知識庫 (.md) + 歷史對話」。
不該因為一開始塞了幾千字的設定檔，就讓後續的對話空間爆掉。

核心法則：
1. 靜態上下文 (Kernel Prompt): 永遠保留在陣列的最開頭 (Index 0)。這是系統的靈魂。
2. 參考知識庫 (External .md): 不要一次全塞。應該在每一輪對話中，只擷取與當前問題最相關的「片段」動態注入。
3. 動態上下文 (History Window): 使用「滑動視窗」，只保留最近 N 輪對話。
4. 滾動摘要 (Rolling Summary): 捨棄的對話不直接刪掉，而是先壓縮成一句話，作為下一輪的「前情提要」。
"""

class ContextManager:
    def __init__(self, max_history_tokens=4000, max_messages=10):
        # 系統核心 Prompt (永遠置頂，不可壓縮)
        self.system_prompt = {
            "role": "system",
            "content": "你是系統級 Agent。你必須嚴格遵循指示，並且一次只能回應一個特定的任務。"
        }
        
        # 動態歷史對話視窗 (List of dict)
        self.history = []
        
        # 前情提要的壓縮精華 (從被捨棄的對話中提煉)
        self.rolling_summary = ""
        
        # 限制參數
        self.MAX_MESSAGES = max_messages
        # 簡單模擬 Token 計算（實際應用中請使用 tiktoken）
        self.MAX_HISTORY_TOKENS = max_history_tokens 

    def _estimate_tokens(self, text):
        """假 token 計算：這只是個簡單模擬，1 char 約等於 0.5 token"""
        return len(text) // 2

    def add_message(self, role, content):
        """將新訊息加入視窗，並執行「垃圾回收機制」"""
        new_msg = {"role": role, "content": content}
        self.history.append(new_msg)
        
        self._prune_history()

    def _prune_history(self):
        """
        核心邏輯：滑動視窗。
        當歷史紀錄過長時，會從「最舊的 User/Assistant」對話開始刪除，
        以確保永遠有空間留給最新的思考與動作。
        """
        # 條件 1: 數量限制
        while len(self.history) > self.MAX_MESSAGES:
            popped_msg = self.history.pop(0)
            # 這裡可以呼叫小模型去壓縮 popped_msg 並加到 self.rolling_summary
            self._update_rolling_summary(popped_msg)
            
        # 條件 2: Token 限制 (簡單防爆保護)
        while sum(self._estimate_tokens(msg['content']) for msg in self.history) > self.MAX_HISTORY_TOKENS:
            if not self.history:
                break
            popped_msg = self.history.pop(0)
            self._update_rolling_summary(popped_msg)

    def _update_rolling_summary(self, popped_msg):
        """
        實作概念：這段應該呼叫便宜的模型（如 GPT-4o-mini 或 Gemini Flash）來總結。
        這裡用簡單字串堆疊示範。
        """
        # 實際應用中，這段會是： summary = call_cheap_model(popped_msg)
        topic_preview = popped_msg['content'][:20] + "..."
        if not self.rolling_summary:
            self.rolling_summary = f"[歷史總結]: 曾經討論過 -> {topic_preview}"
        else:
            self.rolling_summary += f" | {topic_preview}"


    def build_payload_for_api(self, external_md_content=""):
        """
        每一次呼叫 API 前，動態組裝最終的 Context Array。
        這就是我們傳送給 API 的最終 Payload。
        """
        payload = [self.system_prompt]
        
        # 如果有外部知識庫，不要作為系統提示，而是當作一個 "前置知識" 動態塞入
        if external_md_content:
            knowledge_msg = {
                "role": "system",  # 或是 'user'，視模型支援而定
                "content": f"【動態檢索的參考資料】:\n{external_md_content}\n---以上為參考資料---"
            }
            payload.append(knowledge_msg)
            
        # 塞入由舊對話壓縮而來的「滾動摘要」
        if self.rolling_summary:
            summary_msg = {
                "role": "system",
                "content": self.rolling_summary
            }
            payload.append(summary_msg)
            
        # 最後才是我們維護好的「乾淨、瘦身的歷史對話」
        payload.extend(self.history)
        
        return payload

# ----------------- 實驗執行區 -----------------
if __name__ == "__main__":
    print("=== 上下文管理器 (Context Manager) 實驗開始 ===")
    
    # 初始化一個最多只保留 4 句話的嚴格管理器
    manager = ContextManager(max_messages=4)
    
    print("\n[階段 1] 模擬冗長的早期對話 (即將被擠出視窗)")
    manager.add_message("user", "我要建立一個專案，我想先討論架構，不要寫程式。")
    manager.add_message("assistant", "好的，架構可以選擇 MVC 或微服務。")
    manager.add_message("user", "那我們決定用語義層。不要用 MVC。")
    manager.add_message("assistant", "收到，語義層架構確立。")
    
    print("\n[階段 2] 模擬目前的最新對話")
    manager.add_message("user", "現在我們從哪裡開始寫？")
    manager.add_message("assistant", "我們可以先寫主入口 main.py。")
    
    print("\n=== 發送給強大 API 的最終淨化 Payload ===")
    
    # 假設我們讀取了一個外部的 Readme.md (模擬動態讀入)
    dummy_md = "# 團隊規範\n所有縮排必須是 4 格空格。"
    
    final_payload = manager.build_payload_for_api(external_md_content=dummy_md)
    
    for i, msg in enumerate(final_payload):
        print(f"[{i}] {msg['role'].upper()}: {msg['content']}")
        print("-" * 40)
        
    print("\n[實驗結論]")
    print("你看！最舊的對話（決定不要用 MVC 那段）已經被擠出 'User/Assistant' 陣列了。")
    print("但它被壓縮進了 `[歷史總結]` 裡面（在實務上會由小模型生出高品質摘要）！")
    print("這就是大廠避免 API 爆掉、失憶，又能塞入大量 .md 的終極解決方案。")
