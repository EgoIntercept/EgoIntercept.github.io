#!/usr/bin/env python3
"""Cover faces in the site's videos with black boxes.

    ./tools/face-mask.py status                 # every served clip + progress
    ./tools/face-mask.py annotate <video.mp4>   # draw / review boxes
    ./tools/face-mask.py render <video.mp4>     # bake boxes into the clip
    ./tools/face-mask.py render --all           # ...every annotated clip

Boxes are keyframed: draw one where a face is, step forward, move or resize
it where the face has drifted, and every frame in between is linearly
interpolated. A box holds its last keyframe until the next one, or until a
"hide" key (h) says the face has left the shot. Several faces = several
tracks (n starts a new one).

"Reviewed" means you actually looked at that frame with the boxes drawn --
single-stepping or playing, not jumping. Editing a keyframe un-reviews every
other frame whose box it moved, so the green bar on the timeline is always
an honest "I checked this". render refuses to bake a clip until every frame
is green (override with --allow-unreviewed).

Annotations live in tools/masks/<clip>.json (box coordinates only, safe to
commit). On first render the unmasked original is moved to media/unmasked/
(gitignored, never published) along with its poster; annotate and re-render
always read from there, so masks never stack and you can re-render freely.

Keys in the annotate window (also printed with ?):
  . d ->   next frame          , a <-   previous frame
  > D      +10 frames          < A      -10 frames
  ] [      next / prev keyframe of the current track
  space    play / pause        - =      slower / faster playback
  drag     inside a box: move     corner: resize
           empty area: redraw the current track's box here (n first for another face)
  click    timeline: seek
  k        keyframe the current (interpolated) box here
  x        delete this frame's keyframe          h   hide track from here
  n        new track (next box you draw)         t / tab   next track
  X        delete the current track entirely     u   undo
  m        toggle preview: see-through / solid black (what render writes)
  s        save                                  q / esc   save and quit
"""
import argparse
import bisect
import copy
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASKS = os.path.join(ROOT, "tools", "masks")
BACKUP = os.path.join(ROOT, "media", "unmasked")
CACHE = os.path.join(ROOT, "media", ".face-mask-cache")
POSTERS = "static/img/posters"

MAX_W, MAX_H = 1280, 760          # display frame area
TL_H = 34                         # timeline strip under the frame
HANDLE = 10                       # corner grab radius, display px
COLORS = [(0, 200, 255), (255, 120, 0), (80, 220, 80), (220, 80, 220),
          (0, 80, 255), (255, 255, 0)]


# ---------------------------------------------------------------- paths ----

def rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT)


def clip_key(relpath):
    """static/vids/sim/x.mp4 -> sim/x"""
    p = relpath[len("static/vids/"):] if relpath.startswith("static/vids/") else relpath
    return os.path.splitext(p)[0]


def mask_path(relpath):
    return os.path.join(MASKS, clip_key(relpath) + ".json")


def poster_rel(relpath):
    return os.path.join(POSTERS, os.path.splitext(os.path.basename(relpath))[0] + ".jpg")


def original(relpath):
    """The unmasked source: the backup if we've rendered before, else the served file."""
    b = os.path.join(BACKUP, relpath)
    return b if os.path.exists(b) else os.path.join(ROOT, relpath)


def site_videos():
    """Every clip index.html or main.js actually serves, in page order."""
    seen = []
    for f in ("index.html", "static/js/main.js"):
        with open(os.path.join(ROOT, f)) as fh:
            for m in re.finditer(r'static/vids/[\w./-]+?\.mp4', fh.read()):
                if m.group(0) not in seen:
                    seen.append(m.group(0))
    return seen


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate", "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"], s["r_frame_rate"]


# ---------------------------------------------------------------- model ----

class Track:
    def __init__(self, keys=None):
        # frame -> [x, y, w, h] in source pixels, or None for "hidden from here"
        self.keys = {int(k): v for k, v in (keys or {}).items()}
        self.order = sorted(self.keys)

    def set(self, f, box):
        if f not in self.keys:
            bisect.insort(self.order, f)
        self.keys[f] = box

    def delete(self, f):
        if f in self.keys:
            del self.keys[f]
            self.order.remove(f)

    def box_at(self, f):
        i = bisect.bisect_right(self.order, f) - 1
        if i < 0:
            return None
        k0 = self.order[i]
        b0 = self.keys[k0]
        if b0 is None or k0 == f or i + 1 == len(self.order):
            return b0
        k1 = self.order[i + 1]
        b1 = self.keys[k1]
        if b1 is None:
            return b0
        t = (f - k0) / (k1 - k0)
        return [a + (b - a) * t for a, b in zip(b0, b1)]

    def neighbours(self, f):
        """Nearest keys strictly before and after f (None at either end)."""
        i = bisect.bisect_left(self.order, f)
        j = bisect.bisect_right(self.order, f)
        return (self.order[i - 1] if i > 0 else None,
                self.order[j] if j < len(self.order) else None)


