import sys
import os
import json
import threading
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict

from PySide6.QtCore import Qt, QUrl, QRectF, QPointF, QTimer, QObject, Signal
from PySide6.QtGui import QPainter, QColor, QMouseEvent, QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaFormat
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QFileDialog, QInputDialog,
    QMessageBox, QListWidget, QLabel, QSplitter, QMenu, QProgressDialog
)

# 使用 moviepy 进行稳定的剪切
from moviepy import VideoFileClip

@dataclass
class Timestamp:
    id: int
    category: str
    start: float  # seconds
    end: float    # seconds
    selected: bool = False

class TimelineWidget(QWidget):
    HANDLE_WIDTH = 6
    # 增加滑块高度以便更易点击
    SLIDER_HEIGHT = 12

    def __init__(self, player: QMediaPlayer, project):
        super().__init__()
        self.player = player
        self.project = project
        # 初始化上次使用的标签
        self.last_category = None
        # 略增时间线高度
        self.setMinimumHeight(40)
        self.dragging = None
        self.drag_offset = 0.0
        self.copied_region: Optional[Timestamp] = None

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()
        # 白色背景
        painter.fillRect(rect, QColor(250, 250, 250))
        duration = max(self.player.duration() / 1000.0, 1.0)
        # 时间刻度
        ticks = 5
        painter.setPen(QColor(150, 150, 150))
        painter.setFont(QFont('Arial', 7))
        for i in range(ticks + 1):
            x = rect.left() + i * rect.width() / ticks
            painter.drawLine(x, rect.bottom() - 8, x, rect.bottom())
            t = i * duration / ticks
            text = f"{t:.1f}s"
            tx = x - (painter.fontMetrics().horizontalAdvance(text) if i == ticks else 0)
            painter.drawText(tx, rect.bottom() - 10, text)
        # 绘制时间块
        for ts in self.project.timestamps_by_video.get(self.project.current_video, []):
            x1 = rect.left() + rect.width() * (ts.start / duration)
            x2 = rect.left() + rect.width() * (ts.end / duration)
            y = rect.top() + 4
            h = rect.height() - 18
            color = QColor(100, 200, 255, 160) if not ts.selected else QColor(255, 180, 100, 200)
            painter.fillRect(QRectF(x1, y, x2 - x1, h), color)
            painter.fillRect(QRectF(x1, y - self.SLIDER_HEIGHT, x2 - x1, self.SLIDER_HEIGHT), QColor(200, 200, 200))
            painter.fillRect(QRectF(x1, y, self.HANDLE_WIDTH, h), QColor(120, 120, 120))
            painter.fillRect(QRectF(x2 - self.HANDLE_WIDTH, y, self.HANDLE_WIDTH, h), QColor(120, 120, 120))
            painter.setPen(Qt.black)
            painter.setFont(QFont('Arial', 8))
            painter.drawText(QPointF(x1 + 3, y + 12), ts.category)
            painter.setFont(QFont('Arial', 6))
            painter.drawText(QPointF(x1 + 3, y + h + 10), f"{ts.start:.1f}s")
            painter.drawText(QPointF(x2 - painter.fontMetrics().horizontalAdvance(f"{ts.end:.1f}s") - 3, y + h + 10), f"{ts.end:.1f}s")
        # 播放头
        pos = self.player.position() / 1000.0
        x_play = rect.left() + rect.width() * (pos / duration)
        painter.setPen(QColor(255, 0, 0))
        painter.drawLine(x_play, rect.top(), x_play, rect.bottom())
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        pos_point = event.position().toPoint()
        t = (pos_point.x() / self.width()) * (self.player.duration() / 1000.0)
        clicked_ts = None
        for ts in reversed(self.project.timestamps_by_video.get(self.project.current_video, [])):
            if self._on_body(pos_point, ts) or self._on_slider(pos_point, ts):
                clicked_ts = ts
                break
        self.project.current_region = clicked_ts
        if event.button() == Qt.RightButton:
            if clicked_ts:
                menu = QMenu(self)
                delete_action = menu.addAction("删除块")
                action = menu.exec(event.globalPosition().toPoint())

                if action == delete_action:
                    self.project.timestamps_by_video[self.project.current_video].remove(clicked_ts)
                    self.update()
            else:
                menu = QMenu(self)
                cats = list(self.project.categories)
                if self.last_category in cats:
                    cats.remove(self.last_category)
                    cats.insert(0, self.last_category)
                actions = {}
                for c in cats:
                    actions[c] = menu.addAction(c)
                menu.addSeparator()
                add_tag = menu.addAction("添加标签...")
                del_tag = menu.addAction("删除标签...")
                action = menu.exec(event.globalPosition().toPoint())

                if action == add_tag:
                    text, ok = QInputDialog.getText(self, "新建标签", "标签名称:")
                    if ok and text:
                        self.project.categories.append(text)
                        self.last_category = text
                elif action == del_tag:
                    if not self.project.categories:
                        return
                    text, ok = QInputDialog.getItem(self, "删除标签", "选择要删除的标签:", self.project.categories, 0, False)
                    if ok and text:
                        self.project.categories.remove(text)
                        if self.last_category == text:
                            self.last_category = None
                else:
                    for c, act in actions.items():
                        if action == act:
                            cat = c
                            ok = True
                            self.last_category = c
                            break
                if action and action not in (del_tag,):
                    try:
                        cat
                    except NameError:
                        return
                    ts_id = self.project.next_id()
                    start_t = t
                    end_t = min(t + 2.0, self.player.duration() / 1000.0)
                    new_ts = Timestamp(id=ts_id, category=cat, start=start_t, end=end_t)
                    self.project.timestamps_by_video.setdefault(self.project.current_video, []).append(new_ts)
                    self.update()
            return
        if event.button() == Qt.LeftButton and clicked_ts:
            if self._on_slider(pos_point, clicked_ts):
                clicked_ts.selected = True
                self.dragging = (clicked_ts, 'move'); self.drag_offset = t - clicked_ts.start
            else:
                self.player.setPosition(int(clicked_ts.start * 1000))
            self.update()
            return
        for ts in reversed(self.project.timestamps_by_video.get(self.project.current_video, [])):
            if self._on_handle(pos_point, ts, 'start'):
                ts.selected = True; self.dragging = (ts, 'start'); self.drag_offset = ts.start - t; return
            if self._on_handle(pos_point, ts, 'end'):
                ts.selected = True; self.dragging = (ts, 'end'); self.drag_offset = ts.end - t; return
        if event.button() == Qt.LeftButton:
            self.player.setPosition(int(t * 1000))
            self.player.play()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.dragging: return
        pos_point = event.position().toPoint()
        t = (pos_point.x() / self.width()) * (self.player.duration() / 1000.0)
        ts, part = self.dragging
        if part == 'move':
            length = ts.end - ts.start
            new_start = max(0.0, min(t - self.drag_offset, self.player.duration() / 1000.0 - length))
            ts.start, ts.end = new_start, new_start + length
        elif part == 'start':
            ts.start = max(0.0, min(t + self.drag_offset, ts.end - 0.1))
        else:
            ts.end = min(self.player.duration() / 1000.0, max(t + self.drag_offset, ts.start + 0.1))
        self.player.setPosition(int((ts.start if part=='start' else ts.end) * 1000))
        self.update()

    def mouseReleaseEvent(self, event):
        self.dragging = None

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self.copied_region = self.project.current_region
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
            if self.copied_region:
                cr = self.copied_region
                duration = self.player.duration()/1000.0
                length = cr.end - cr.start
                new_start = min(cr.start + 1.0, duration - length)
                new_ts = Timestamp(id=self.project.next_id(), category=cr.category, start=new_start, end=new_start+length)
                self.project.timestamps_by_video.setdefault(self.project.current_video, []).append(new_ts)
                self.update()

    def _on_handle(self, pos, ts: Timestamp, which: str) -> bool:
        duration = max(self.player.duration() / 1000.0, 1.0)
        rect = self.rect()
        x1 = rect.left() + rect.width() * (ts.start / duration)
        x2 = rect.left() + rect.width() * (ts.end / duration)
        y = rect.top() + 4; h = rect.height() - 14
        r = QRectF(x1, y, self.HANDLE_WIDTH, h) if which == 'start' else QRectF(x2 - self.HANDLE_WIDTH, y, self.HANDLE_WIDTH, h)
        return r.contains(pos)

    def _on_body(self, pos, ts: Timestamp) -> bool:
        duration = max(self.player.duration() / 1000.0, 1.0)
        rect = self.rect()
        x1 = rect.left() + rect.width() * (ts.start / duration)
        x2 = rect.left() + rect.width() * (ts.end / duration)
        r = QRectF(x1 + self.HANDLE_WIDTH, rect.top() + 4, x2 - x1 - 2*self.HANDLE_WIDTH, rect.height() - 14)
        return r.contains(pos)

    def _on_slider(self, pos, ts: Timestamp) -> bool:
        duration = max(self.player.duration() / 1000.0, 1.0)
        rect = self.rect()
        x1 = rect.left() + rect.width() * (ts.start / duration)
        x2 = rect.left() + rect.width() * (ts.end / duration)
        y = rect.top() + 4 - self.SLIDER_HEIGHT
        r = QRectF(x1, y, x2 - x1, self.SLIDER_HEIGHT)
        return r.contains(pos)

