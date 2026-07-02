import csv
import json
import os
import subprocess
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CACHE_FILENAME = ".caption_gui_cache.json"


def build_time_cache(folder_path):
    """
    對資料夾中所有 JPEG 檔案一次呼叫 exiftool 取得 DateTimeOriginal，
    並建立 {DateTimeOriginal: filename} 的對應表，同時寫入暫存檔。
    """
    cache_path = os.path.join(folder_path, CACHE_FILENAME)
    time_map = {}

    # 取得資料夾內所有 jpeg 檔案
    jpg_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.jpg', '.jpeg'))
    ]
    if not jpg_files:
        return time_map

    # 使用 -csv 輸出，結構穩定可避免 -s3 多檔多 tag 時的解析問題
    cmd = ["exiftool", "-csv", "-DateTimeOriginal"]
    cmd.extend(os.path.join(folder_path, f) for f in jpg_files)
    result = subprocess.run(cmd, capture_output=True, text=True)

    # 解析 CSV 輸出：欄位為 SourceFile, DateTimeOriginal
    reader = csv.DictReader(result.stdout.splitlines())
    for row in reader:
        src = row.get("SourceFile", "")
        dt = row.get("DateTimeOriginal", "")
        if not src or not dt:
            continue
        fname = os.path.basename(src)
        # 若 DateTimeOriginal 已存在（多張同時間），保留第一個
        if dt not in time_map:
            time_map[dt] = fname

    # 寫入暫存檔
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(time_map, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

    return time_map


def load_time_cache(folder_path):
    """嘗試讀取現有的暫存檔，失敗則回傳 None。"""
    cache_path = os.path.join(folder_path, CACHE_FILENAME)
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_all_csv(csv_folder):
    """讀取資料夾中所有 CSV 檔案並合併成一筆資料清單。

    每筆資料會額外加上 'SourceFile' 欄位記錄來源檔名，方便除錯與追溯。
    只讀取含有 DateTimeOriginal 與 Caption-Abstract 欄位的 CSV，
    避免誤讀其他用途的 CSV 檔案。
    """
    REQUIRED_FIELDS = {"DateTimeOriginal", "Caption-Abstract"}

    csv_files = sorted(
        f for f in os.listdir(csv_folder)
        if f.lower().endswith('.csv')
    )
    if not csv_files:
        print(f"在 {csv_folder} 中找不到任何 CSV 檔案")
        sys.exit(1)

    all_data = []
    skipped = []
    for fname in csv_files:
        f_path = os.path.join(csv_folder, fname)
        with open(f_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # 檢查是否含必要欄位
            if not REQUIRED_FIELDS.issubset(reader.fieldnames or []):
                skipped.append(fname)
                print(f"  跳過 {fname} (缺少必要欄位)")
                continue
            rows = list(reader)
        for row in rows:
            row['SourceFile'] = fname
        print(f"  讀取 {fname}: {len(rows)} 筆")
        all_data.extend(rows)

    if skipped:
        print(f"已跳過 {len(skipped)} 個非標註用 CSV: {', '.join(skipped)}")
    if not all_data:
        print("沒有讀取到任何有效的標註資料")
        sys.exit(1)

    print(f"共讀取 {len(csv_files) - len(skipped)} 個 CSV 檔案，合計 {len(all_data)} 筆資料")
    return all_data


class TaggerApp(QWidget):
    def __init__(self, csv_data, folder_path, time_map):
        super().__init__()
        self.csv_data = csv_data
        self.folder_path = folder_path
        # {DateTimeOriginal: filename}
        self.time_map = time_map
        self.initUI()

    def initUI(self):
        self.setWindowTitle('專業照片標註確認工具')
        self.resize(900, 600)

        main_layout = QHBoxLayout()

        # 左側：CSV 標籤清單（含勾選框）
        self.listWidget = QListWidget()
        for entry in self.csv_data:
            display_text = f"{entry['DateTimeOriginal']} | {entry['Caption-Abstract']}"
            item = QListWidgetItem(display_text)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.listWidget.addItem(item)

        # 勾選操作按鈕列
        check_layout = QHBoxLayout()
        btnSelectAll = QPushButton("全選")
        btnSelectNone = QPushButton("取消全選")
        btnSelectAll.clicked.connect(lambda: self._set_all_checked(True))
        btnSelectNone.clicked.connect(lambda: self._set_all_checked(False))
        check_layout.addWidget(btnSelectAll)
        check_layout.addWidget(btnSelectNone)

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.listWidget)
        left_layout.addLayout(check_layout)

        # 右側：影像與標籤確認
        right_layout = QVBoxLayout()
        self.imageLabel = QLabel("請從左側點選標籤以匹配照片")
        self.imageLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.imageLabel.setFixedSize(600, 400)
        self.imageLabel.setStyleSheet("border: 1px solid #ccc;")

        self.timeLabel = QLabel("拍攝時間: -")

        # 顯示檔案現有 IPTC caption 與 CSV 預計寫入內容，方便比對
        self.currentCaptionLabel = QLabel("現有 IPTC Caption: -")
        self.currentCaptionLabel.setWordWrap(True)
        self._style_current_caption(has_caption=False)
        self.newCaptionLabel = QLabel("CSV 預計寫入: -")
        self.newCaptionLabel.setWordWrap(True)
        self.newCaptionLabel.setStyleSheet("background-color: #fff8e1; padding: 6px; border: 1px solid #ffe082;")

        btnWrite = QPushButton("寫入勾選項目的 IPTC 標籤")
        btnWrite.setStyleSheet("background-color: #28a745; color: white; padding: 10px;")
        btnWrite.clicked.connect(self.write_tag)

        # 重建快取按鈕：當資料夾內容變動時可手動重建
        btnRebuild = QPushButton("重建時間快取")
        btnRebuild.clicked.connect(self.rebuild_cache)

        right_layout.addWidget(self.imageLabel)
        right_layout.addWidget(self.timeLabel)
        right_layout.addWidget(self.currentCaptionLabel)
        right_layout.addWidget(self.newCaptionLabel)
        right_layout.addWidget(btnWrite)
        right_layout.addWidget(btnRebuild)

        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)
        self.setLayout(main_layout)

        self.listWidget.currentRowChanged.connect(self.on_item_changed)

    def _style_current_caption(self, has_caption):
        """依是否有現有 IPTC caption 切換顯示樣式。

        有內容：紅底加粗白字（提醒已存在、可能需確認是否重複寫入）
        無內容：灰色顯示
        """
        if has_caption:
            self.currentCaptionLabel.setStyleSheet(
                "background-color: #c62828; color: white; font-weight: bold;"
                " padding: 6px; border: 1px solid #b71c1c;"
            )
        else:
            self.currentCaptionLabel.setStyleSheet(
                "background-color: #f8f9fa; color: #6c757d;"
                " padding: 6px; border: 1px solid #dee2e6;"
            )

    def _set_all_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.listWidget.count()):
            self.listWidget.item(i).setCheckState(state)

    def find_target_file(self, entry):
        """依據快取對應表找出符合 DateTimeOriginal 的檔案路徑。"""
        fname = self.time_map.get(entry['DateTimeOriginal'])
        if fname is None:
            return None
        f_path = os.path.join(self.folder_path, fname)
        return f_path if os.path.exists(f_path) else None

    def get_current_caption(self, img_path):
        """讀取檔案現有的 IPTC Caption-Abstract。"""
        cmd = ["exiftool", "-s3", "-charset", "IPTC=UTF8", "-Caption-Abstract", img_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip()

    def on_item_changed(self, row):
        entry = self.csv_data[row]
        target_file = self.find_target_file(entry)

        # 預先顯示 CSV 預計寫入內容
        self.newCaptionLabel.setText(f"CSV 預計寫入: {entry['Caption-Abstract']}")

        if target_file:
            pixmap = QPixmap(target_file).scaled(550, 350, Qt.AspectRatioMode.KeepAspectRatio)
            self.imageLabel.setPixmap(pixmap)
            self.timeLabel.setText(
                f"匹配到檔案: {os.path.basename(target_file)} | 時間: {entry['DateTimeOriginal']}"
            )
            # 讀取現有 IPTC caption
            current = self.get_current_caption(target_file)
            if current:
                self.currentCaptionLabel.setText(f"現有 IPTC Caption: {current}")
                self._style_current_caption(has_caption=True)
            else:
                self.currentCaptionLabel.setText("現有 IPTC Caption: (無)")
                self._style_current_caption(has_caption=False)
        else:
            self.imageLabel.setText("未在資料夾中找到對應時間的檔案")
            self.timeLabel.setText("請確認檔案是否已放入資料夾，或重建時間快取")
            self.currentCaptionLabel.setText("現有 IPTC Caption: -")
            self._style_current_caption(has_caption=False)

    def write_tag(self):
        """一次寫入所有勾選項目的 IPTC 標籤。"""
        # 收集所有勾選的項目
        checked = []
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked.append(i)

        if not checked:
            QMessageBox.warning(self, "提示", "請先勾選要寫入的項目")
            return

        # 確認寫入
        reply = QMessageBox.question(
            self, "確認寫入",
            f"即將寫入 {len(checked)} 個項目的 IPTC 標籤，是否繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success = []
        failed = []
        for row in checked:
            entry = self.csv_data[row]
            target_path = self.find_target_file(entry)
            if target_path is None:
                failed.append((entry, "找不到匹配照片"))
                continue
            cmd = ["exiftool", "-charset", "IPTC=UTF8",
                   "-Caption-Abstract=" + entry['Caption-Abstract'],
                   "-overwrite_original", target_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                success.append(os.path.basename(target_path))
            else:
                failed.append((entry, result.stderr.strip() or "寫入失敗"))

        # 統整結果報告
        msg_lines = [f"成功寫入 {len(success)} 個檔案"]
        if success:
            msg_lines.append("\n".join(f"  ✓ {f}" for f in success))
        if failed:
            msg_lines.append(f"\n失敗 {len(failed)} 個項目:")
            for entry, reason in failed:
                msg_lines.append(f"  ✗ {entry['DateTimeOriginal']} - {reason}")

        if failed and not success:
            QMessageBox.critical(self, "寫入結果", "\n".join(msg_lines))
        elif failed:
            QMessageBox.warning(self, "寫入結果（部分失敗）", "\n".join(msg_lines))
        else:
            QMessageBox.information(self, "寫入完成", "\n".join(msg_lines))

    def rebuild_cache(self):
        """手動重建時間快取（資料夾內容變動時使用）。"""
        self.time_map = build_time_cache(self.folder_path)
        QMessageBox.information(
            self, "完成",
            f"已重建時間快取，共 {len(self.time_map)} 筆資料"
        )
        # 重新整理目前選擇的項目
        row = self.listWidget.currentRow()
        if row != -1:
            self.on_item_changed(row)


if __name__ == "__main__":
    folder = input("請輸入照片資料夾路徑: ").strip()
    csv_folder = input(
        "請輸入 CSV 資料夾路徑 (直接 Enter 使用照片資料夾): ").strip()
    if not csv_folder:
        csv_folder = folder

    if not os.path.isdir(folder):
        print(f"照片資料夾不存在: {folder}")
        sys.exit(1)
    if not os.path.isdir(csv_folder):
        print(f"CSV 資料夾不存在: {csv_folder}")
        sys.exit(1)

    print(f"照片資料夾: {folder}")
    print(f"CSV 資料夾: {csv_folder}")
    data = load_all_csv(csv_folder)

    # 嘗試讀取現有暫存檔；若不存在或失效則重新建立
    time_map = load_time_cache(folder)
    if time_map is None:
        print("首次執行：正在建立時間快取，請稍候...")
        time_map = build_time_cache(folder)
        print(f"時間快取建立完成，共 {len(time_map)} 筆資料")
    else:
        print(f"已載入時間快取，共 {len(time_map)} 筆資料")

    app = QApplication(sys.argv)
    window = TaggerApp(data, folder, time_map)
    window.show()
    sys.exit(app.exec())
