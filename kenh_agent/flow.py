"""Phiếu Flow: agent viết prompt, chủ kênh tạo clip trong Google Flow rồi thả file vào thư mục.

    python -m kenh_agent flow phieu <phieu.json>   -> tạo PHIEU-FLOW.html (nút chép prompt) + thư mục nhan/
    python -m kenh_agent flow check <phieu.json>   -> kiểm tra file chủ kênh đã thả vào, báo thiếu/lỗi

Mẫu phieu.json (mọi "file" tính từ thư mục chứa phieu.json):
{
  "series": "Tên series", "tap": "Tập 2", "tieu_de": "...", "ti_le": "9:16",
  "mo_hinh": "Veo 3.1 - Fast", "credit_moi_clip": 20,
  "ghi_chu": "Lời dặn chung cho chủ kênh",
  "nguyen_lieu": [{"id": "nv-a", "ten": "Nhân vật A", "loai": "anh", "mo_ta_vi": "...",
                   "prompt": "...", "file": "../nhan-vat/nv-a.png"}],
  "canh": [{"so": 1, "loai": "video", "che_do": "Ingredients to Video", "nguyen_lieu": ["nv-a"],
            "mo_ta_vi": "...", "prompt": "...", "file": "nhan/c01.mp4", "luot_thu_toi_da": 2}]
}
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _load(path: str | Path) -> tuple[dict, Path]:
    p = Path(path).resolve()
    return json.loads(p.read_text(encoding="utf-8")), p.parent


def _find(base: Path, rel: str) -> Path | None:
    """Tìm file đúng tên; chấp nhận khác đuôi (vd .jpg thay .png) vì Flow có thể tải về định dạng khác."""
    target = (base / rel).resolve()
    if target.exists():
        return target
    if target.parent.exists():
        for f in target.parent.iterdir():
            if f.stem.lower() == target.stem.lower() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT:
                return f
    return None


def _credit(d: dict) -> int:
    per = int(d.get("credit_moi_clip", 20))
    return sum(per for c in d.get("canh", []) if c.get("loai") == "video")


def _probe(f: Path) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    r = subprocess.run([exe, "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", str(f)], capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def check(path: str | Path) -> dict:
    d, base = _load(path)
    want_ratio = d.get("ti_le", "9:16")
    out = {"tap": d.get("tap"), "du": [], "thieu": [], "loi": []}
    items = [("nguyen_lieu", n.get("id"), n) for n in d.get("nguyen_lieu", [])]
    items += [("canh", c.get("so"), c) for c in d.get("canh", [])]
    for kind, key, it in items:
        label = f"{'Nguyên liệu' if kind == 'nguyen_lieu' else 'Cảnh'} {key}: {it.get('file')}"
        f = _find(base, it["file"])
        if not f:
            out["thieu"].append(label)
            continue
        info = _probe(f)
        streams = info.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not v:
            out["loi"].append(f"{label} — không đọc được hình")
            continue
        w, h = v.get("width", 0), v.get("height", 0)
        if it.get("loai") == "video" and f.suffix.lower() not in VIDEO_EXT:
            out["loi"].append(f"{label} — cần file video nhưng nhận {f.name}")
            continue
        if kind == "canh" and w and h:
            doc = h > w
            if (want_ratio == "9:16") != doc:
                out["loi"].append(f"{label} — khung {w}x{h} không đúng tỉ lệ {want_ratio}")
                continue
        dur = float(info.get("format", {}).get("duration", 0) or 0)
        out["du"].append(f"{label} — {w}x{h}" + (f", {dur:.1f}s" if dur > 0.5 else "")
                         + (", có tiếng" if any(s.get("codec_type") == "audio" for s in streams) else ""))
    out["xong"] = not out["thieu"] and not out["loi"]
    out["tom_tat"] = (f"Đủ {len(out['du'])}/{len(items)} file"
                      + (f", thiếu {len(out['thieu'])}" if out["thieu"] else "")
                      + (f", lỗi {len(out['loi'])}" if out["loi"] else ""))
    return out


def _copy_text(it: dict) -> str:
    """Flow mới là ô chat: mở đầu bằng câu lệnh rõ ràng để trợ lý của Flow biết tạo ảnh hay video."""
    head = "Create a video: " if it.get("loai") == "video" else "Create an image: "
    if it.get("flow_nhan_vat"):
        head = head.rstrip(": ") + " featuring my project characters " + ", ".join(it["flow_nhan_vat"])             + " (use their character references for face and costume): "
    elif it.get("nguyen_lieu"):
        head += "Use the attached reference image(s) for the character's face and costume. "
    return head + it["prompt"]


def _card(n: int, it: dict, kind: str, base: Path, names: dict) -> str:
    e = html.escape
    done = _find(base, it["file"]) is not None
    loai = "VIDEO" if it.get("loai") == "video" else "ẢNH"
    title = it.get("ten") or f"Cảnh {it.get('so', n)}"
    fname = Path(it["file"]).name
    ing = ""
    if it.get("nguyen_lieu"):
        ing = "<p class=ing>Thêm nguyên liệu: " + ", ".join(e(names.get(i, i)) for i in it["nguyen_lieu"]) + "</p>"
    tries = f" · thử tối đa {it['luot_thu_toi_da']} lần" if it.get("luot_thu_toi_da") else ""
    return f"""
