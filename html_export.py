"""
HTML 导出模块
将 ETS 内容渲染为对齐「E听说答案校对」模板视觉的单文件 HTML。
图片 base64 内嵌，音频相对路径引用，交互功能由内嵌原生 JS 实现。
"""
import re
import json
import base64
from os.path import join as path_join, isfile, relpath

from utils import clean_html_tags

TYPE_NAMES = {
    "collector.choose": "听力选择",
    "collector.role": "角色扮演",
    "collector.picture": "图片描述",
    "collector.read": "阅读理解",
    "collector.repeat_essay": "问答短文",
    "collector.repeat_dialogue": "对话复述",
    "collector.word": "词汇问答",
}

ANSWER_PREVIEW = 8


def _specific_type_name(data) -> str:
    """根据内容特征返回更精确的题型名"""
    st = data.get("structure_type", "")
    info = data.get("info", {}) or {}
    if st == "collector.choose":
        xtlist = info.get("xtlist", [])
        has_image = any(opt.get("xx_wj") for xt in xtlist for opt in xt.get("xxlist", []))
        if has_image:
            return "听句子选择图片"
        has_transcript = bool(clean_html_tags(info.get("st_nr", "")))
        if has_transcript:
            return "听对话选择"
        return "听句子选择"
    return TYPE_NAMES.get(st, st)


def _esc(text) -> str:
    """HTML 转义"""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _img_base64(path: str) -> str:
    """读取图片并转为 base64 data URI"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp"}.get(ext, "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _audio_base64(path: str) -> str:
    """读取音频并转为 base64 data URI"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    mime = {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
            "m4a": "audio/mp4", "aac": "audio/aac"}.get(ext, "audio/mpeg")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _split_transcript(text: str):
    """将连写的 W:/M: 对话切分为 (speaker, text) 列表"""
    normalized = re.sub(r"\b([WM])[：:]\s*", "\n\\1: ", text)
    chunks = [c.strip() for c in normalized.split("\n") if c.strip()]
    result = []
    last = "W"
    for chunk in chunks:
        m = re.match(r"^([WM])[：:]\s*(.*)$", chunk)
        if m:
            last = m.group(1)
            result.append([last, m.group(2).strip()])
        elif result:
            result[-1][1] += " " + chunk
        else:
            result.append([last, chunk])
    return result


_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "in", "on", "at", "is", "are",
    "was", "were", "be", "been", "it", "its", "he", "she", "they", "we", "you",
    "my", "his", "her", "our", "their", "this", "that", "these", "those",
    "with", "for", "from", "as", "by", "so", "not", "no", "do", "did", "does",
    "had", "has", "have", "will", "would", "can", "could",
}


def _expand_keywords(keywords):
    """展开关键词：整短语 + 多词短语中的实词"""
    terms = set()
    for kw in keywords:
        k = kw.strip().lower()
        if not k:
            continue
        terms.add(k)
        if re.search(r"\s", k):
            for w in re.split(r"\s+", k):
                if len(w) >= 3 and w not in _STOPWORDS:
                    terms.add(w)
    return sorted(terms, key=len, reverse=True)


def _highlight_keywords(text: str, keywords) -> str:
    """在已转义的文本上对关键词做琥珀色高亮，返回含 <mark> 的片段"""
    terms = _expand_keywords(keywords)
    if not terms:
        return text
    pattern = "|".join(re.escape(t) for t in terms)
    try:
        return re.sub(rf"\b(?:{pattern})\b", lambda m: f'<mark class="kw-mark">{m.group(0)}</mark>',
                      text, flags=re.IGNORECASE)
    except re.error:
        return text


