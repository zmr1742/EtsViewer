"""
自定义控件模块
包含CenteredStaticText、TSListView、ContentJsonViewer
"""
import re
import json
import os
import wx
from os import walk
from datetime import datetime
from os.path import getmtime, join as path_join, isfile

from utils import MAX_SIZE, get_font, AudioPlayer
from formatters import format_question_json, extract_choose_images, extract_audio_list, extract_role_images
from html_export import build_html_doc
from png_export import export_content_png
from notes import load_notes, notes_for_content, get_note, set_note


class CenteredStaticText(wx.StaticText):
    """居中显示的静态文本控件"""
    
    def __init__(self, parent, id=wx.ID_ANY, label=wx.EmptyString, 
                 pos=wx.DefaultPosition, size=wx.DefaultSize, 
                 style=0, name=wx.StaticTextNameStr):
        super().__init__(parent, id, label, pos, size, style, name)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, event: wx.PaintEvent):
        dc = wx.PaintDC(self)
        label = self.GetLabel()
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        dc.SetFont(self.GetFont())
        text_size = dc.GetTextExtent(label)
        size = self.GetSize()
        dc.DrawText(label, (size[0] - text_size[0]) // 2, (size[1] - text_size[1]) // 2)


class TSListView(wx.ListCtrl):
    """题目文件夹列表视图"""
    
    def __init__(self, parent: wx.Window, on_item_selected_callback):
        super().__init__(parent, size=(250, MAX_SIZE[1]), 
                        style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_SORT_ASCENDING)
        self._callback = on_item_selected_callback
        self.root_dir = ""
        
        self.InsertColumn(0, "文件名", width=60)
        self.InsertColumn(1, "更改时间", width=140)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)

    def load_dir(self, dir_path: str):
        """加载目录内容"""
        self.root_dir = dir_path
        walk_obj = walk(dir_path)
        _, dir_names, _ = next(walk_obj)
        self.DeleteAllItems()
        
        full_number_pattern = re.compile(r".*\d+")
        for dir_name in dir_names:
            if not re.match(full_number_pattern, dir_name):
                continue
            self.InsertItem(self.GetItemCount(), dir_name)
            mtime = getmtime(path_join(dir_path, dir_name))
            mtime_string = datetime.fromtimestamp(int(mtime))
            self.SetItem(self.GetItemCount() - 1, 1, str(mtime_string))
            self.SetItemData(self.GetItemCount() - 1, int(mtime * 100))
        
        self.SortItems(self._sort_callback)

    def _sort_callback(self, item1, item2):
        return item2 - item1

    def _on_item_selected(self, event: wx.ListEvent):
        item: wx.ListItem = event.GetItem()
        self._callback(item.GetText())


