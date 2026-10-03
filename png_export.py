"""
PNG 导出模块
把 content 内容渲染为 PNG 图片，支持选择题（含图片）、角色扮演（含题干图片）和文本题型。
"""
import re
import wx
from os.path import join as path_join, isfile

from utils import clean_html_tags

WIDTH = 820
MARGIN = 24
TITLE_H = 44
Q_GAP = 18
OPT_GAP = 12
IMG_MAX_H = 130
IMG_MAX_W = 190


def _resolve(content_dir, file_name):
    if not file_name:
        return ""
    for cand in [path_join(content_dir, "material", file_name), path_join(content_dir, file_name)]:
        if isfile(cand):
            return cand
    return ""


def _load_scaled_image(path):
    img = wx.Image(path, wx.BITMAP_TYPE_ANY)
    w, h = img.GetWidth(), img.GetHeight()
    if w <= 0 or h <= 0:
        return None
    if h > IMG_MAX_H:
        ratio = IMG_MAX_H / h
        w, h = int(w * ratio), IMG_MAX_H
    if w > IMG_MAX_W:
        ratio = IMG_MAX_W / w
        h, w = int(h * ratio), IMG_MAX_W
    return img.Scale(w, h, wx.IMAGE_QUALITY_HIGH)


def _wrap_text(dc, text, max_width):
    dc.SetFont(dc.GetFont())
    words = text.split(" ")
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if dc.GetTextExtent(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [""]


def _calc_note_lines(dc, notes, key, width):
    """计算一条笔记的行数（无笔记返回 0）"""
    note = notes.get(key, "")
    if not note:
        return 0
    return len(_wrap_text(dc, "📝 " + note, width))


def _calc_choose_height(dc, info, content_dir, width, block_key="", notes=None):
    notes = notes or {}
    xtlist = info.get("xtlist", [])
    total = 0
    for i, xt in enumerate(xtlist, 1):
        value = clean_html_tags(xt.get("xt_value", ""))
        text_lines = _wrap_text(dc, value or xt.get("xt_nr", ""), width) if value or xt.get("xt_nr") else []
        total += 6 + max(len(text_lines), 1) * 20 + OPT_GAP
        xxlist = xt.get("xxlist", [])
        has_img = any(opt.get("xx_wj") for opt in xxlist)
        if has_img:
            total += IMG_MAX_H + 24
        else:
            total += len(xxlist) * 22
        total += _calc_note_lines(dc, notes, f"{block_key}-q{i}", width - 50) * 18 + 6
        total += Q_GAP
    return total


def _calc_text_height(dc, text, width, font):
    dc.SetFont(font)
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(_wrap_text(dc, paragraph, width))
    return max(len(lines), 1) * 18


def export_content_png(content, content_dir, path, type_name="", block_key="", notes=None):
    """把单个 content 渲染为 PNG 并保存到 path"""
    st = content.get("structure_type", "")
    info = content.get("info", {}) or {}
    notes = notes or {}

    font_title = wx.Font(15, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, faceName="Microsoft YaHei")
    font_text = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Microsoft YaHei")
    font_small = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, faceName="Microsoft YaHei")

    content_w = WIDTH - 2 * MARGIN

    tmp_bmp = wx.Bitmap(1, 1)
    tmp_dc = wx.MemoryDC(tmp_bmp)

    if st == "collector.choose":
        body_h = _calc_choose_height(tmp_dc, info, content_dir, content_w, block_key, notes)
    elif st == "collector.role":
        body_h = _calc_role_height(tmp_dc, info, content_dir, content_w, block_key, notes)
    else:
        from formatters import format_question_json
        text = format_question_json(content, show_full_answers=True)
        body_h = _calc_text_height(tmp_dc, text, content_w, font_text)

    total_h = MARGIN + TITLE_H + Q_GAP + body_h + MARGIN
    if total_h < 200:
        total_h = 200

    bmp = wx.Bitmap(WIDTH, total_h)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.WHITE))
    dc.Clear()

    dc.SetFont(font_title)
    dc.SetTextForeground(wx.Colour(15, 53, 43))
    dc.DrawText(type_name or st, MARGIN, MARGIN)

    line_color = wx.Colour(223, 234, 227)
    dc.SetPen(wx.Pen(line_color, 1))
    dc.DrawLine(MARGIN, MARGIN + TITLE_H - 6, WIDTH - MARGIN, MARGIN + TITLE_H - 6)

    y = MARGIN + TITLE_H + Q_GAP

    if st == "collector.choose":
        y = _draw_choose(dc, info, content_dir, content_w, y, font_text, font_small, block_key, notes)
    elif st == "collector.role":
        y = _draw_role(dc, info, content_dir, content_w, y, font_text, font_small, block_key, notes)
    else:
        from formatters import format_question_json
        text = format_question_json(content, show_full_answers=True)
        y = _draw_text_block(dc, text, content_w, y, font_text)

    dc.SelectObject(wx.NullBitmap)
    bmp.SaveFile(path, wx.BITMAP_TYPE_PNG)


