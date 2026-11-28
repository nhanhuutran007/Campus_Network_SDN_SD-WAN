"""Hình đối chứng SDN với mạng truyền thống (RSTP) cho 6 kịch bản cắt S1-S6, đo ngày 28/11/2026.

Đọc log/doi-chung-rstp/cutcmp_20261128.jsonl (sinh bởi cut_compare.py). Mỗi kịch bản lấy gián đoạn lớn nhất
trong 4 VLAN lúc cắt.
  SDN            : trung vị 3 lần, vạch = nhỏ nhất-lớn nhất
  RSTP + xóa MAC : trung vị 3 lần, vạch = nhỏ nhất-lớn nhất; bỏ lần lỗi tồn đọng (> 20 s, lần 3 của S5)
  RSTP           : lần 1 (bảng MAC sạch); cột chạm 20 s = không tự phục hồi trong thời gian giữ cắt
Chạy: python ve_bieu_do_doi_chung_rstp.py <jsonl> <out.png>
"""
import json
import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
HOLD = 20.0
rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
v = defaultdict(list)
for r in rows:
    if r["mode"] in ("SDN", "RSTP", "RSTP+xoaMAC"):
        v[(r["mode"], r["case"])].append((r["rep"], max(t.get("cut_s", 0) for t in r["targets"].values())))

cases = ["S1", "S2", "S3", "S4", "S5", "S6"]
names = ["S1\nD1-C1", "S2\nA4-D1", "S3\nD1-D2", "S4\nD2-C1", "S5\nA4-D1 + D2-C1", "S6\nD1-C1 + D1-C2"]


def stat(mode, c, drop_over=None):
    xs = [x for _, x in v[(mode, c)] if drop_over is None or x <= drop_over]
    return np.median(xs), min(xs), max(xs)


sdn = [stat("SDN", c) for c in cases]
flush = [stat("RSTP+xoaMAC", c, HOLD) for c in cases]
rstp = [min(dict(v[("RSTP", c)])[1], HOLD) for c in cases]
rstp_capped = [dict(v[("RSTP", c)])[1] >= HOLD - 0.5 for c in cases]

BLUE, AQUA, ORANGE = "#257de0", "#00b894", "#f47230"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#ffffff"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})
fig, ax = plt.subplots(figsize=(10.5, 5.8), dpi=200)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)
x = np.arange(len(cases))
w, gap = 0.26, 0.02


def label(xi, top, val=None, txt=None):
    t = txt or ("%.1f" % val).replace(".", ",")
    ax.text(xi, top + 0.35, t, ha="center", va="bottom", fontsize=10, color=INK)


for i, (m, lo, hi) in enumerate(sdn):
    xi = x[i] - (w + gap)
    ax.bar(xi, m, w, color=BLUE, zorder=2, label="SDN (Ryu)" if i == 0 else None)
    ax.vlines(xi, lo, hi, color=INK, linewidth=1.2, zorder=3)
    label(xi, max(m, hi), m)
for i, (m, lo, hi) in enumerate(flush):
    xi = x[i]
    ax.bar(xi, m, w, color=AQUA, zorder=2, label="RSTP, giả lập xóa MAC đúng" if i == 0 else None)
    ax.vlines(xi, lo, hi, color=INK, linewidth=1.2, zorder=3)
    label(xi, max(m, hi), m)
for i, val in enumerate(rstp):
    xi = x[i] + (w + gap)
    ax.bar(xi, val, w, color=ORANGE, zorder=2, hatch="//" if rstp_capped[i] else None, edgecolor=SURFACE,
           linewidth=0, label="RSTP (PVST+ ở Core)" if i == 0 else None)
    label(xi, val, val, "≥ 20" if rstp_capped[i] else None)

ax.axhline(HOLD, color="#b8b7b0", linewidth=1, linestyle="--", zorder=1)
ax.text(2.5, HOLD + 0.3, "hết thời gian giữ cắt (20 s)", ha="center", va="bottom", fontsize=9.5,
        color=INK2)
ax.set_xticks(x, names, fontsize=10.5, color=INK)
ax.set_ylabel("Gián đoạn khi cắt (giây)", color=INK2)
ax.set_ylim(0, 24)
ax.yaxis.grid(True, color=GRID, linewidth=1, zorder=0)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color("#b8b7b0")
ax.tick_params(axis="y", colors=INK2, length=0)
ax.tick_params(axis="x", length=0, pad=6)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.08), ncol=3, frameon=False, fontsize=11, labelcolor=INK,
          handlelength=1.2, handleheight=1.0)
fig.text(0.01, 0.01, "Số trên cột: trung vị (giây). SDN và RSTP giả lập xóa MAC: 3 lần, vạch đen = nhỏ nhất–lớn nhất. "
         "RSTP: lần đo đầu; cột gạch = không tự phục hồi.", fontsize=9, color=INK2)
fig.subplots_adjust(left=0.07, right=0.99, top=0.9, bottom=0.17)
fig.savefig(OUT, facecolor=SURFACE)
print("saved", OUT)
