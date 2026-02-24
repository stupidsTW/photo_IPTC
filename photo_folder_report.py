import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import re

# ================= 設定區 =================
DB_PATH = "photo_folder_index.db"
# 請設定資料庫內的 Linux 開頭與對應的 Windows 開頭
LINUX_BASE_PREFIX = "/media/stupids/WD_6T/photo"
WINDOWS_BASE_PREFIX = r"G:\photo" 
# ==========================================

class PhotoSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IPTC 檢索系統 - 多平台路徑切換版")
        self.root.geometry("1100x850")

        # 1. 搜尋與控制區域
        ctrl_frame = tk.Frame(root, pady=10, bg="#f0f0f0")
        ctrl_frame.pack(fill=tk.X)
        
        # 搜尋輸入
        search_sub = tk.Frame(ctrl_frame, bg="#f0f0f0")
        search_sub.pack(fill=tk.X, padx=20)
        tk.Label(search_sub, text="Regex 搜尋: ", font=("Microsoft JhengHei", 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT)
        self.search_entry = tk.Entry(search_sub, font=("Consolas", 12))
        self.search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.search_entry.bind("<Return>", lambda e: self.perform_search())
        
        # 路徑模式切換
        mode_sub = tk.Frame(ctrl_frame, bg="#f0f0f0")
        mode_sub.pack(fill=tk.X, padx=20, pady=(5, 0))
        tk.Label(mode_sub, text="路徑顯示模式: ", font=("Microsoft JhengHei", 9), bg="#f0f0f0").pack(side=tk.LEFT)
        
        self.path_mode = tk.StringVar(value="linux") # 預設 Linux
        tk.Radiobutton(mode_sub, text="Linux 原生 (/media/...)", variable=self.path_mode, 
                       value="linux", bg="#f0f0f0", command=self.perform_search).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(mode_sub, text="Windows 映射 (G:\...)", variable=self.path_mode, 
                       value="windows", bg="#f0f0f0", command=self.perform_search).pack(side=tk.LEFT)

        tk.Button(search_sub, text="搜尋", command=self.perform_search, width=10, bg="#0078d7", fg="white").pack(side=tk.LEFT, padx=5)

        # 2. 結果區域
        self.result_frame = tk.Frame(root)
        self.result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.text_area = tk.Text(self.result_frame, font=("Consolas", 10), wrap=tk.NONE, bg="#ffffff", padx=10, pady=10)
        
        v_scroll = tk.Scrollbar(self.result_frame, orient=tk.VERTICAL, command=self.text_area.yview)
        h_scroll = tk.Scrollbar(self.result_frame, orient=tk.HORIZONTAL, command=self.text_area.xview)
        self.text_area.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 樣式與雙擊事件
        self.text_area.tag_configure("path_header", foreground="#0000FF", font=("Consolas", 11, "bold"))
        self.text_area.tag_configure("highlight", background="#fff3cd", foreground="#d9534f")
        self.text_area.tag_configure("divider", foreground="#cccccc")
        self.text_area.bind("<Double-1>", self.on_double_click)

    def get_display_path(self, raw_path):
        """根據選擇模式轉換路徑"""
        if self.path_mode.get() == "windows":
            # 替換前綴並轉反斜線
            return raw_path.replace(LINUX_BASE_PREFIX, WINDOWS_BASE_PREFIX).replace("/", "\\")
        return raw_path # Linux 模式直接回傳

    def perform_search(self):
        query = self.search_entry.get().strip()
        if not query: return
        
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)

        try:
            reg_pattern = re.compile(query, re.IGNORECASE)
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT path, content_blob FROM folder_index")
            
            for path, blob in cursor.fetchall():
                content = blob if blob else ""
                if reg_pattern.search(path) or reg_pattern.search(content):
                    # 關鍵：這裡調用轉換函數
                    display_path = self.get_display_path(path)
                    self.text_area.insert(tk.END, f"{display_path}\n", "path_header")
                    
                    if blob:
                        indented = "".join([f"  {line}\n" for line in blob.strip().split('\n')])
                        self.text_area.insert(tk.END, indented)
                    else:
                        self.text_area.insert(tk.END, "  (此目錄無帶有有效 IPTC 標籤之檔案)\n")
                    self.text_area.insert(tk.END, "─" * 100 + "\n", "divider")
            
            conn.close()
            self.apply_highlight(query)
            self.text_area.config(state=tk.DISABLED)

        except Exception as e:
            messagebox.showerror("錯誤", str(e))

    def apply_highlight(self, pattern):
        """Regex 高亮"""
        start = "1.0"
        while True:
            start = self.text_area.search(pattern, start, nocase=True, stopindex=tk.END, regexp=True)
            if not start: break
            # 取得匹配項長度
            line_text = self.text_area.get(start, f"{start} lineend")
            m = re.search(pattern, line_text, re.IGNORECASE)
            if m:
                match_len = len(m.group())
                end = f"{start}+{match_len}c"
                self.text_area.tag_add("highlight", start, end)
                start = end
            else:
                start = f"{start}+1c"

    def on_double_click(self, event):
        """雙擊處理：只有在 Windows 模式下才嘗試開啟資料夾"""
        line_idx = self.text_area.index(f"@{event.x},{event.y}").split('.')[0]
        path = self.text_area.get(f"{line_idx}.0", f"{line_idx}.end").strip()
        
        if self.path_mode.get() == "windows":
            if os.path.isdir(path):
                os.startfile(path)
            else:
                messagebox.showwarning("提示", f"找不到資料夾，請確認硬碟已連接：\n{path}")
        else:
            # Linux 模式下雙擊，可以改為複製到剪貼簿
            self.root.clipboard_clear()
            self.root.clipboard_append(path)
            self.root.title("路徑已複製到剪貼簿")

if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoSearchApp(root)
    root.mainloop()