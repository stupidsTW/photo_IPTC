import sqlite3
import os

# ================= 設定區 =================
DB_PATH = "photo_folder_index.db"
OUTPUT_TXT = "iptc_dump_report.txt"

# 路徑轉換設定 (僅在選擇 Windows 模式時生效)
LINUX_BASE = "/media/stupids/WD_6T/photo"
WINDOWS_BASE = r"G:\photo"
# ==========================================

def convert_to_windows(linux_path):
    """將 Linux 路徑轉換為 Windows 格式"""
    if linux_path.startswith(LINUX_BASE):
        win_path = linux_path.replace(LINUX_BASE, WINDOWS_BASE)
        return win_path.replace("/", "\\")
    return linux_path

def dump_data():
    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到資料庫檔案: {DB_PATH}")
        return

    # 讓使用者選擇格式
    print("請選擇輸出的路徑格式：")
    print("1) 原始路徑 (Linux 格式: /media/...)")
    print("2) Windows 路徑 (映射格式: G:\...)")
    choice = input("請輸入數字 (1 或 2): ").strip()

    mode = "linux" if choice == "1" else "windows"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 取得總筆數以顯示進度
        cursor.execute("SELECT COUNT(*) FROM folder_index")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT path, content_blob FROM folder_index ORDER BY path ASC")
        
        print(f"🚀 開始導出 {total} 筆目錄資料 (模式: {mode})...")

        with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
            for path, blob in cursor:
                # 根據選擇進行路徑轉換
                display_path = convert_to_windows(path) if mode == "windows" else path
                
                # 1. 寫入路徑標題
                f.write(f"{display_path}\n")
                
                # 2. 寫入內容
                if blob:
                    # 還原縮排格式
                    indented_blob = "".join([f"  {line}\n" for line in blob.strip().split('\n')])
                    f.write(indented_blob)
                #else:
                    #f.write("  (此目錄無符合之 IPTC 標籤檔案)\n")
                
                # 3. 寫入分隔線
                #f.write("-" * 80 + "\n")

        print(f"✅ 導出成功！檔案已儲存至: {OUTPUT_TXT}")

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    dump_data()