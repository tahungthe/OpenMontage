"""Cắt video full thành các phần (tập) cho TikTok / Facebook Reels.

- Ưu tiên điểm cắt agent đưa vào (theo nhịp kịch bản: dừng ở cao trào để
  người xem phải tìm phần sau).
- Nếu không có, tự tìm điểm cắt ở chỗ lời thoại ngắt (khoảng lặng) gần độ dài
  mục tiêu nhất, để không cắt giữa câu.
- Xuất video dọc 1080x1920: video gốc ở giữa, nền mờ, tiêu đề phía trên và
  nhãn "Phần n/tổng" phía dưới.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("Không tìm thấy ffmpeg trên máy.")
    return exe


def probe(path: str | Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    out = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), {})
    return {
        "duration": float(data["format"].get("duration", 0)),
        "width": int(v.get("width", 0)),
        "height": int(v.get("height", 0)),
    }


def silence_points(path: str | Path, noise_db: int = -32, min_silence: float = 0.35) -> list[float]:
    """Trả về các mốc thời gian (giây) ở giữa những khoảng lặng."""
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", proc.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def scene_points(path: str | Path, threshold: float = 0.35) -> list[float]:
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-an",
         "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", proc.stderr)]


def plan_cuts(duration: float, candidates: list[float], target: float, min_len: float, max_len: float) -> list[tuple[float, float]]:
    """Chia đều thành n phần gần `target` giây; mỗi điểm cắt chọn khoảng lặng gần mốc lý tưởng nhất."""
    if duration <= max_len:
        return [(0.0, duration)]
    n = max(2, round(duration / target))
    ideal_len = duration / n
    candidates = sorted(c for c in candidates if 0 < c < duration)
    segments: list[tuple[float, float]] = []
    start = 0.0
    for k in range(1, n):
        ideal = k * ideal_len
        lo, hi = start + min_len, min(start + max_len, duration - min_len)
        window = [c for c in candidates if lo <= c <= hi]
        cut = min(window, key=lambda c: abs(c - ideal)) if window else min(max(ideal, lo), hi)
        segments.append((start, cut))
        start = cut
    segments.append((start, duration))
    return segments


def _esc(p: str | Path) -> str:
    """Escape đường dẫn cho bộ lọc ffmpeg (Windows có dấu ':')."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _font() -> str | None:
    return next((f for f in FONT_CANDIDATES if Path(f).exists()), None)


def render_part(src: Path, out: Path, start: float, end: float, title: str, label: str,
                vertical: bool = True) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    font = _font()
    title_file = out.with_suffix(".title.txt")
    label_file = out.with_suffix(".label.txt")
    title_file.write_text(title, encoding="utf-8")
    label_file.write_text(label, encoding="utf-8")

    if vertical:
        vf = (
            "[0:v]split=2[a][b];"
            "[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,eq=brightness=-0.12,scale=1080:1920[bg];"
            "[b]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        if font:
            ff = _esc(font)
            vf += (
                f",drawtext=fontfile='{ff}':textfile='{_esc(title_file)}':fontcolor=white:fontsize=58:"
                "line_spacing=6:borderw=4:bordercolor=black:x=(w-text_w)/2:y=230"
                f",drawtext=fontfile='{ff}':textfile='{_esc(label_file)}':fontcolor=yellow:fontsize=64:"
                "borderw=5:bordercolor=black:x=(w-text_w)/2:y=h-430"
            )
        vf += "[v]"
        maps = ["-filter_complex", vf, "-map", "[v]", "-map", "0:a?"]
    else:
        maps = ["-map", "0:v", "-map", "0:a?"]

    cmd = [
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src),
        *maps,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    title_file.unlink(missing_ok=True)
    label_file.unlink(missing_ok=True)


def wrap_title(title: str, width: int = 22) -> str:
    words, lines, cur = title.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:3])


def split_video(src: str | Path, out_dir: str | Path, title: str, cfg: dict[str, Any],
                cuts: list[dict] | None = None, vertical: bool = True) -> list[dict]:
    """Cắt `src` thành các phần. `cuts` = [{"start":..,"end":..,"hook":..}, ...] nếu agent tự chọn."""
    src, out_dir = Path(src), Path(out_dir)
    info = probe(src)
    duration = info["duration"]
    cp = cfg["cat_phan"]

    if cuts:
        segments = [(float(c["start"]), float(c["end"])) for c in cuts]
        hooks = [c.get("hook") for c in cuts]
    else:
        cands = silence_points(src) or scene_points(src)
        segments = plan_cuts(duration, cands, cp["do_dai_muc_tieu_giay"], cp["do_dai_toi_thieu_giay"], cp["do_dai_toi_da_giay"])
        hooks = [None] * len(segments)

    total = len(segments)
    parts = []
    for i, (s, e) in enumerate(segments, start=1):
        label = cp["phu_de_phan"].format(n=i, tong=total)
        out = out_dir / f"phan-{i:02d}.mp4"
        # Nguồn đã là video dọc (ví dụ tập phim ngắn 9:16): giữ nguyên khung, không chèn tiêu đề/nhãn đè lên.
        already_vertical = info.get("height", 0) > info.get("width", 0)
        render_part(src, out, s, e, wrap_title(title.split('|')[0].strip()), label,
                    vertical=vertical and not already_vertical)
        parts.append({"idx": i, "total": total, "path": str(out), "start_s": round(s, 2),
                      "end_s": round(e, 2), "hook": hooks[i - 1]})
    return parts