<section class="card{' done' if done else ''}" id="{e(kind)}-{n}">
  <div class=head><span class=num>{n}</span><b>{e(title)}</b>
    <span class="tag {'v' if loai == 'VIDEO' else 'a'}">{loai}</span>
    <span class=mode>{e(it.get('che_do', ''))}{e(tries)}</span>
    {'<span class=ok>✓ đã có file</span>' if done else ''}</div>
  <p class=vi>{e(it.get('mo_ta_vi', ''))}</p>{ing}
  <pre>{e(_copy_text(it))}</pre>
  <div class=row><button onclick="cp(this)" data-t="{e(_copy_text(it))}">Chép prompt</button>
    <span>Lưu thành: <code>{e(fname)}</code></span>
    <button class=sec onclick="cp(this)" data-t="{e(Path(fname).stem)}">Chép tên file</button></div>
</section>"""


def phieu(path: str | Path) -> Path:
    d, base = _load(path)
    names = {n["id"]: n.get("ten", n["id"]) for n in d.get("nguyen_lieu", [])}
    for it in d.get("nguyen_lieu", []) + d.get("canh", []):
        (base / it["file"]).resolve().parent.mkdir(parents=True, exist_ok=True)
    nl = d.get("nguyen_lieu", [])
    cards_nl = "".join(_card(i + 1, it, "nl", base, names) for i, it in enumerate(nl))
    cards_c = "".join(_card(int(c.get("so", i + 1)), c, "c", base, names) for i, c in enumerate(d.get("canh", [])))
    nhan = (base / "nhan").resolve()
    e = html.escape
    so_video = sum(1 for c in d.get("canh", []) if c.get("loai") == "video")
    so_anh = len(d.get("canh", [])) - so_video
    page = f"""<!doctype html><html lang=vi><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Phiếu Flow — {e(d.get('tap', ''))}</title>