class _Renderer:
    """渲染上下文：负责素材定位、图片/音频标签、各题型渲染"""

    def __init__(self, html_dir: str):
        self.html_dir = html_dir

    def _resolve(self, content_dir: str, file_name: str) -> str:
        if not file_name:
            return ""
        for cand in [path_join(content_dir, "material", file_name), path_join(content_dir, file_name)]:
            if isfile(cand):
                return cand
        return ""

    def img(self, content_dir: str, file_name: str, alt: str = "") -> str:
        path = self._resolve(content_dir, file_name)
        if not path:
            return ""
        data = _img_base64(path)
        if not data:
            return ""
        return f'<img class="inline-img" src="{data}" alt="{_esc(alt)}" loading="lazy">'

    def audio(self, content_dir: str, file_name: str) -> str:
        path = self._resolve(content_dir, file_name)
        if not path:
            return ""
        data = _audio_base64(path)
        if not data:
            return ""
        return f'<audio class="audio" controls preload="none" src="{data}"></audio>'

    def transcript(self, text: str) -> str:
        lines = []
        for spk, txt in _split_transcript(text):
            cls = "w" if spk == "W" else "m"
            lines.append(
                f'<div class="utt"><span class="spk {cls}">{spk}</span>'
                f'<span class="utt-text">{_esc(txt)}</span></div>')
        return '<div class="utt-list">' + "".join(lines) + "</div>"

    def answer_list(self, answers, keywords=()) -> str:
        items = "".join(
            f'<li class="ans-item"><span class="ans-num">{i}</span>'
            f'<span class="ans-text">{_highlight_keywords(_esc(a), keywords)}</span></li>'
            for i, a in enumerate(answers, 1)
        )
        return f'<ol class="ans-list">{items}</ol>'

    def check(self, key: str) -> str:
        return (f'<button type="button" class="check-toggle" data-checkkey="{_esc(key)}" '
                f'title="标记为已核对" aria-label="标记为已核对">○</button>')

    def render_block(self, data, content_dir: str, block_key: str) -> str:
        structure_type = data.get("structure_type", "")
        handler = getattr(self, "_render_" + structure_type.split(".")[-1], None)
        if handler:
            return handler(data, content_dir, block_key)
        return f'<pre class="raw-json">{_esc(json.dumps(data, indent=2, ensure_ascii=False))}</pre>'

    # ---------- 各题型 ----------

    def _render_choose(self, data, content_dir, block_key):
        info = data.get("info", {}) or {}
        xtlist = info.get("xtlist", [])
        st_nr = clean_html_tags(info.get("st_nr", ""))
        fallback_audio = info.get("audio", "")
        parts = []

        if st_nr:
            parts.append(
                '<div class="transcript">'
                '<div class="transcript-head" tabindex="0" role="button" '
                'onclick="this.parentElement.classList.toggle(\'open\')">'
                '<span class="th-title">🎧 听力原文</span>'
                '<span class="th-arrow">▾</span></div>'
                '<div class="transcript-body">' + self.transcript(st_nr) + "</div></div>")

        badges = " ".join(
            f'<span class="ans-badge" data-answer>{i}·{xt.get("answer", "?")}</span>'
            for i, xt in enumerate(xtlist, 1)
        )
        if badges:
            parts.append(f'<div class="badge-row">{badges}</div>')

        for i, xt in enumerate(xtlist, 1):
            answer = xt.get("answer", "")
            value = clean_html_tags(xt.get("xt_value", ""))
            xt_audio = xt.get("xt_wj", "") or (fallback_audio if len(xtlist) == 1 else "")
            parts.append(
                f'<div class="question" data-checkkey="{_esc(block_key)}-q{i}">'
                f'<div class="q-head"><span class="q-num">{i}</span>'
                f'<div class="q-main">'
                f'<p class="searchable q-text">{_esc(value) if value else _esc(xt.get("xt_nr", ""))}</p>'
                f'{self.audio(content_dir, xt_audio) if xt_audio else ""}'
                f'</div>{self.check(block_key + f"-q{i}")}</div>'
                f'<div class="opts">{self._render_options(xt.get("xxlist", []), answer, content_dir)}</div>'
                f'</div>')
        return "".join(parts)

    def _render_options(self, xxlist, answer, content_dir):
        out = []
        for opt in xxlist:
            mc = opt.get("xx_mc", "")
            nr = clean_html_tags(opt.get("xx_nr", ""))
            wj = opt.get("xx_wj", "")
            is_correct = bool(answer) and mc == answer
            cls = "opt correct" if is_correct else "opt"
            content = ""
            if wj:
                img = self.img(content_dir, wj, alt=f"选项{mc}")
                content += f'<span class="opt-img">{img}</span>' if img else f'<span class="opt-img-name">{_esc(wj)}</span>'
            if nr:
                content += f'<span class="searchable">{_esc(nr)}</span>'
            mark = '<span class="opt-check">✓</span>' if is_correct else ""
            out.append(
                f'<div class="{cls}"><span class="opt-letter">{_esc(mc)}</span>'
                f'<span class="opt-content">{content}</span>{mark}</div>')
        return "".join(out)

    def _render_role(self, data, content_dir, block_key):
        info = data.get("info", {}) or {}
        dialog = clean_html_tags(info.get("value", ""))
        questions = info.get("question", [])
        parts = []
        if dialog:
            parts.append(
                '<div class="sub-block"><div class="sec-label">对话内容</div>'
                f'<p class="pre-line searchable">{_esc(dialog)}</p></div>')

        for i, q in enumerate(questions, 1):
            ask = clean_html_tags(q.get("ask", ""))
            ask = re.sub(r"ets_th\d+\s*", "", ask)
            ask = re.sub(r"^\s*\d+\s*[.、．]\s*", "", ask).strip()
            keywords = [k.strip() for k in re.split(r"[|｜]", q.get("keywords", "")) if k.strip()]
            std = [clean_html_tags(s.get("value", "")) for s in q.get("std", []) if s.get("value")]
            head = f'<span class="q-num">{i}</span>'
            askimg = self.img(content_dir, q.get("askimg", ""), alt=f"第{i}题图片")
            askaudio = self.audio(content_dir, q.get("askaudio", ""))
            kw = "".join(f'<span class="badge kw">{_esc(k)}</span>' for k in keywords)
            subj = (
                f'<div class="question subjective" data-checkkey="{_esc(block_key)}-q{i}">'
                f'<div class="q-head"><div class="q-main">'
                f'{head}<div class="subj-title">'
                f'<p class="searchable q-text">{_esc(ask) if ask else "(题干未导出)"}</p>'
                f'{askimg}{askaudio}'
                f'</div></div>{self.check(block_key + f"-q{i}")}</div>'
                f'<div class="meta-row">{kw}</div>'
                f'{self.answer_list(std, keywords)}'
                f'</div>')
            parts.append(subj)
        return "".join(parts)

    def _render_picture(self, data, content_dir, block_key):
        info = data.get("info", {}) or {}
        topic = info.get("topic", "")
        image = info.get("image", "")
        value = clean_html_tags(info.get("value", ""))
        keypoint = clean_html_tags(info.get("keypoint", ""))
        std = [clean_html_tags(s.get("value", "")) for s in info.get("std", []) if s.get("value")]
        audio = info.get("audio", "")
        parts = []
        if topic:
            parts.append(f'<div class="sub-block"><div class="sec-label">主题</div>'
                         f'<p class="q-text searchable">{_esc(topic)}</p></div>')
        if image:
            parts.append(f'<div class="sub-block">{self.img(content_dir, image, alt="图片")}</div>')
        if value:
            parts.append(f'<div class="sub-block"><div class="sec-label">内容描述</div>'
                         f'<p class="pre-line searchable">{_esc(value)}</p></div>')
        if keypoint:
            parts.append(f'<div class="sub-block"><div class="sec-label">核心要点</div>'
                         f'<p class="pre-line searchable">{_esc(keypoint)}</p></div>')
        parts.append(self.audio(content_dir, audio))
        parts.append(
            f'<div class="question subjective" data-checkkey="{_esc(block_key)}-q1">'
            f'<div class="q-head"><div class="q-main"><span class="q-num">1</span>'
            f'<div class="subj-title"><p class="q-text">参考答案</p></div></div>'
            f'{self.check(block_key + "-q1")}</div>'
            f'{self.answer_list(std)}</div>')
        return "".join(parts)

    def _render_read(self, data, content_dir, block_key=""):
        info = data.get("info", {}) or {}
        value = clean_html_tags(info.get("value", ""))
        audio = info.get("audio", "")
        return (f'<div class="sub-block"><div class="sec-label">阅读材料</div>'
                f'<p class="pre-line searchable">{_esc(value)}</p>'
                f'{self.audio(content_dir, audio)}</div>')

    def _render_repeat_essay(self, data, content_dir, block_key=""):
        info = data.get("info", {}) or {}
        value = clean_html_tags(info.get("value", ""))
        audio = info.get("audio", "")
        sublist = info.get("sublist", [])
        parts = [
            f'<div class="sub-block"><div class="sec-label">短文</div>'
            f'<p class="pre-line searchable">{_esc(value)}</p>{self.audio(content_dir, audio)}</div>']
        if sublist:
            rows = []
            for item in sublist:
                if "text" in item:
                    text = clean_html_tags(item.get("text", ""))
                    trans = clean_html_tags(item.get("translate", ""))
                    rows.append(
                        f'<div class="trans-row"><span class="trans-text searchable">{_esc(text)}</span>'
                        + (f'<span class="trans-tr">→ {_esc(trans)}</span>' if trans else "") + "</div>")
            parts.append('<div class="sub-block"><div class="sec-label">逐句对照</div>'
                         + "".join(rows) + "</div>")
        return "".join(parts)

    def _render_repeat_dialogue(self, data, content_dir, block_key=""):
        info = data.get("info", {}) or {}
        value = clean_html_tags(info.get("value", ""))
        audio = info.get("audio", "")
        sublist = info.get("sublist", [])
        parts = [
            f'<div class="sub-block"><div class="sec-label">对话内容</div>'
            f'<p class="pre-line searchable">{_esc(value)}</p>{self.audio(content_dir, audio)}</div>']
        if sublist:
            rows = []
            for item in sublist:
                if "role" in item and "text" in item:
                    role = item.get("role", "")
                    text = clean_html_tags(item.get("text", ""))
                    trans = clean_html_tags(item.get("translate", ""))
                    cls = "w" if role.upper() == "W" else "m"
                    rows.append(
                        f'<div class="utt"><span class="spk {cls}">{_esc(role)}</span>'
                        f'<span class="utt-text searchable">{_esc(text)}</span></div>'
                        + (f'<div class="utt-tr">→ {_esc(trans)}</div>' if trans else ""))
            parts.append('<div class="sub-block"><div class="sec-label">逐句对照</div>'
                         + "".join(rows) + "</div>")
        return "".join(parts)

    def _render_word(self, data, content_dir, block_key):
        info = data.get("info", {}) or {}
        value = clean_html_tags(info.get("value", ""))
        translate = clean_html_tags(info.get("translate", ""))
        audio = info.get("audio", "")
        parts = []
        if value:
            parts.append(f'<div class="sub-block"><div class="sec-label">原文</div>'
                         f'<p class="pre-line searchable">{_esc(value)}</p></div>')
        if translate:
            parts.append(f'<div class="sub-block"><div class="sec-label">参考翻译</div>'
                         f'<p class="pre-line searchable">{_esc(translate)}</p></div>')
        parts.append(self.audio(content_dir, audio))
        parts.append(
            f'<div class="question subjective" data-checkkey="{_esc(block_key)}-q1">'
            f'<div class="q-head"><div class="q-main"><span class="q-num">1</span>'
            f'<div class="subj-title"><p class="q-text">参考答案</p></div></div>'
            f'{self.check(block_key + "-q1")}</div></div>')
        return "".join(parts)


