"""
笔记存储模块
自定义题目标记，存于 %APPDATA%\\EtsViewer\\notes.json
"""
import json
import os
from os.path import expandvars, join as path_join

_NOTES_DIR = path_join(expandvars(r"%APPDATA%"), "EtsViewer")
_NOTES_FILE = path_join(_NOTES_DIR, "notes.json")


def load_notes() -> dict:
    """加载全部笔记"""
    try:
        with open(_NOTES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_notes(notes: dict) -> bool:
    """保存全部笔记"""
    try:
        os.makedirs(_NOTES_DIR, exist_ok=True)
        with open(_NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def get_note(notes: dict, key: str) -> str:
    """读取一条笔记"""
    return notes.get(key, "")


def set_note(notes: dict, key: str, value: str) -> bool:
    """设置或删除一条笔记（value 为空则删除）"""
    if value:
        notes[key] = value
    else:
        notes.pop(key, None)
    return save_notes(notes)


def notes_for_content(notes: dict, block_key: str) -> dict:
    """返回某个内容块下所有题的笔记 {题号: 内容}"""
    prefix = block_key + "-q"
    result = {}
    for k, v in notes.items():
        if k.startswith(prefix):
            try:
                result[int(k[len(prefix):])] = v
            except ValueError:
                pass
    return result