<style>
:root{{--bg:#f6f4ef;--fg:#1d1d1b;--card:#fff;--mut:#6b6860;--line:#e2ded4;--acc:#2f5bd3;--ok:#1d8a4a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141413;--fg:#eceae4;--card:#1f1f1d;--mut:#a29f96;--line:#34332f;--acc:#7b9cff;--ok:#4cc07f}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,'Segoe UI',sans-serif}}
main{{max-width:860px;margin:0 auto;padding:24px 16px 80px}}
h1{{font-size:24px;margin:0 0 4px}} h2{{margin:32px 0 8px;font-size:19px}}
.sub{{color:var(--mut);margin:0 0 16px}}
.steps{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 20px}}
.steps li{{margin:4px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}}
.card.done{{border-color:var(--ok);opacity:.7}}
.head{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
.num{{background:var(--fg);color:var(--bg);border-radius:99px;min-width:26px;height:26px;display:inline-grid;place-items:center;font-size:13px}}
.tag{{font-size:12px;padding:2px 8px;border-radius:6px;font-weight:600}}
.tag.v{{background:#e8eeff;color:#2a4bb0}} .tag.a{{background:#eef6e9;color:#3b6b25}}
.mode{{color:var(--mut);font-size:14px}} .ok{{color:var(--ok);font-weight:600;font-size:14px}}
.vi{{margin:8px 0 4px}} .ing{{margin:0 0 6px;color:var(--acc);font-size:14px}}
pre{{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:13.5px;max-height:220px;overflow:auto}}
.row{{display:flex;flex-wrap:wrap;gap:10px;align-items:center}}
button{{font:inherit;border:0;border-radius:8px;padding:8px 14px;background:var(--acc);color:#fff;cursor:pointer}}
button.sec{{background:transparent;color:var(--acc);border:1px solid var(--acc);padding:6px 10px;font-size:14px}}
code{{background:var(--bg);padding:1px 6px;border-radius:4px}}
</style></head><body><main>
<h1>Phiếu Flow — {e(d.get('series', ''))} · {e(d.get('tap', ''))}</h1>
<p class=sub>{e(d.get('tieu_de', ''))}<br>{so_video} clip video + {so_anh} ảnh · khung {e(d.get('ti_le', '9:16'))} ·
mô hình {e(d.get('mo_hinh', 'Omni 1.2 Flash'))} · ước tính ~{_credit(d)} credit</p>
<ol class=steps>
<li>Mở <b>labs.google/flow</b>, vào dự án của series. Lần đầu: bấm biểu tượng bánh răng của ô chat (Cài đặt tác nhân) → chế độ ảnh và video đều chọn khung <b>{e(d.get('ti_le', '9:16'))}</b>; video mô hình <b>{e(d.get('mo_hinh', 'Omni 1.2 Flash'))}</b>, 1 kết quả.</li>
<li>Làm lần lượt từ trên xuống: bấm <b>Chép prompt</b> → dán vào ô chat "Bạn muốn tạo gì?" bên phải → bấm mũi tên. Thẻ có "Thêm nguyên liệu": trước khi gửi, bấm dấu <b>+</b> trong ô chat và chọn ảnh mẫu nhân vật ghi trên thẻ.</li>
<li>Bấm vào bản ưng ý → nút <b>Tải về</b> (mũi tên xuống) → chọn <b>2K</b>. Đổi tên đúng như thẻ ghi (đuôi .jpg hay .png đều được), bỏ vào thư mục:<br><code>{e(str(nhan))}</code><br>
(nguyên liệu nhân vật thì bỏ theo đường dẫn ghi trên thẻ). Chưa ưng thì tạo lại, nhưng không quá số lần ghi trên thẻ.</li>
<li>Xong thì nói với Claude: <b>"đã làm xong phiếu Flow"</b>. Thẻ nào đã có file sẽ hiện ✓ khi mở lại trang này.</li>
</ol>
{f'<p>{e(d["ghi_chu"])}</p>' if d.get('ghi_chu') else ''}
{'<h2>Bước 1 — Nguyên liệu (ảnh nhân vật / bối cảnh, làm một lần cho cả series)</h2>' + cards_nl if nl else ''}
<h2>{'Bước 2 — ' if nl else ''}Các cảnh</h2>{cards_c}
</main><script>
function cp(b){{const t=b.dataset.t;const done=()=>{{const o=b.textContent;b.textContent='Đã chép ✓';setTimeout(()=>b.textContent=o,1400)}};
if(navigator.clipboard&&window.isSecureContext){{navigator.clipboard.writeText(t).then(done,()=>fb(t,done))}}else fb(t,done)}}
function fb(t,done){{const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();try{{document.execCommand('copy');done()}}catch(e){{}}a.remove()}}
</script></body></html>"""
    out = base / "PHIEU-FLOW.html"
    out.write_text(page, encoding="utf-8")
    return out