class ContentJsonViewer(wx.Panel):
    """JSON内容查看器面板"""
    
    def __init__(self, parent: wx.Window):
        super().__init__(parent)
        self.activate_exam_dir = ""
        self.contents = []
        self.content_names = []
        self.content_dirs = []
        self.content_index = 0
        self.ctrl_down = False
        self.pretty_print_enabled = True
        self.show_full_answers = False
        
        self._init_ui()

    def _init_ui(self):
        """初始化UI组件"""
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 选项栏
        option_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pretty_print_checkbox = wx.CheckBox(self, label="启用美观输出")
        self.pretty_print_checkbox.SetValue(True)
        self.pretty_print_checkbox.Bind(wx.EVT_CHECKBOX, self._on_pretty_print_toggle)
        
        self.full_answers_checkbox = wx.CheckBox(self, label="显示完整答案")
        self.full_answers_checkbox.SetValue(False)
        self.full_answers_checkbox.Bind(wx.EVT_CHECKBOX, self._on_full_answers_toggle)
        
        self.export_btn = wx.Button(self, label="导出为TXT")
        self.export_btn.Bind(wx.EVT_BUTTON, self._export_to_txt)

        self.export_html_btn = wx.Button(self, label="导出为HTML")
        self.export_html_btn.Bind(wx.EVT_BUTTON, self._export_to_html)
        self.export_html_btn.Enable(False)

        self.export_png_btn = wx.Button(self, label="导出为PNG")
        self.export_png_btn.Bind(wx.EVT_BUTTON, self._export_to_png)
        self.export_png_btn.Enable(False)

        self.note_btn = wx.Button(self, label="编辑笔记")
        self.note_btn.Bind(wx.EVT_BUTTON, self._on_note_btn)
        self.note_btn.Enable(False)

        self.audio_choice = wx.Choice(self)
        self.audio_btn = wx.Button(self, label="播放")
        self.audio_btn.Bind(wx.EVT_BUTTON, self._on_audio_btn)
        self.audio_btn.Enable(False)
        
        option_sizer.Add(self.pretty_print_checkbox, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        option_sizer.Add(self.full_answers_checkbox, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        option_sizer.Add(self.export_btn, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        option_sizer.Add(self.export_html_btn, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        option_sizer.Add(self.export_png_btn, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        option_sizer.Add(self.note_btn, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        option_sizer.AddStretchSpacer()
        option_sizer.Add(self.audio_choice, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        option_sizer.Add(self.audio_btn, proportion=0, flag=wx.LEFT | wx.RIGHT, border=10)
        sizer.Add(option_sizer, proportion=0, flag=wx.EXPAND | wx.TOP | wx.BOTTOM, border=5)

        # 导航栏
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.back_btn = wx.Button(self, label="返回")
        self.forward_btn = wx.Button(self, label="前进")
        self.content_dir_text = CenteredStaticText(self, label="当前目录：")
        self.content_dir_text.SetMinSize((MAX_SIZE[0], -1))
        
        top_sizer.Add(self.back_btn, proportion=0)
        top_sizer.Add(self.content_dir_text, flag=wx.EXPAND, proportion=1)
        top_sizer.Add(self.forward_btn, proportion=0)
        sizer.Add(top_sizer, proportion=0)

        # 内容显示区
        self.json_viewer = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        sizer.Add(self.json_viewer, flag=wx.EXPAND, proportion=3)

        # 图片预览区（选择题选项图片）
        self.image_panel = wx.ScrolledWindow(self)
        self.image_panel.SetScrollRate(10, 10)
        self.image_sizer = wx.BoxSizer(wx.VERTICAL)
        self.image_panel.SetSizer(self.image_sizer)
        self.image_panel.Hide()
        sizer.Add(self.image_panel, flag=wx.EXPAND, proportion=2)

        # 播放控制区（进度条 + 音量）
        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.progress_slider = wx.Slider(self, minValue=0, maxValue=1000)
        self.time_label = wx.StaticText(self, label="00:00 / 00:00")
        self.volume_label = wx.StaticText(self, label="音量 80%")
        self.volume_slider = wx.Slider(self, minValue=0, maxValue=100)
        self.volume_slider.SetValue(80)
        self.volume_slider.SetMinSize((120, -1))
        AudioPlayer.set_volume(80)
        bottom_sizer.Add(self.progress_slider, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, border=8, proportion=1)
        bottom_sizer.Add(self.time_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        bottom_sizer.Add(self.volume_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        bottom_sizer.Add(self.volume_slider, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        sizer.Add(bottom_sizer, proportion=0, flag=wx.EXPAND | wx.TOP | wx.BOTTOM, border=5)

        self.SetSizer(sizer)
        self.font_size = self.json_viewer.GetFont().GetPointSize()

        self._sync_progress = False
        self._play_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_play_timer, self._play_timer)

        # 绑定事件
        self.back_btn.Bind(wx.EVT_BUTTON, self._prev_content)
        self.forward_btn.Bind(wx.EVT_BUTTON, self._next_content)
        self.content_dir_text.Bind(wx.EVT_LEFT_DOWN, self._popup_choose_menu)
        self.json_viewer.Bind(wx.EVT_KEY_DOWN, lambda e: self._on_key_down(e, True))
        self.json_viewer.Bind(wx.EVT_KEY_UP, lambda e: self._on_key_down(e, False))
        self.json_viewer.Bind(wx.EVT_MOUSEWHEEL, self._on_scroll)
        self.progress_slider.Bind(wx.EVT_SLIDER, self._on_progress_slider)
        self.volume_slider.Bind(wx.EVT_SLIDER, self._on_volume_slider)

    def _on_pretty_print_toggle(self, event: wx.CommandEvent):
        self.pretty_print_enabled = event.IsChecked()
        self.full_answers_checkbox.Enable(event.IsChecked())
        if self.contents:
            self._content_change()

    def _on_full_answers_toggle(self, event: wx.CommandEvent):
        self.show_full_answers = event.IsChecked()
        if self.contents and self.pretty_print_enabled:
            self._content_change()

    def _on_key_down(self, event: wx.KeyEvent, down_up: bool):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            self.ctrl_down = down_up
        if not down_up:
            event.Skip()
            return
        elif event.GetKeyCode() == wx.WXK_LEFT and self.ctrl_down:
            self._prev_content()
        elif event.GetKeyCode() == wx.WXK_RIGHT and self.ctrl_down:
            self._next_content()
        else:
            event.Skip()

    def _on_scroll(self, event: wx.MouseEvent):
        if self.ctrl_down:
            if event.GetWheelRotation() > 0:
                self.font_size += 1
            else:
                self.font_size -= 1
            self.json_viewer.SetFont(get_font(self.font_size))
        event.Skip()

    def _popup_choose_menu(self, _):
        if self.activate_exam_dir == "":
            return
        menu = wx.Menu()
        for i, content_name in enumerate(self.content_names):
            menu.Append(i, content_name)
            menu.Bind(wx.EVT_MENU, self._switch_to_item, id=i)
        menu.Enable(self.content_index, False)
        self.content_dir_text.PopupMenu(menu)

    def _switch_to_item(self, event: wx.MenuEvent):
        self.content_index = event.GetId()
        self._content_change()

    def _next_content(self, *_):
        self.content_index += 1
        if self._check_index():
            self._content_change()
        else:
            self.content_index -= 1
            wx.MessageBox("已经是最后一个了", "提示", wx.OK | wx.ICON_INFORMATION)

    def _prev_content(self, *_):
        self.content_index -= 1
        if self._check_index():
            self._content_change()
        else:
            self.content_index += 1
            wx.MessageBox("已经是第一个了", "提示", wx.OK | wx.ICON_INFORMATION)

    def _check_index(self) -> bool:
        return 0 <= self.content_index < len(self.contents)

    def _content_change(self):
        self.content_dir_text.SetLabel(f"当前目录：{self.content_names[self.content_index]}")
        self.GetSizer().Layout()
        
        if self.pretty_print_enabled:
            formatted_content = format_question_json(
                self.contents[self.content_index],
                show_full_answers=self.show_full_answers
            )
            formatted_content = self._append_notes(formatted_content)
        else:
            formatted_content = json.dumps(self.contents[self.content_index], indent=4, ensure_ascii=False)
        self.json_viewer.SetValue(formatted_content)
        self._update_images()
        self._update_audio()

    def _current_block_key(self) -> str:
        """当前内容块的笔记 key 前缀（与 HTML 导出一致）"""
        dir_path_parts = self.activate_exam_dir.replace('\\', '/').split('/')
        folder_name = dir_path_parts[-1] if dir_path_parts[-1] else dir_path_parts[-2]
        if not self.contents or self.content_index >= len(self.content_names):
            return folder_name
        return f"{folder_name}-{self.content_names[self.content_index]}"

    def _question_count(self, data) -> int:
        """返回内容块中可标记的题目数"""
        info = data.get("info", {}) or {}
        st = data.get("structure_type", "")
        if st == "collector.choose":
            return len(info.get("xtlist", []))
        if st == "collector.role":
            return len(info.get("question", []))
        if st in ("collector.picture", "collector.word"):
            return 1
        return 0

    def _append_notes(self, text: str) -> str:
        """在格式化内容后附加当前内容块的笔记区块"""
        notes = notes_for_content(load_notes(), self._current_block_key())
        if not notes:
            return text
        lines = ["", "==我的笔记=="]
        for no in sorted(notes):
            lines.append(f"第 {no} 题：{notes[no]}")
        return text + "\n" + "\n".join(lines)

    def _edit_note(self, question_no: int):
        """编辑指定题号的笔记（留空删除）"""
        key = f"{self._current_block_key()}-q{question_no}"
        notes = load_notes()
        dlg = wx.TextEntryDialog(
            self,
            message=f"第 {question_no} 题的笔记（留空则删除笔记）：",
            caption="编辑笔记",
            value=get_note(notes, key),
        )
        if dlg.ShowModal() == wx.ID_OK:
            value = dlg.GetValue().strip()
            set_note(notes, key, value)
            self._content_change()
        dlg.Destroy()

    def _on_note_btn(self, _):
        """弹出题目菜单选择要编辑笔记的题"""
        if not self.contents:
            return
        question_count = self._question_count(self.contents[self.content_index])
        if question_count == 0:
            wx.MessageBox("当前内容没有可标记的题目", "提示", wx.OK | wx.ICON_INFORMATION, parent=self)
            return
        menu = wx.Menu()
        for i in range(1, question_count + 1):
            menu.Append(i, f"第 {i} 题")
            menu.Bind(wx.EVT_MENU, lambda e: self._edit_note(e.GetId()), id=i)
        self.content_dir_text.PopupMenu(menu)

    def _update_audio(self):
        """刷新音频选择列表"""
        self._reset_playback()
        audio_list = extract_audio_list(self.contents[self.content_index]) if self.contents else []
        self.audio_choice.Clear()
        self.audio_choice.Append([item["label"] for item in audio_list])
        self.audio_choice.SetSelection(0 if audio_list else -1)
        self.audio_btn.Enable(bool(audio_list))
        self.audio_btn.SetLabel("播放")

    def _reset_playback(self):
        """停止播放并复位进度显示"""
        AudioPlayer.stop()
        self._play_timer.Stop()
        self._sync_progress = True
        self.progress_slider.SetValue(0)
        self._sync_progress = False
        self.time_label.SetLabel("00:00 / 00:00")

    def _on_audio_btn(self, _):
        """播放/停止当前选中的音频"""
        if AudioPlayer.is_playing():
            self._reset_playback()
            self.audio_btn.SetLabel("播放")
            return
        audio_list = extract_audio_list(self.contents[self.content_index]) if self.contents else []
        selection = self.audio_choice.GetSelection()
        if not audio_list or selection < 0 or selection >= len(audio_list):
            return
        file_name = audio_list[selection]["file"]
        path = self._resolve_file(file_name)
        if not path:
            wx.MessageBox(f"未找到音频文件：{file_name}", "提示", wx.OK | wx.ICON_INFORMATION, parent=self)
            return
        if AudioPlayer.play(path):
            self.audio_btn.SetLabel("停止")
            self._sync_progress = True
            self.progress_slider.SetValue(0)
            self._sync_progress = False
            self.time_label.SetLabel(f"00:00 / {self._fmt_time(AudioPlayer.get_length())}")
            self._play_timer.Start(100)
        else:
            wx.MessageBox(f"音频播放失败：{path}", "错误", wx.OK | wx.ICON_ERROR, parent=self)

    @staticmethod
    def _fmt_time(ms: int) -> str:
        total = max(0, int(ms // 1000))
        return f"{total // 60:02d}:{total % 60:02d}"

    def _on_play_timer(self, _):
        """定时刷新播放进度"""
        if not AudioPlayer.is_playing():
            self._stop_playback()
            return
        length = AudioPlayer.get_length()
        position = AudioPlayer.get_position()
        if length > 0 and position >= length:
            self._stop_playback()
            return
        self._sync_progress = True
        if length > 0:
            self.progress_slider.SetValue(int(position * 1000 / length))
        self._sync_progress = False
        self.time_label.SetLabel(f"{self._fmt_time(position)} / {self._fmt_time(length)}")

    def _stop_playback(self):
        """播放结束或停止：复位按钮与进度"""
        AudioPlayer.stop()
        self._play_timer.Stop()
        self.audio_btn.SetLabel("播放")
        self._sync_progress = True
        self.progress_slider.SetValue(0)
        self._sync_progress = False
        self.time_label.SetLabel("00:00 / 00:00")

    def _on_progress_slider(self, event: wx.CommandEvent):
        """拖动进度条跳转播放位置"""
        if self._sync_progress:
            event.Skip()
            return
        length = AudioPlayer.get_length()
        if length > 0 and AudioPlayer.is_open():
            position = int(self.progress_slider.GetValue() * length / 1000)
            AudioPlayer.play_from(position)

    def _on_volume_slider(self, event: wx.CommandEvent):
        """调节音量"""
        value = self.volume_slider.GetValue()
        self.volume_label.SetLabel(f"音量 {value}%")
        AudioPlayer.set_volume(value)
        event.Skip()

    def _resolve_file(self, file_name: str) -> str:
        """在当前内容目录及根目录下查找素材文件，返回绝对路径或空字符串"""
        if not file_name:
            return ""
        content_dir = ""
        if self.content_dirs and 0 <= self.content_index < len(self.content_dirs):
            content_dir = self.content_dirs[self.content_index]
        for base in [content_dir, self.activate_exam_dir]:
            if not base:
                continue
            for candidate in [path_join(base, "material", file_name), path_join(base, file_name)]:
                if isfile(candidate):
                    return candidate
        return ""

    def _update_images(self):
        """刷新图片预览区（选择题选项图片 / 角色扮演题干图片）"""
        self.image_sizer.Clear(True)
        content = self.contents[self.content_index] if self.contents else None
        show = False
        if content and self.pretty_print_enabled:
            structure_type = content.get("structure_type")
            if structure_type == "collector.choose":
                choose_images = extract_choose_images(content)
                if any(question["options"] for question in choose_images):
                    show = True
                    self._build_images(choose_images)
            elif structure_type == "collector.role":
                role_images = extract_role_images(content)
                if role_images:
                    show = True
                    self._build_role_images(role_images)
        self.image_panel.Show(show)
        self.image_panel.FitInside()
        self.GetSizer().Layout()

    def _build_role_images(self, role_images):
        """在图片预览区中渲染角色扮演各题的题干图片"""
        normal_colour = self.image_panel.GetBackgroundColour()
        notes = notes_for_content(load_notes(), self._current_block_key())
        for idx, item in enumerate(role_images, 1):
            box = wx.Panel(self.image_panel)
            box.SetBackgroundColour(normal_colour)
            box_sizer = wx.BoxSizer(wx.VERTICAL)

            title = wx.StaticText(box, label=f"第 {idx} 题　题干图片（点击可编辑笔记）")
            title.SetBackgroundColour(normal_colour)
            title.SetForegroundColour(wx.Colour(15, 157, 107))
            box_sizer.Add(title, flag=wx.TOP | wx.LEFT | wx.RIGHT, border=8)
            title.Bind(wx.EVT_LEFT_DOWN, lambda e, idx=idx: self._edit_note(idx))

            bitmap = self._load_option_image(item["img"])
            if bitmap:
                img_ctrl = wx.StaticBitmap(box, bitmap=bitmap)
                img_ctrl.SetBackgroundColour(normal_colour)
                box_sizer.Add(img_ctrl, flag=wx.ALIGN_CENTER | wx.ALL, border=6)
            else:
                missing = wx.StaticText(box, label=f"[缺图] {item['img']}")
                missing.SetBackgroundColour(normal_colour)
                box_sizer.Add(missing, flag=wx.ALL, border=8)

            note_text = notes.get(idx, "")
            if note_text:
                note_lbl = wx.StaticText(box, label=f"📝 {note_text}")
                note_lbl.SetBackgroundColour(normal_colour)
                note_lbl.SetForegroundColour(wx.Colour(180, 83, 9))
                box_sizer.Add(note_lbl, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

            box.SetSizer(box_sizer)
            self.image_sizer.Add(box, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=6)

    def _build_images(self, choose_images):
        """在图片预览区中逐题渲染选项图片"""
        highlight_colour = wx.Colour(210, 240, 210)
        normal_colour = self.image_panel.GetBackgroundColour()
        notes = notes_for_content(load_notes(), self._current_block_key())
        for idx, question in enumerate(choose_images, 1):
            if not question["options"]:
                continue
            title = wx.StaticText(self.image_panel, label=f"第 {idx} 题　正确答案：{question['answer']}（点击可编辑笔记）")
            title.SetForegroundColour(wx.Colour(15, 157, 107))
            self.image_sizer.Add(title, flag=wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
            title.Bind(wx.EVT_LEFT_DOWN, lambda e, idx=idx: self._edit_note(idx))

            option_sizer = wx.BoxSizer(wx.HORIZONTAL)
            for opt in question["options"]:
                bg = highlight_colour if opt["is_answer"] else normal_colour
                box = wx.Panel(self.image_panel)
                box.SetBackgroundColour(bg)
                box_sizer = wx.BoxSizer(wx.VERTICAL)

                bitmap = self._load_option_image(opt["wj"])
                if bitmap:
                    img_ctrl = wx.StaticBitmap(box, bitmap=bitmap)
                    img_ctrl.SetBackgroundColour(bg)
                    box_sizer.Add(img_ctrl, flag=wx.ALIGN_CENTER)
                else:
                    missing = wx.StaticText(box, label=f"[缺图] {opt['wj']}")
                    missing.SetBackgroundColour(bg)
                    box_sizer.Add(missing, flag=wx.ALL, border=8)

                mark = "✓" if opt["is_answer"] else ""
                label = wx.StaticText(box, label=f"选项 {opt['mc']} {mark}".rstrip())
                label.SetBackgroundColour(bg)
                box_sizer.Add(label, flag=wx.ALIGN_CENTER | wx.TOP, border=4)

                box.SetSizer(box_sizer)
                option_sizer.Add(box, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=6)
            self.image_sizer.Add(option_sizer, flag=wx.LEFT, border=6)

            note_text = notes.get(idx, "")
            if note_text:
                note_lbl = wx.StaticText(self.image_panel, label=f"📝 {note_text}")
                note_lbl.SetForegroundColour(wx.Colour(180, 83, 9))
                self.image_sizer.Add(note_lbl, flag=wx.LEFT | wx.BOTTOM, border=14)

    def _load_option_image(self, file_name: str, max_height=150, max_width=220):
        """加载并缩放选项图片，失败返回None"""
        path = self._resolve_file(file_name)
        if not path:
            return None
        try:
            image = wx.Image(path)
        except Exception:
            return None
        width, height = image.GetWidth(), image.GetHeight()
        if width <= 0 or height <= 0:
            return None
        if height > max_height:
            ratio = max_height / height
            width = int(width * ratio)
            height = max_height
        if width > max_width:
            ratio = max_width / width
            height = int(height * ratio)
            width = max_width
        if width != image.GetWidth() or height != image.GetHeight():
            image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
        return wx.Bitmap(image)

    def init_data(self, dir_path: str):
        """初始化数据，加载目录中的content.json文件"""
        self.content_names.clear()
        self.contents.clear()
        self.content_dirs.clear()
        self.activate_exam_dir = dir_path
        
        walk_obj = walk(dir_path)
        _, dir_names, _ = next(walk_obj)
        errors = []
        
        for dir_name in dir_names:
            if dir_name.startswith("content"):
                try:
                    with open(path_join(dir_path, dir_name, "content.json"), "r", encoding="utf-8") as f:
                        content_text = f.read()
                    self.contents.append(json.loads(content_text))
                    self.content_names.append(dir_name)
                    self.content_dirs.append(path_join(dir_path, dir_name))
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    errors.append(f"{dir_name}: {str(e)}")
        
        if errors:
            wx.MessageBox(f"解析错误：\n" + "\n".join(errors), "错误", wx.OK | wx.ICON_ERROR, parent=self)
        
        self.content_index = 0
        self.export_html_btn.Enable(bool(self.contents))
        self.export_png_btn.Enable(bool(self.contents))
        self.note_btn.Enable(bool(self.contents))
        self._content_change()

    def _export_to_txt(self, event: wx.CommandEvent):
        """导出内容为TXT文件"""
        if not self.contents or not self.activate_exam_dir:
            wx.MessageBox("没有可导出的数据或目录未加载。", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        
        dir_path_parts = self.activate_exam_dir.replace('\\', '/').split('/')
        folder_name = dir_path_parts[-1] if dir_path_parts[-1] else dir_path_parts[-2]
        
        with wx.FileDialog(
            self,
            message="保存导出文件",
            defaultDir="",
            defaultFile=f"export_{folder_name}.txt",
            wildcard="Text files (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            
            pathname = fileDialog.GetPath()
            try:
                with open(pathname, 'w', encoding='utf-8') as file:
                    for i, (content_name, content_data) in enumerate(zip(self.content_names, self.contents)):
                        file.write(f"--- 条目 {i+1}: {content_name} ---\n")
                        if self.pretty_print_enabled:
                            formatted_content = format_question_json(
                                content_data,
                                show_full_answers=self.show_full_answers
                            )
                        else:
                            formatted_content = json.dumps(content_data, indent=4, ensure_ascii=False)
                        file.write(formatted_content)
                        block_notes = notes_for_content(load_notes(), f"{folder_name}-{content_name}")
                        for no in sorted(block_notes):
                            file.write(f"[笔记] 第 {no} 题：{block_notes[no]}\n")
                        file.write("\n\n")
                wx.MessageBox(f"导出成功！文件保存至：\n{pathname}", "成功", wx.OK | wx.ICON_INFORMATION)
            except IOError:
                wx.MessageBox(f"无法保存文件：{pathname}", "错误", wx.OK | wx.ICON_ERROR)

    def _export_to_html(self, event: wx.CommandEvent):
        """导出整卷内容为单文件HTML"""
        if not self.contents or not self.activate_exam_dir:
            wx.MessageBox("没有可导出的数据或目录未加载。", "提示", wx.OK | wx.ICON_INFORMATION)
            return

        dir_path_parts = self.activate_exam_dir.replace('\\', '/').split('/')
        folder_name = dir_path_parts[-1] if dir_path_parts[-1] else dir_path_parts[-2]

        with wx.FileDialog(
            self,
            message="保存 HTML 文件",
            defaultDir="",
            defaultFile=f"export_{folder_name}.html",
            wildcard="HTML files (*.html)|*.html",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = fileDialog.GetPath()
            html_dir = os.path.dirname(pathname)
            try:
                html_text = build_html_doc(
                    self.contents, self.content_names, self.content_dirs,
                    html_dir=html_dir, root_name=folder_name,
                    notes=load_notes(),
                )
                with open(pathname, 'w', encoding='utf-8') as file:
                    file.write(html_text)
                wx.MessageBox(
                    f"导出成功！文件保存至：\n{pathname}\n\n"
                    f"图片和音频已内嵌进 HTML，单文件可独立分享。",
                    "成功", wx.OK | wx.ICON_INFORMATION)
            except (IOError, OSError) as e:
                wx.MessageBox(f"无法保存文件：{pathname}\n{e}", "错误", wx.OK | wx.ICON_ERROR)

    def _export_to_png(self, event: wx.CommandEvent):
        """导出当前内容为PNG图片"""
        if not self.contents or not self.activate_exam_dir:
            wx.MessageBox("没有可导出的数据或目录未加载。", "提示", wx.OK | wx.ICON_INFORMATION)
            return

        content = self.contents[self.content_index]
        content_name = self.content_names[self.content_index]
        content_dir = self.content_dirs[self.content_index]
        type_name = _specific_type_name(content)

        with wx.FileDialog(
            self,
            message="保存 PNG 文件",
            defaultDir="",
            defaultFile=f"export_{content_name}.png",
            wildcard="PNG files (*.png)|*.png",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = fileDialog.GetPath()
            try:
                export_content_png(content, content_dir, pathname, type_name,
                                   block_key=self._current_block_key(), notes=load_notes())
                wx.MessageBox(f"导出成功！文件保存至：\n{pathname}", "成功", wx.OK | wx.ICON_INFORMATION)
            except (IOError, OSError) as e:
                wx.MessageBox(f"无法保存文件：{pathname}\n{e}", "错误", wx.OK | wx.ICON_ERROR)