def _draw_note_line(dc, note, x, y, width, font_text):
    """绘制一行笔记，返回新的 y"""
    note_colour = wx.Colour(180, 83, 9)
    dc.SetFont(font_text)
    dc.SetTextForeground(note_colour)
    for line in _wrap_text(dc, "📝 " + note, width):
        dc.DrawText(line, x, y)
        y += 18
    return y


def _clean_ask_text(ask: str) -> str:
    """清理题干：去掉 ets_thN 前缀与原始题号"""
    ask = re.sub(r"ets_th\d+\s*", "", ask)
    return re.sub(r"^\s*\d+\s*[.、．]\s*", "", ask).strip()


def _calc_role_height(dc, info, content_dir, width, block_key="", notes=None):
    notes = notes or {}
    total = 0
    dialog = clean_html_tags(info.get("value", ""))
    if dialog:
        total += 20 + len(_wrap_text(dc, dialog, width)) * 18 + 12
    for i, q in enumerate(info.get("question", []), 1):
        ask = _clean_ask_text(clean_html_tags(q.get("ask", "")))
        total += 6 + max(len(_wrap_text(dc, ask, width - 32)), 1) * 20 + 6
        if q.get("askimg") and _resolve(content_dir, q["askimg"]):
            total += IMG_MAX_H + 28
        keywords = [k.strip() for k in re.split(r"[|｜]", q.get("keywords", "")) if k.strip()]
        if keywords:
            total += 20
        std = [clean_html_tags(s.get("value", "")) for s in q.get("std", []) if s.get("value")]
        total += 20
        for a in std:
            total += len(_wrap_text(dc, f"- {a}", width - 50)) * 18
        total += _calc_note_lines(dc, notes, f"{block_key}-q{i}", width - 50) * 18 + 6
        total += 12 + Q_GAP
    return total


def _draw_role(dc, info, content_dir, width, y, font_text, font_small, block_key="", notes=None):
    notes = notes or {}
    num_color = wx.Colour(15, 157, 107)
    dialog = clean_html_tags(info.get("value", ""))

    if dialog:
        dc.SetFont(font_small)
        dc.SetTextForeground(wx.Colour(92, 117, 104))
        dc.DrawText("==对话内容==", MARGIN, y)
        y += 20
        dc.SetFont(font_text)
        dc.SetTextForeground(wx.Colour(21, 53, 43))
        for line in _wrap_text(dc, dialog, width):
            dc.DrawText(line, MARGIN, y)
            y += 18
        y += 12

    for i, q in enumerate(info.get("question", []), 1):
        ask = _clean_ask_text(clean_html_tags(q.get("ask", "")))

        dc.SetFont(font_small)
        dc.SetBrush(wx.Brush(wx.Colour(220, 243, 228)))
        dc.SetPen(wx.Pen(wx.Colour(220, 243, 228)))
        dc.DrawCircle(MARGIN + 12, y + 10, 12)
        dc.SetTextForeground(num_color)
        dc.DrawText(str(i), MARGIN + 7, y + 3)

        dc.SetFont(font_text)
        dc.SetTextForeground(wx.Colour(21, 53, 43))
        for line in _wrap_text(dc, ask, width - 32):
            dc.DrawText(line, MARGIN + 32, y)
            y += 20
        y += 6

        img_path = _resolve(content_dir, q.get("askimg", ""))
        if img_path:
            img = _load_scaled_image(img_path)
            if img:
                dc.DrawBitmap(wx.Bitmap(img), MARGIN + 32, y, False)
                y += img.GetHeight() + 12

        keywords = [k.strip() for k in re.split(r"[|｜]", q.get("keywords", "")) if k.strip()]
        if keywords:
            dc.SetFont(font_small)
            dc.SetTextForeground(wx.Colour(180, 83, 9))
            dc.DrawText("关键词：" + " | ".join(keywords), MARGIN + 32, y)
            y += 20

        std = [clean_html_tags(s.get("value", "")) for s in q.get("std", []) if s.get("value")]
        dc.SetFont(font_small)
        dc.SetTextForeground(wx.Colour(92, 117, 104))
        dc.DrawText("参考答案：", MARGIN + 32, y)
        y += 20
        dc.SetFont(font_text)
        dc.SetTextForeground(wx.Colour(21, 53, 43))
        for j, a in enumerate(std, 1):
            for line in _wrap_text(dc, f"{j}. {a}", width - 50):
                dc.DrawText(line, MARGIN + 32, y)
                y += 18
        note = notes.get(f"{block_key}-q{i}", "")
        if note:
            y = _draw_note_line(dc, note, MARGIN + 32, y, width - 50, font_text)
        y += 12 + Q_GAP
    return y


