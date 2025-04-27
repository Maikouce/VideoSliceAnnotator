# VideoSliceAnnotator

## English Documentation

### Features

- Visual Timeline Annotation: Click to add, drag, and adjust segments on a timeline below the video.
- Category Management: Create/delete custom labels; copy & paste annotated segments.
- Robust Clip Export: Uses MoviePy to subclip each annotated interval and export by category.
- Project Save/Load: Save annotations to a JSON project file and reload at any time.
- Playback Controls: Play/pause, jump to segment boundaries, and loop segment playback.



### Usage

```bash
python src/main.py
```

1. Open a directory containing video files, add categories, and click on the timeline to annotate.
2. After annotating, click "Export Clips" and choose an output folder to export clips by category.

---

### Dependencies

- Python >= 3.8
- PySide6
- MoviePy

```text
# ffmpeg
PySide6
moviepy
```
![using](https://github.com/user-attachments/assets/9d3e48b0-2213-47c9-b066-fd9694c0a0be)

## 中文说明

### 功能

- 可视化时间线标注：在视频播放窗口下方，可点击添加、拖动、调整标注区域。
- 多类别管理：自定义标签类别，支持增删；复制粘贴片段区域。
- 稳定剪切导出：基于 moviepy 对每个标注区间进行无缝剪切并按类别输出。
- 项目保存/加载：将当前标注状态保存为 JSON 项目文件，可随时重新加载。
- 播放控制：播放/暂停、跳转到片段起止点，并自动循环当前片段。



### 使用

```bash
python src/main.py
```

1. 打开视频文件所在文件夹，添加类别，点击时间线进行标注。
2. 完成标注后，点击“导出片段”并选择输出目录，即可按类别导出剪辑。

---