def _compute_stats(contents):
    choice_sections = 0
    choice_questions = 0
    subjective_questions = 0
    answers = 0
    for data in contents:
        st = data.get("structure_type", "")
        info = data.get("info", {}) or {}
        if st == "collector.choose":
            choice_sections += 1
            choice_questions += len(info.get("xtlist", []))
        elif st == "collector.role":
            questions = info.get("question", [])
            subjective_questions += len(questions)
            answers += sum(len(q.get("std", [])) for q in questions)
        elif st == "collector.picture":
            subjective_questions += 1
            answers += len(info.get("std", []))
        elif st == "collector.word":
            subjective_questions += 1
    return choice_sections, choice_questions, subjective_questions, answers


# ---------------------------------------------------------------------------
# 内嵌 CSS / JS
# ---------------------------------------------------------------------------

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f6fbf8;--card:#fff;--fg:#15352b;--muted:#f0f7f3;--muted-fg:#5c7568;
  --primary:#0f9d6b;--primary-fg:#fff;--border:#dfeae3;--amber:#b45309;
  --amber-bg:#fef3c7;--emerald-bg:#d1fae5;--emerald-bd:#a7f3d0;
  --rose:#f43f5e;--teal:#0d9488;--shadow:0 1px 3px rgba(21,53,43,.08);
}
html.dark{
  --bg:#0f1a15;--card:#16231d;--fg:#e6f2ec;--muted:#1d2d25;--muted-fg:#9db8ab;
  --border:#2a4035;--amber:#fbbf24;--amber-bg:#4a330f;--emerald-bg:#0b3d2a;
  --emerald-bd:#155e40;--rose:#fb7185;--teal:#2dd4bf;--shadow:0 1px 3px rgba(0,0,0,.4);
}
body{background:var(--bg);color:var(--fg);font-family:ui-sans-serif,system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}
.wrap{max-width:56rem;margin:0 auto;padding:0 1rem 3rem}
.topbar{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:.5rem;padding:.75rem 0;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);margin-bottom:1.25rem}
.logo{display:flex;align-items:center;gap:.6rem;min-width:0;flex:1}
.logo-icon{width:2.1rem;height:2.1rem;border-radius:.6rem;background:linear-gradient(135deg,#10b981,#0d9488);color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.05rem;flex-shrink:0}
.logo h1{font-size:1rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.logo p{font-size:.7rem;color:var(--muted-fg)}
.icon-btn{border:1px solid var(--border);background:var(--card);border-radius:.5rem;width:2.25rem;height:2.25rem;cursor:pointer;color:var(--fg);font-size:1rem;flex-shrink:0}
.icon-btn:hover{background:var(--muted)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin-bottom:1rem}
.stat{border:1px solid var(--border);background:var(--card);border-radius:.65rem;padding:.55rem .7rem}
.stat b{display:block;font-size:.95rem}
.stat span{font-size:.68rem;color:var(--muted-fg)}
.controls{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin-bottom:1rem}
.search{flex:1;min-width:10rem;display:flex;align-items:center;gap:.4rem;border:1px solid var(--border);background:var(--card);border-radius:.5rem;padding:.4rem .6rem}
.search input{border:0;outline:0;background:transparent;color:var(--fg);font:inherit;width:100%}
.switch{display:flex;align-items:center;gap:.35rem;font-size:.75rem;color:var(--muted-fg);cursor:pointer;user-select:none}
.switch input{accent-color:var(--primary)}
.block{border:1px solid var(--border);background:var(--card);border-radius:.8rem;box-shadow:var(--shadow);padding:1.1rem 1.15rem;margin-bottom:1rem}
.block-head{display:flex;align-items:center;gap:.7rem;margin-bottom:.9rem}
.block-idx{width:2.25rem;height:2.25rem;border-radius:.55rem;background:var(--emerald-bg);color:var(--primary);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.9rem}
.block-head h2{font-size:1rem}
.block-sub{font-size:.72rem;color:var(--muted-fg)}
.badge-row{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.9rem}
.ans-badge{border:1px solid var(--emerald-bd);background:var(--emerald-bg);color:var(--primary);font-size:.72rem;font-weight:700;border-radius:.45rem;padding:.1rem .5rem;font-variant-numeric:tabular-nums}
.transcript{border:1px solid var(--emerald-bd);background:color-mix(in srgb,var(--emerald-bg) 55%,transparent);border-radius:.65rem;margin-bottom:.9rem;overflow:hidden}
.transcript-head{display:flex;justify-content:space-between;align-items:center;padding:.55rem .8rem;cursor:pointer;font-size:.78rem;font-weight:600;color:var(--primary)}
.transcript-head:hover{background:color-mix(in srgb,var(--emerald-bg) 80%,transparent)}
.transcript-body{max-height:0;overflow:hidden;transition:max-height .25s ease}
.transcript.open .transcript-body{max-height:30rem;overflow-y:auto}
.transcript.open .th-arrow{transform:rotate(180deg)}
.transcript-body{padding:0 .8rem}
.transcript.open .transcript-body{padding:0 .8rem .7rem}
.th-arrow{transition:transform .2s}
.utt{display:flex;gap:.5rem;align-items:flex-start;margin-top:.45rem}
.spk{width:1.35rem;height:1.35rem;border-radius:50%;color:#fff;font-size:.6rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:.15rem}
.spk.w{background:var(--rose)}
.spk.m{background:var(--teal)}
.utt-text{font-size:.82rem}
.utt-tr{font-size:.75rem;color:var(--muted-fg);margin:.1rem 0 .2rem 1.85rem}
.question{border:1px solid var(--border);border-radius:.65rem;padding:.8rem;margin-top:.6rem}
.q-head{display:flex;align-items:flex-start;gap:.55rem;margin-bottom:.5rem}
.q-main{flex:1;display:flex;align-items:flex-start;gap:.55rem;min-width:0}
.q-num{width:1.5rem;height:1.5rem;border-radius:50%;background:color-mix(in srgb,var(--primary) 12%,transparent);color:var(--primary);font-size:.72rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:.1rem}
.q-text{font-size:.9rem;font-weight:500}
.subj-title{min-width:0;flex:1}
.meta-row{display:flex;flex-wrap:wrap;gap:.35rem;margin:.4rem 0}
.badge{font-size:.68rem;font-weight:600;border-radius:.45rem;padding:.12rem .55rem;border:1px solid}
.badge.kw{color:var(--amber);background:var(--amber-bg);border-color:color-mix(in srgb,var(--amber) 45%,transparent)}
.sec-label{font-size:.72rem;font-weight:600;color:var(--muted-fg);margin-bottom:.35rem}
.sub-block{margin-bottom:.9rem}
.pre-line{white-space:pre-line;font-size:.85rem}
.raw-json{font-family:ui-monospace,Consolas,monospace;font-size:.75rem;white-space:pre-wrap;overflow-x:auto}
.opts{display:flex;flex-direction:column;gap:.4rem;margin-left:2.05rem}
.opt{display:flex;align-items:center;gap:.6rem;border-radius:.5rem;padding:.45rem .7rem;font-size:.85rem;border:1px solid transparent;background:var(--muted)}
.opt-letter{width:1.25rem;height:1.25rem;border-radius:.35rem;border:1px solid var(--border);background:var(--card);color:var(--muted-fg);font-size:.65rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.opt.correct{border-color:var(--emerald-bd);background:var(--emerald-bg)}
.opt.correct .opt-letter{background:var(--primary);color:#fff;border-color:var(--primary)}
.opt.correct .opt-content{color:var(--primary);font-weight:600}
.opt-check{color:var(--primary);font-weight:700;margin-left:auto;flex-shrink:0}
.opt-img img{max-width:9rem;max-height:7rem;border-radius:.4rem;display:block}
.opt-img-name{font-size:.7rem;color:var(--muted-fg)}
.ans-list{list-style:none;max-height:26rem;overflow-y:auto}
.ans-item{display:flex;gap:.55rem;padding:.35rem .5rem;border-radius:.45rem;font-size:.85rem}
.ans-item:nth-child(odd){background:var(--muted)}
.ans-num{width:1.4rem;text-align:right;flex-shrink:0;color:var(--muted-fg);font-size:.72rem;font-weight:600;padding-top:.1rem;font-variant-numeric:tabular-nums}
.ans-item.hidden{display:none}
.expand-btn{margin-top:.5rem;border:1px solid var(--border);background:var(--card);color:var(--fg);border-radius:.5rem;padding:.35rem .8rem;font-size:.75rem;cursor:pointer}
.expand-btn:hover{background:var(--muted)}
.check-toggle{width:2rem;height:2rem;border-radius:50%;border:0;background:transparent;color:var(--muted-fg);font-size:1rem;cursor:pointer;flex-shrink:0;opacity:.55}
.check-toggle:hover{background:var(--muted);opacity:1}
.check-toggle.on{background:var(--primary);color:#fff;opacity:1;box-shadow:0 1px 3px rgba(15,157,107,.4)}
.audio{width:100%;max-width:20rem;height:1.9rem;margin-top:.45rem}
mark.kw-mark{background:var(--amber-bg);color:var(--amber);border-radius:.2rem;padding:0 .15rem}
mark.search-hit{background:#6ee7b7;color:#064e3b;border-radius:.2rem;padding:0 .15rem}
html.dark mark.search-hit{background:#10b981;color:#052e1f}
.progress-row{display:flex;align-items:center;gap:.6rem;margin-bottom:1rem}
.progress-bar{flex:1;height:.4rem;background:var(--muted);border-radius:999px;overflow:hidden}
.progress-fill{height:100%;width:0;background:var(--primary);border-radius:999px;transition:width .2s}
.progress-text{font-size:.72rem;color:var(--muted-fg);white-space:nowrap}
body.hide-answers .ans-badge{display:none}
body.hide-answers .opt.correct{border-color:transparent;background:var(--muted)}
body.hide-answers .opt.correct .opt-letter{background:var(--card);color:var(--muted-fg);border-color:var(--border)}
body.hide-answers .opt.correct .opt-content{color:var(--fg);font-weight:400}
body.hide-answers .opt-check{display:none}
.foot{margin-top:1.5rem;text-align:center;font-size:.72rem;color:var(--muted-fg)}
@media(max-width:560px){.stats{grid-template-columns:repeat(2,1fr)}.block{padding:.9rem}.opts{margin-left:0}}
"""

JS = """
(function () {
  var ROOT = __ROOT_NAME__;

  /* ---------- 主题 ---------- */
  function applyTheme(dark) {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('etsviewer-theme', dark ? 'dark' : 'light');
  }
  var savedTheme = localStorage.getItem('etsviewer-theme');
  if (savedTheme) applyTheme(savedTheme === 'dark');
  else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) applyTheme(true);
  var themeBtn = document.getElementById('theme-btn');
  if (themeBtn) themeBtn.onclick = function () {
    applyTheme(!document.documentElement.classList.contains('dark'));
  };

  /* ---------- 显示答案 ---------- */
  function applyAnswers(show) {
    document.body.classList.toggle('hide-answers', !show);
    localStorage.setItem('etsviewer-answers', show ? '1' : '0');
  }
  var savedAnswers = localStorage.getItem('etsviewer-answers');
  applyAnswers(savedAnswers === null ? true : savedAnswers !== '0');
  var ansToggle = document.getElementById('ans-toggle');
  if (ansToggle) {
    ansToggle.checked = !document.body.classList.contains('hide-answers');
    ansToggle.onchange = function () { applyAnswers(ansToggle.checked); };
  }

  /* ---------- 核对勾选 ---------- */
  var CHECK_KEY = 'etsviewer-checked:' + ROOT;
  var checked = {};
  try { checked = JSON.parse(localStorage.getItem(CHECK_KEY) || '{}'); } catch (e) {}
  function renderChecks() {
    var toggles = document.querySelectorAll('.check-toggle');
    var total = toggles.length, done = 0;
    toggles.forEach(function (el) {
      var k = el.getAttribute('data-checkkey');
      var on = !!checked[k];
      el.classList.toggle('on', on);
      el.textContent = on ? '✓' : '○';
      if (on) done++;
    });
    var fill = document.getElementById('progress-fill');
    var txt = document.getElementById('progress-text');
    if (fill) fill.style.width = total ? (done / total * 100) + '%' : '0%';
    if (txt) txt.textContent = '已核对 ' + done + '/' + total;
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.check-toggle');
    if (!btn) return;
    var k = btn.getAttribute('data-checkkey');
    checked[k] = !checked[k];
    try { localStorage.setItem(CHECK_KEY, JSON.stringify(checked)); } catch (err) {}
    renderChecks();
  });
  renderChecks();

  /* ---------- 答案折叠 ---------- */
  document.querySelectorAll('.ans-list').forEach(function (ol) {
    var items = ol.querySelectorAll('li');
    if (items.length <= 8) return;
    for (var i = 8; i < items.length; i++) items[i].classList.add('hidden');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'expand-btn';
    btn.textContent = '展开全部 ' + items.length + ' 条 ▾';
    btn.onclick = function () {
      items.forEach(function (li) { li.classList.remove('hidden'); });
      btn.remove();
    };
    ol.insertAdjacentElement('afterend', btn);
  });

  /* ---------- 搜索 ---------- */
  function escapeReg(s) { return s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'); }
  function clearHits() {
    document.querySelectorAll('mark.search-hit').forEach(function (m) {
      m.replaceWith(document.createTextNode(m.textContent));
    });
  }
  function highlightIn(node, re) {
    var walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    var targets = [];
    while (walker.nextNode()) targets.push(walker.currentNode);
    targets.forEach(function (t) {
      if (!t.nodeValue) return;
      if (t.parentNode && t.parentNode.tagName === 'MARK') return;
      var html = t.nodeValue.replace(re, function (m) {
        return '<mark class="search-hit">' + m + '</mark>';
      });
      if (html !== t.nodeValue) {
        var span = document.createElement('span');
        span.innerHTML = html;
        t.replaceWith(span);
      }
    });
  }
  function applySearch() {
    var input = document.getElementById('search-input');
    var q = (input ? input.value : '').trim().toLowerCase();
    clearHits();
    var blocks = document.querySelectorAll('.block');
    var hit = 0;
    blocks.forEach(function (b) {
      var found = q === '';
      var areas = b.querySelectorAll('.searchable');
      if (!found) {
        areas.forEach(function (a) {
          if (a.textContent.toLowerCase().indexOf(q) !== -1) found = true;
        });
        if (found) {
          var re = new RegExp(escapeReg(q), 'gi');
          areas.forEach(function (a) { highlightIn(a, re); });
        }
      }
      b.style.display = found ? '' : 'none';
      if (found) hit++;
    });
    var hint = document.getElementById('search-hint');
    if (hint) {
      hint.textContent = q
        ? ('搜索 “' + q + '” · 命中 ' + hit + '/' + blocks.length + ' 个区块')
        : '';
    }
  }
  var searchInput = document.getElementById('search-input');
  if (searchInput) searchInput.addEventListener('input', applySearch);
})();
"""


def build_html_doc(contents, names, dirs, html_dir, root_name=""):
    """生成整卷单文件 HTML，返回 HTML 字符串"""
    renderer = _Renderer(html_dir)
    choice_sections, choice_questions, subjective_questions, answers = _compute_stats(contents)

    blocks = []
    for idx, (content, name, content_dir) in enumerate(zip(contents, names, dirs), 1):
        st = content.get("structure_type", "")
        type_name = _specific_type_name(content)
        block_key = f"{root_name}-{name}" if root_name else name
        body = renderer.render_block(content, content_dir, block_key)
        blocks.append(
            f'<section class="block">'
            f'<header class="block-head"><span class="block-idx">{idx}</span>'
            f'<div><h2>{_esc(type_name)}</h2><p class="block-sub">{_esc(name)}</p></div></header>'
            f'{body}</section>')

    css = CSS
    js = JS.replace("__ROOT_NAME__", json.dumps(root_name, ensure_ascii=False))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(root_name or "ETS")} · 答案校对</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <header class="topbar">
    <div class="logo">
      <span class="logo-icon">✓</span>
      <div>
        <h1>{_esc(root_name or "ETS")} · 答案校对</h1>
        <p>听力选择 + 主观题参考答案 · 一页速览</p>
      </div>
    </div>
    <button type="button" class="icon-btn" id="theme-btn" title="切换深浅色">🌙</button>
  </header>

  <div class="stats">
    <div class="stat"><b>{choice_sections}</b><span>听力选择组</span></div>
    <div class="stat"><b>{choice_questions}</b><span>选择小题</span></div>
    <div class="stat"><b>{subjective_questions}</b><span>主观题</span></div>
    <div class="stat"><b>{answers}</b><span>参考答案</span></div>
  </div>

  <div class="controls">
    <div class="search"><span>🔍</span><input id="search-input" type="search" placeholder="搜索题干、选项、关键词或答案…"></div>
    <label class="switch"><input id="ans-toggle" type="checkbox" checked> 显示答案</label>
  </div>
  <p id="search-hint" class="search-hint" style="font-size:.75rem;color:var(--muted-fg);margin-bottom:.6rem"></p>

  <div class="progress-row">
    <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
    <span class="progress-text" id="progress-text">已核对 0/0</span>
  </div>

  {''.join(blocks)}

  <footer class="foot">由 EtsViewer 导出 · 核对进度保存在本地浏览器</footer>
</div>
<script>{js}</script>
</body>
</html>
"""