def _draw_choose(dc, info, content_dir, width, y, font_text, font_small, block_key="", notes=None):
    notes = notes or {}
    xtlist = info.get("xtlist", [])
    num_color = wx.Colour(15, 157, 107)
    correct_bg = wx.Colour(209, 240, 210)
    correct_bd = wx.Colour(167, 243, 208)
    border_color = wx.Colour(223, 234, 227)

    for i, xt in enumerate(xtlist, 1):
        answer = xt.get("answer", "")
        value = clean_html_tags(xt.get("xt_value", ""))
        xxlist = xt.get("xxlist", [])

        dc.SetFont(font_small)
        dc.SetBrush(wx.Brush(wx.Colour(220, 243, 228)))
        dc.SetPen(wx.Pen(wx.Colour(220, 243, 228)))
        dc.DrawCircle(MARGIN + 12, y + 10, 12)
        dc.SetTextForeground(num_color)
        dc.DrawText(str(i), MARGIN + 7, y + 3)

        text_x = MARGIN + 32
        dc.SetFont(font_text)
        dc.SetTextForeground(wx.Colour(21, 53, 43))
        if value:
            for line in _wrap_text(dc, value, width - 32):
                dc.DrawText(line, text_x, y)
                y += 20
        y += 6

        has_img = any(opt.get("xx_wj") for opt in xxlist)
        if has_img:
            ox = MARGIN + 32
            for opt in xxlist:
                mc = opt.get("xx_mc", "")
                wj = opt.get("xx_wj", "")
                is_correct = bool(answer) and mc == answer
                img_path = _resolve(content_dir, wj)
                img = _load_scaled_image(img_path) if img_path else None

                if img:
                    iw, ih = img.GetWidth(), img.GetHeight()
                    if is_correct:
                        dc.SetBrush(wx.Brush(correct_bg))
                        dc.SetPen(wx.Pen(correct_bd, 2))
                        dc.DrawRectangle(ox - 4, y - 4, iw + 8, ih + 8)
                    dc.DrawBitmap(wx.Bitmap(img), ox, y, False)
                    dc.SetFont(font_small)
                    dc.SetTextForeground(num_color if is_correct else wx.Colour(92, 117, 104))
                    label = f"{mc}{' \u2713' if is_correct else ''}"
                    dc.DrawText(label, ox + iw // 2 - 12, y + ih + 4)
                    ox += iw + OPT_GAP + 16
            y += IMG_MAX_H + 28
        else:
            for opt in xxlist:
                mc = opt.get("xx_mc", "")
                nr = clean_html_tags(opt.get("xx_nr", ""))
                is_correct = bool(answer) and mc == answer
                if is_correct:
                    dc.SetBrush(wx.Brush(correct_bg))
                    dc.SetPen(wx.Pen(correct_bd, 1))
                    dc.DrawRectangle(MARGIN + 32, y, width - 32, 22)
                dc.SetFont(font_small)
                dc.SetTextForeground(num_color if is_correct else wx.Colour(92, 117, 104))
                dc.DrawText(f"{mc}.", MARGIN + 38, y + 3)
                dc.SetFont(font_text)
                dc.SetTextForeground(wx.Colour(15, 87, 63) if is_correct else wx.Colour(21, 53, 43))
                for line in _wrap_text(dc, nr, width - 60):
                    dc.DrawText(line, MARGIN + 58, y + 2)
                    y += 20
            y += 8
        note = notes.get(f"{block_key}-q{i}", "")
        if note:
            y = _draw_note_line(dc, note, MARGIN + 32, y, width - 50, font_text)
        y += Q_GAP
    return y


def _draw_text_block(dc, text, width, y, font):
    dc.SetFont(font)
    dc.SetTextForeground(wx.Colour(21, 53, 43))
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            y += 9
            continue
        for line in _wrap_text(dc, paragraph, width):
            dc.DrawText(line, MARGIN, y)
            y += 18
    return y