class Masks:
    def __init__(self, relpath, n, w, h):
        self.path = mask_path(relpath)
        self.relpath, self.n, self.w, self.h = relpath, n, w, h
        self.tracks = []
        self.reviewed = bytearray(n)
        if os.path.exists(self.path):
            with open(self.path) as fh:
                d = json.load(fh)
            if d["frames"] != n:
                sys.exit(f"{rel(self.path)} was made for {d['frames']} frames but the "
                         f"clip now has {n} -- was it re-trimmed? Move the json aside to start over.")
            self.tracks = [Track(t["keys"]) for t in d["tracks"]]
            for a, b in d["reviewed"]:
                self.reviewed[a:b + 1] = b"\x01" * (b - a + 1)

    @classmethod
    def load(cls, relpath):
        with open(mask_path(relpath)) as fh:
            d = json.load(fh)
        m = cls.__new__(cls)
        m.path, m.relpath, m.n, m.w, m.h = mask_path(relpath), relpath, d["frames"], d["width"], d["height"]
        m.tracks = [Track(t["keys"]) for t in d["tracks"]]
        m.reviewed = bytearray(m.n)
        for a, b in d["reviewed"]:
            m.reviewed[a:b + 1] = b"\x01" * (b - a + 1)
        return m

    def boxes_at(self, f):
        return [b for b in (t.box_at(f) for t in self.tracks) if b is not None]

    def unreviewed_ranges(self):
        return runs(self.reviewed, 0)

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        d = {
            "source": self.relpath, "frames": self.n, "width": self.w, "height": self.h,
            "tracks": [{"keys": {str(k): (None if t.keys[k] is None else [round(v, 1) for v in t.keys[k]])
                                 for k in t.order}} for t in self.tracks],
            "reviewed": runs(self.reviewed, 1),
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(d, fh, indent=1)
        os.replace(tmp, self.path)


def runs(flags, value):
    out, start = [], None
    for i, v in enumerate(flags):
        if v == value and start is None:
            start = i
        elif v != value and start is not None:
            out.append([start, i - 1]); start = None
    if start is not None:
        out.append([start, len(flags) - 1])
    return out


# --------------------------------------------------------------- frames ----

def read_frames(src, scale):
    """Decode every frame once, keep them JPEG-compressed at display size.

    Sequential decode (never seek) so frame i here is exactly frame i in
    render. Cached on disk keyed by the source's size and mtime.
    """
    st = os.stat(src)
    tag = f"{os.path.basename(src)}-{st.st_size}-{int(st.st_mtime)}-{scale:.4f}.pkl"
    cpath = os.path.join(CACHE, tag)
    if os.path.exists(cpath):
        with open(cpath, "rb") as fh:
            return pickle.load(fh)
    cap = cv2.VideoCapture(src)
    frames = []
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if scale != 1:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        frames.append(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())
        if len(frames) % 100 == 0:
            print(f"\r  decoding {len(frames)} frames", end="", flush=True)
    print(f"\r  decoded {len(frames)} frames      ")
    os.makedirs(CACHE, exist_ok=True)
    for old in os.listdir(CACHE):
        if old.startswith(os.path.basename(src) + "-"):
            os.remove(os.path.join(CACHE, old))
    with open(cpath, "wb") as fh:
        pickle.dump(frames, fh)
    return frames


# ------------------------------------------------------------- annotate ----

class Annotator:
    def __init__(self, relpath):
        src = original(relpath)
        w, h, rate = probe(src)
        num, den = (int(x) for x in rate.split("/"))
        self.fps = num / den
        self.scale = min(MAX_W / w, MAX_H / h, 2.0)
        print(f"{relpath}  {w}x{h} @ {self.fps:.3f} fps  (source: {rel(src)})")
        self.frames = read_frames(src, self.scale)
        self.n = len(self.frames)
        self.m = Masks(relpath, self.n, w, h)
        self.dw, self.dh = round(w * self.scale), round(h * self.scale)
        self.f = 0
        self.cur = 0                  # current track index
        self.pending_new = not self.m.tracks
        self.drag = None              # (mode, data) while the mouse is down
        self.live = None              # box being dragged, source px
        self.solid = False
        self.playing = False
        self.speed = 1.0
        self.undo = []
        self.dirty_file = False
        self.msg, self.msg_t = "", 0
        self.cache_idx, self.cache_img = -1, None

    # -- edits ---------------------------------------------------------------

    def snapshot(self):
        self.undo.append((copy.deepcopy(self.m.tracks), bytearray(self.m.reviewed), self.cur))
        del self.undo[:-200]

    def edit(self, track, fn):
        """Apply fn() to track, un-reviewing every other frame whose box changed."""
        self.snapshot()
        lo, hi = track.neighbours(self.f)
        lo = 0 if lo is None else lo
        hi = self.n - 1 if hi is None else hi
        before = [track.box_at(i) for i in range(lo, hi + 1)]
        fn()
        for i in range(lo, hi + 1):
            if i != self.f and track.box_at(i) != before[i - lo]:
                self.m.reviewed[i] = 0
        self.dirty_file = True

    def set_key(self, box):
        if self.pending_new or not self.m.tracks:
            self.snapshot()
            self.m.tracks.append(Track())
            self.cur = len(self.m.tracks) - 1
            self.pending_new = False
            self.m.tracks[self.cur].set(self.f, box)
            # the new box holds to the end of the clip, over frames that were
            # reviewed without it
            self.m.reviewed[self.f + 1:] = bytes(self.n - self.f - 1)
            self.dirty_file = True
            return
        t = self.m.tracks[self.cur]
        self.edit(t, lambda: t.set(self.f, box))

    def track(self):
        return self.m.tracks[self.cur] if self.m.tracks and not self.pending_new else None

    def say(self, s):
        self.msg, self.msg_t = s, time.time()

    # -- geometry ------------------------------------------------------------

    def to_disp(self, b):
        s = self.scale
        return [b[0] * s, b[1] * s, b[2] * s, b[3] * s]

    def to_src(self, x0, y0, x1, y1):
        s = self.scale
        x0, x1 = sorted((max(0, min(self.dw, x0)), max(0, min(self.dw, x1))))
        y0, y1 = sorted((max(0, min(self.dh, y0)), max(0, min(self.dh, y1))))
        return [x0 / s, y0 / s, (x1 - x0) / s, (y1 - y0) / s]

    def on_mouse(self, ev, x, y, flags, _):
        if ev == cv2.EVENT_LBUTTONDOWN:
            self.playing = False
            if y >= self.dh:
                self.drag = ("scrub", None)
                self.seek_x(x)
                return
            # prefer the current track's box, else grab whichever box was clicked
            order = ([self.cur] if self.track() else []) + [i for i in range(len(self.m.tracks)) if i != self.cur]
            for i in order:
                b = self.m.tracks[i].box_at(self.f)
                if b is None:
                    continue
                dx, dy, dw, dh = self.to_disp(b)
                corners = [(dx, dy), (dx + dw, dy), (dx, dy + dh), (dx + dw, dy + dh)]
                for ci, (cx, cy) in enumerate(corners):
                    if abs(x - cx) <= HANDLE and abs(y - cy) <= HANDLE:
                        self.cur, self.pending_new = i, False
                        ox, oy = corners[3 - ci]
                        self.drag = ("resize", (ox, oy))
                        return
                if dx <= x <= dx + dw and dy <= y <= dy + dh:
                    self.cur, self.pending_new = i, False
                    self.drag = ("move", (x - dx, y - dy, dw, dh))
                    self.live = list(b)
                    return
            self.drag = ("draw", (x, y))
            self.live = None
        elif ev == cv2.EVENT_MOUSEMOVE and self.drag:
            mode, d = self.drag
            if mode == "scrub":
                self.seek_x(x)
            elif mode == "draw":
                self.live = self.to_src(d[0], d[1], x, y)
            elif mode == "resize":
                self.live = self.to_src(d[0], d[1], x, y)
            elif mode == "move":
                ox, oy, bw, bh = d
                nx = max(0, min(self.dw - bw, x - ox))
                ny = max(0, min(self.dh - bh, y - oy))
                self.live = self.to_src(nx, ny, nx + bw, ny + bh)
        elif ev == cv2.EVENT_LBUTTONUP and self.drag:
            mode, _ = self.drag
            self.drag = None
            if mode != "scrub" and self.live and self.live[2] * self.scale >= 4 and self.live[3] * self.scale >= 4:
                self.set_key(self.live)
            self.live = None

    def seek_x(self, x):
        self.f = max(0, min(self.n - 1, int(x / self.dw * self.n)))

    # -- drawing -------------------------------------------------------------

    def frame_img(self):
        if self.cache_idx != self.f:
            buf = np.frombuffer(self.frames[self.f], np.uint8)
            self.cache_img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            self.cache_idx = self.f
        return self.cache_img.copy()

    def draw(self):
        img = self.frame_img()
        shade = img.copy()
        boxes = []
        for i, t in enumerate(self.m.tracks):
            b = self.live if (i == self.cur and self.live is not None and not self.pending_new) else t.box_at(self.f)
            if b is not None:
                boxes.append((i, b, self.f in t.keys and t.keys[self.f] is not None))
        if self.live is not None and (self.pending_new or not self.m.tracks):
            boxes.append((len(self.m.tracks), self.live, True))
        for i, b, _ in boxes:
            x, y, w, h = (int(round(v)) for v in self.to_disp(b))
            cv2.rectangle(shade, (x, y), (x + w, y + h), (0, 0, 0), -1)
        img = shade if self.solid else cv2.addWeighted(shade, 0.55, img, 0.45, 0)
        for i, b, is_key in boxes:
            x, y, w, h = (int(round(v)) for v in self.to_disp(b))
            c = COLORS[i % len(COLORS)]
            cv2.rectangle(img, (x, y), (x + w, y + h), c, 3 if is_key else 1)
            label = f"{i + 1}" + (" KEY" if is_key else "")
            cv2.putText(img, label, (x + 3, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)
            if i == self.cur:
                for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                    cv2.rectangle(img, (cx - 4, cy - 4), (cx + 4, cy + 4), c, -1)

        # status line
        rv = sum(self.m.reviewed)
        t = self.track()
        tr = f"track {self.cur + 1}/{len(self.m.tracks)}" if t else f"new track {len(self.m.tracks) + 1} (draw a box)"
        state = ""
        if t and self.f in t.keys:
            state = "  HIDE KEY" if t.keys[self.f] is None else "  KEY"
        s = (f"frame {self.f + 1}/{self.n}  {tr}{state}   reviewed {rv}/{self.n} ({100 * rv // self.n}%)"
             f"   {'PLAY x%g' % self.speed if self.playing else ''}{'  *' if self.dirty_file else ''}")
        cv2.putText(img, s, (9, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, s, (9, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        if self.msg and time.time() - self.msg_t < 2.5:
            cv2.putText(img, self.msg, (9, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(img, self.msg, (9, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)

        return np.vstack([img, self.timeline()])

    def timeline(self):
        W, n = self.dw, self.n
        tl = np.full((TL_H, W, 3), 30, np.uint8)
        xs = (np.arange(W) * n // W).clip(0, n - 1)
        rev = np.frombuffer(bytes(self.m.reviewed), np.uint8)
        # top half: reviewed (green) vs not (red) -- a pixel is green only if
        # every frame it covers is reviewed
        edges = np.linspace(0, n, W + 1).astype(int)
        for px in range(W):
            a, b = edges[px], max(edges[px] + 1, edges[px + 1])
            tl[2:14, px] = (60, 170, 60) if rev[a:b].all() else (40, 40, 150)
        # bottom half: where the current track has a box, plus its keyframes
        t = self.track()
        if t:
            c = COLORS[self.cur % len(COLORS)]
            for px in range(W):
                if t.box_at(int(xs[px])) is not None:
                    tl[18:30, px] = tuple(v // 2 for v in c)
            for k in t.order:
                px = int(k / n * W)
                cv2.line(tl, (px, 16), (px, 32), (255, 255, 255) if t.keys[k] is not None else (0, 0, 255), 1)
        px = int((self.f + 0.5) / n * W)
        cv2.line(tl, (px, 0), (px, TL_H), (0, 255, 255), 2)
        return tl

    # -- loop ----------------------------------------------------------------

    def run(self):
        win = "face-mask  (? for keys)"
        cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(win, self.on_mouse)
        print(__doc__[__doc__.index("Keys in"):])
        self.next_t = time.time()
        while True:
            self.m.reviewed[self.f] = 1
            cv2.imshow(win, self.draw())
            if self.playing:
                self.next_t += 1 / (self.fps * self.speed)
                wait = max(1, int((self.next_t - time.time()) * 1000))
            else:
                wait = 20
            k = cv2.waitKeyEx(wait)
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
            if k == -1:
                if self.playing:
                    if self.f + 1 < self.n:
                        self.f += 1
                    else:
                        self.playing = False
                continue
            if self.handle_key(k) == "quit":
                break
        self.m.save()
        cv2.destroyAllWindows()
        left = self.m.unreviewed_ranges()
        print(f"saved {rel(self.m.path)}  ({len(self.m.tracks)} tracks, "
              f"{sum(len(t.order) for t in self.m.tracks)} keyframes, "
              f"{self.n - sum(self.m.reviewed)} frames still unreviewed)")
        if left:
            print("  unreviewed: " + ", ".join(f"{a + 1}-{b + 1}" if a != b else f"{a + 1}" for a, b in left[:12])
                  + (" ..." if len(left) > 12 else ""))

    def step(self, d):
        self.playing = False
        self.f = max(0, min(self.n - 1, self.f + d))

    def handle_key(self, k):
        ch = chr(k) if 0 <= k < 0x110000 and k < 256 else ""
        t = self.track()
        if ch in (".", "d") or k in (63235, 65363, 2555904):
            self.step(1)
        elif ch in (",", "a") or k in (63234, 65361, 2424832):
            self.step(-1)
        elif ch in (">", "D"):
            self.step(10)
        elif ch in ("<", "A"):
            self.step(-10)
        elif ch in ("]", "[") and t:
            lo, hi = t.neighbours(self.f)
            tgt = hi if ch == "]" else lo
            if tgt is not None:
                self.step(tgt - self.f)
        elif ch == " ":
            self.playing = not self.playing
            if self.playing and self.f == self.n - 1:
                self.f = 0
            self.next_t = time.time()
        elif ch in ("-", "_"):
            self.speed = max(0.125, self.speed / 2); self.say(f"speed x{self.speed:g}")
        elif ch in ("=", "+"):
            self.speed = min(4, self.speed * 2); self.say(f"speed x{self.speed:g}")
        elif ch == "k" and t:
            b = t.box_at(self.f)
            if b is not None:
                self.set_key(list(b)); self.say("keyframed")
        elif ch == "x" and t and self.f in t.keys:
            self.edit(t, lambda: t.delete(self.f)); self.say("keyframe deleted")
        elif ch == "h" and t:
            self.edit(t, lambda: t.set(self.f, None)); self.say(f"track {self.cur + 1} hidden from here")
        elif ch == "n":
            self.pending_new = True; self.say("draw a box to start a new track")
        elif (ch == "t" or k == 9) and self.m.tracks:
            self.cur = (self.cur + 1) % len(self.m.tracks) if not self.pending_new else self.cur
            self.pending_new = False; self.say(f"track {self.cur + 1}")
        elif ch == "X" and t:
            self.snapshot()
            for i in range(self.n):
                if i != self.f and t.box_at(i) is not None:
                    self.m.reviewed[i] = 0
            del self.m.tracks[self.cur]
            self.cur = max(0, self.cur - 1)
            self.pending_new = not self.m.tracks
            self.dirty_file = True
            self.say("track deleted (u to undo)")
        elif ch == "u" and self.undo:
            tracks, reviewed, cur = self.undo.pop()
            self.m.tracks, self.m.reviewed, self.cur = tracks, reviewed, cur
            self.pending_new = not self.m.tracks
            self.dirty_file = True
            self.say("undone")
        elif ch == "m":
            self.solid = not self.solid; self.say("solid preview" if self.solid else "see-through preview")
        elif ch == "s":
            self.m.save(); self.dirty_file = False; self.say("saved")
        elif ch == "?":
            print(__doc__[__doc__.index("Keys in"):]); self.say("keys printed in the terminal")
        elif ch == "q" or k == 27:
            return "quit"


# --------------------------------------------------------------- render ----

def source_crf(path):
    """The crf x264 stamped into the clip, so a re-encode keeps its size."""
    with open(path, "rb") as fh:
        m = re.search(rb"crf=([0-9.]+)", fh.read(8 << 20))
    return round(float(m.group(1))) if m else 18


def render(relpath, allow_unreviewed, crf):
    if not os.path.exists(mask_path(relpath)):
        print(f"skip {relpath}: no annotations"); return False
    m = Masks.load(relpath)
    left = m.unreviewed_ranges()
    if left and not allow_unreviewed:
        n_left = sum(b - a + 1 for a, b in left)
        print(f"skip {relpath}: {n_left} frames not reviewed yet "
              f"(first: {left[0][0] + 1}) -- finish in annotate, or pass --allow-unreviewed")
        return False

    served = os.path.join(ROOT, relpath)
    poster = os.path.join(ROOT, poster_rel(relpath))
    for p in (served, poster):
        b = os.path.join(BACKUP, rel(p))
        if os.path.exists(p) and not os.path.exists(b):
            os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.copy2(p, b)
            print(f"  backed up original -> {rel(b)}")
    src = os.path.join(BACKUP, relpath)
    src_poster = os.path.join(BACKUP, poster_rel(relpath))

    w, h, rate = probe(src)
    crf = source_crf(src) if crf is None else crf
    # The poster was grabbed from some frame of the clip; find it by picture
    # similarity and re-grab that same frame from the masked output.
    ref = None
    if os.path.exists(src_poster):
        ref = cv2.resize(cv2.imread(src_poster, cv2.IMREAD_GRAYSCALE), (64, 36)).astype(np.float32)
    best = (float("inf"), None)

    tmp = served + ".masking.mp4"
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", rate, "-i", "-",
         "-i", src, "-map", "0:v", "-map", "1:a?", "-c:a", "copy",
         "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", tmp],
        stdin=subprocess.PIPE)
    cap = cv2.VideoCapture(src)
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        # match the poster against the unmasked frame -- the poster is unmasked too
        g = None if ref is None else cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 36)).astype(np.float32)
        if i < m.n:
            for x, y, bw, bh in m.boxes_at(i):
                x0, y0 = max(0, int(np.floor(x))), max(0, int(np.floor(y)))
                x1, y1 = min(w, int(np.ceil(x + bw))), min(h, int(np.ceil(y + bh)))
                img[y0:y1, x0:x1] = 0
        ff.stdin.write(img.tobytes())
        if g is not None:
            d = float(np.mean((g - ref) ** 2))
            if d < best[0]:
                best = (d, img.copy())
        i += 1
        if i % 100 == 0:
            print(f"\r  {relpath}: {i}/{m.n}", end="", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit(f"ffmpeg failed on {relpath}")
    print(f"\r  {relpath}: {i}/{m.n} frames")
    if i != m.n:
        os.remove(tmp)
        sys.exit(f"{relpath}: decoded {i} frames but annotations cover {m.n}; not replacing it")
    os.replace(tmp, served)

    if best[1] is not None:
        ph, pw = cv2.imread(src_poster).shape[:2]
        out = best[1] if (pw, ph) == (w, h) else cv2.resize(best[1], (pw, ph), interpolation=cv2.INTER_AREA)
        cv2.imwrite(poster, out, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"  poster -> {rel(poster)}")
    print(f"  {relpath}: {os.path.getsize(src) / 1e6:.1f} MB -> {os.path.getsize(served) / 1e6:.1f} MB")
    return True


# --------------------------------------------------------------- status ----

def status():
    for v in site_videos():
        mp = mask_path(v)
        masked = os.path.exists(os.path.join(BACKUP, v))
        if not os.path.exists(mp):
            print(f"  {'--':>4}  {v}")
            continue
        m = Masks.load(v)
        pct = 100 * sum(m.reviewed) // m.n
        stale = masked and os.path.getmtime(mp) > os.path.getmtime(os.path.join(ROOT, v))
        state = "rendered" + (" (annotations changed since)" if stale else "") if masked else "not rendered"
        keys = sum(len(t.order) for t in m.tracks)
        print(f"  {pct:>3}%  {v}  [{len(m.tracks)} tracks, {keys} keys, {state}]")
    print("\n  % = frames reviewed; -- = not started")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    a = sub.add_parser("annotate"); a.add_argument("video")
    r = sub.add_parser("render"); r.add_argument("video", nargs="?")
    r.add_argument("--all", action="store_true", help="every served clip with annotations")
    r.add_argument("--allow-unreviewed", action="store_true")
    r.add_argument("--crf", type=int, help="default: whatever the original was encoded at")
    args = ap.parse_args()

    if args.cmd == "status":
        status()
    elif args.cmd == "annotate":
        Annotator(rel(args.video)).run()
    elif args.cmd == "render":
        if args.all == bool(args.video):
            ap.error("give a video or --all")
        for v in (site_videos() if args.all else [rel(args.video)]):
            if args.all and not os.path.exists(mask_path(v)):
                continue
            render(v, args.allow_unreviewed, args.crf)


if __name__ == "__main__":
    main()