class Project:
    def __init__(self):
        self.dir: Optional[str] = None
        self.video_files: List[str] = []
        self.categories: List[str] = []
        # 用于存储上次使用标签，可持久化到项目文件中
        self.last_category: Optional[str] = None
        self.timestamps_by_video: Dict[str, List[Timestamp]] = {}
        self._id_counter = 0
        self.current_video: Optional[str] = None
        self.current_region: Optional[Timestamp] = None

    def next_id(self):
        self._id_counter += 1; return self._id_counter

    def save(self, path: str):
        data = {
            'dir': self.dir,
            'video_files': self.video_files,
            'categories': self.categories,
            'last_category': self.last_category,
            'timestamps_by_video': {
                video: [asdict(ts) for ts in lst]
                for video, lst in self.timestamps_by_video.items()
            }
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        with open(path) as f:
            data = json.load(f)
        self.dir = data['dir']
        self.video_files = data['video_files']
        self.categories = data['categories']
        self.last_category = data.get('last_category')
        self.timestamps_by_video = {
            video: [Timestamp(**ts) for ts in lst]
            for video, lst in data['timestamps_by_video'].items()
        }
        self._id_counter = max((ts.id for lst in self.timestamps_by_video.values() for ts in lst), default=0)
        self.current_region = None

class ExportWorker(QObject):
    progress = Signal(int, int)
    finished = Signal()

    def __init__(self, project: Project, out_dir: str):
        super().__init__()
        self.project = project
        self.out_dir = out_dir

    def run(self):
        total = sum(len(lst) for lst in self.project.timestamps_by_video.values())
        done = 0
        for video, lst in self.project.timestamps_by_video.items():
            counts: Dict[str, int] = {}
            for ts in lst:
                counts.setdefault(ts.category, 0)
                counts[ts.category] += 1
                clip = VideoFileClip(video).subclipped(ts.start, ts.end)
                cat_dir = os.path.join(self.out_dir, ts.category)
                os.makedirs(cat_dir, exist_ok=True)
                name, ext = os.path.splitext(os.path.basename(video))
                seq = counts[ts.category]
                out_path = os.path.join(cat_dir, f"{name}_{ts.category}_{seq}{ext}")
                clip.write_videofile(out_path, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
                done += 1
                self.progress.emit(done, total)
        self.finished.emit()



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer(); self.player.setAudioOutput(self.audio_output)
        self.video_widget = QVideoWidget(); self.player.setVideoOutput(self.video_widget)
        self.video_list = QListWidget()
        self.video_list.currentTextChanged.connect(self.on_video_selected)
        self.video_list.itemDoubleClicked.connect(lambda item: self.on_video_selected(item.text()))
        self.timeline = TimelineWidget(self.player, self.project)
        self.player.durationChanged.connect(self.timeline.update)
        self.player.positionChanged.connect(self.on_position_changed)
        btn_style = "QPushButton{padding:6px; border:1px solid #888; border-radius:4px; background:#EEE; color:#333;} QPushButton:hover{background:#DDD;}"
        play_btn = QPushButton("播放"); play_btn.setStyleSheet(btn_style); play_btn.clicked.connect(self.player.play)
        pause_btn = QPushButton("暂停"); pause_btn.setStyleSheet(btn_style); pause_btn.clicked.connect(self.player.pause)
        folder_btn = QPushButton("打开文件夹"); folder_btn.setStyleSheet(btn_style); folder_btn.clicked.connect(self.open_directory)
        add_cat_btn = QPushButton("添加类别"); add_cat_btn.setStyleSheet(btn_style); add_cat_btn.clicked.connect(self.add_category)
        save_btn = QPushButton("保存项目"); save_btn.setStyleSheet(btn_style); save_btn.clicked.connect(self.save_project)
        load_btn = QPushButton("加载项目"); load_btn.setStyleSheet(btn_style); load_btn.clicked.connect(self.load_project)
        export_btn = QPushButton("导出片段"); export_btn.setStyleSheet(btn_style); export_btn.clicked.connect(self.export_clips)
        split = QSplitter(Qt.Horizontal)
        left = QWidget(); lv = QVBoxLayout(left); lv.addWidget(QLabel("视频列表")); lv.addWidget(self.video_list)
        right = QWidget(); rv = QVBoxLayout(right)
        rv.addWidget(self.video_widget, stretch=8)
        rv.addWidget(self.timeline, stretch=1)
        ctrl = QHBoxLayout();
        for w in (play_btn, pause_btn, folder_btn, add_cat_btn, save_btn, load_btn, export_btn): ctrl.addWidget(w)
        rv.addLayout(ctrl)
        split.addWidget(left); split.addWidget(right)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 4)
        self.setCentralWidget(split)
        self.setWindowTitle("视频标注与剪辑工具")
        self.setStyleSheet("QMainWindow{background:white;} QLabel{color:black;} QListWidget{background:#F9F9F9; color:black;} QMenu{background:white; color:black;} QProgressDialog{background:white; color:black;}")

    def open_directory(self):
        d = QFileDialog.getExistingDirectory(self, "选择工作目录")
        if not d: return
        self.project.dir = d
        exts = [QMediaFormat(f).mimeType().name().split('/')[-1] for f in QMediaFormat().supportedFileFormats(QMediaFormat.Decode)]
        self.project.video_files = [os.path.join(d, f) for f in os.listdir(d) if any(f.lower().endswith(ext) for ext in exts)]
        self.video_list.clear(); self.video_list.addItems(self.project.video_files)
        if self.project.video_files: self.video_list.setCurrentRow(0)

    def on_video_selected(self, path: str):
        self.project.current_video = path
        if path:
            self.player.setSource(QUrl.fromLocalFile(path)); QTimer.singleShot(100, self.player.pause); self.player.setPosition(0)
        self.timeline.update()

    def on_position_changed(self, pos: int):
        ts = self.project.current_region
        if ts and pos/1000.0 > ts.end:
            self.player.setPosition(int(ts.start * 1000))
        self.timeline.update()

    def add_category(self):
        text, ok = QInputDialog.getText(self, "新建类别", "类别名称:")
        if ok and text: self.project.categories.append(text)

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", filter="JSON files (*.json)")
        if path:
            self.project.save(path)
            QMessageBox.information(self, "保存", "项目已保存")

    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "加载项目", filter="JSON files (*.json)")
        if path:
            self.project.load(path)
            QMessageBox.information(self, "加载", "项目已加载")
            self.video_list.clear(); self.video_list.addItems(self.project.video_files)
            if self.project.video_files: self.video_list.setCurrentRow(0)
            self.timeline.update()

    def export_clips(self):
        if not self.project.dir:
            QMessageBox.warning(self, "错误", "请先选择工作目录并加载视频")
            return
        out = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not out: return
        total = sum(len(lst) for lst in self.project.timestamps_by_video.values())
        progress = QProgressDialog("正在导出片段...", "取消", 0, total, self)
        progress.setWindowModality(Qt.WindowModal)
        worker = ExportWorker(self.project, out)
        worker.progress.connect(lambda done, tot: progress.setValue(done))
        worker.finished.connect(progress.close)
        thread = threading.Thread(target=worker.run)
        thread.start()
        progress.exec()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow(); w.resize(1000, 700); w.show()
    sys.exit(app.exec())
