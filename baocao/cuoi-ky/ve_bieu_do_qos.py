"""Hai hình QoS/SLA (đo 28/11/2026, log/qos-sla/qos_20261128.jsonl, sinh bởi qos_probe.py).

  bd-qos-nghen.png : mất gói theo lớp khi WAN nghẽn (4 luồng TCP), không QoS và có QoS (trung bình 2 lần).
  bd-qos-aar.png   : trễ một chiều theo từng giây khi đường biz-internet của vEdge1-S100 bị thêm 200 ms (Q3c).
Chạy: python ve_bieu_do_qos.py <jsonl> <thu_muc_anh>
"""
import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

SRC, OUTDIR = sys.argv[1], sys.argv[2]
runs = {}
for line in open(SRC, encoding="utf-8"):
    r = json.loads(line)
    runs[r["label"]] = r

BLUE, AQUA, ORANGE = "#257de0", "#00b894", "#f47230"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#ffffff"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})


def style(ax):
    ax.yaxis.grid(True, color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#b8b7b0")
    ax.tick_params(axis="y", colors=INK2, length=0)
    ax.tick_params(axis="x", length=0, pad=6)


# --- Hình 1: nghẽn, không QoS vs có QoS
classes = [("voice", "Thoại (EF)"), ("video", "Video (AF41)"), ("be", "Thường (BE)")]
noq = [runs["Q2a-nghen-khongQoS"], runs["Q2a-nghen-khongQoS-lan2"]]
q = [runs["Q2b-nghen-coQoS"], runs["Q2b-nghen-coQoS-lan2"]]
loss_noq = [np.mean([r["classes"][c]["loss_pct"] for r in noq]) for c, _ in classes]
loss_q = [np.mean([r["classes"][c]["loss_pct"] for r in q]) for c, _ in classes]
mos_noq = np.mean([r["classes"]["voice"]["mos"] for r in noq])
mos_q = np.mean([r["classes"]["voice"]["mos"] for r in q])

fig, ax = plt.subplots(figsize=(10, 5.2), dpi=200)
fig.patch.set_facecolor(SURFACE)
x = np.arange(len(classes))
w, gap = 0.36, 0.02
for off, vals, color, lab in [(-(w + gap) / 2, loss_noq, ORANGE, "Không QoS"), ((w + gap) / 2, loss_q, BLUE, "Có QoS (LLQ + shaping 1,5 Mbit/s)")]:
    ax.bar(x + off, vals, w, color=color, label=lab, zorder=2)
    for xi, v in zip(x + off, vals):
        ax.text(xi, v + 0.6, ("%.1f %%" % v).replace(".", ","), ha="center", va="bottom", fontsize=11, color=INK)
ax.set_xticks(x, [n for _, n in classes], fontsize=12, color=INK)
ax.set_ylabel("Tỷ lệ mất gói (%)", color=INK2)
ax.set_ylim(0, 42)
style(ax)
ax.legend(loc="upper left", frameon=False, fontsize=11, labelcolor=INK)
ax.text(0, 30, ("MOS thoại\nkhông QoS: %.2f\ncó QoS: %.2f" % (mos_noq, mos_q)).replace(".", ","), ha="center",
        va="bottom", fontsize=11, color=INK)
fig.text(0.01, 0.01, "4 luồng TCP làm nghẽn WAN (~2 Mbit/s). Trung bình 2 lần đo, mỗi lần 60 giây.", fontsize=9, color=INK2)
fig.subplots_adjust(left=0.08, right=0.98, top=0.95, bottom=0.14)
fig.savefig(os.path.join(OUTDIR, "bd-qos-nghen.png"), facecolor=SURFACE)
plt.close(fig)

# --- Hình 2: AAR theo thời gian (Q3c)
r = runs["Q3c-AAR-S100-bizinternet-tre200ms"]
fig, ax = plt.subplots(figsize=(10, 5.2), dpi=200)
fig.patch.set_facecolor(SURFACE)
ax.axvspan(28.4, 178.5, color="#f3f2ee", zorder=0)
ax.text(103, 232, "biz-internet của vEdge1-S100 bị thêm 200 ms", ha="center", fontsize=10.5, color=INK2)
for c, color, lab, z in [("be", ORANGE, "Thường (BE, không có AAR)", 3), ("voice", BLUE, "Thoại (EF, có AAR)", 4)]:
    s = r["classes"][c]["series"]
    t = [k for k, d, n in s if d is not None]
    d = [min(dd, 250) for k, dd, n in s if dd is not None]
    ax.plot(t, d, color=color, linewidth=2, label=lab, zorder=z)
ax.annotate("AAR chuyển thoại sang mpls\n(sau khoảng 8 giây)", xy=(36, 60), xytext=(55, 120), fontsize=10.5, color=INK,
            arrowprops=dict(arrowstyle="->", color=INK2, linewidth=1))
ax.annotate("máy ảo bị khựng khoảng 6 giây ở cả 3 lớp\n(không mất gói, không do AAR)", xy=(164, 215), xytext=(70, 175), fontsize=10, color=INK2,
            arrowprops=dict(arrowstyle="->", color=INK2, linewidth=1))
ax.set_xlabel("Thời gian (giây)", color=INK2)
ax.set_ylabel("Trễ một chiều trung bình mỗi giây (ms)", color=INK2)
ax.set_ylim(0, 250)
ax.set_xlim(0, 240)
style(ax)
ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.45), frameon=False, fontsize=11, labelcolor=INK)
fig.text(0.01, 0.01, "Video (AF41) trùng đường với thoại nên không vẽ riêng. Trục cắt ở 250 ms.", fontsize=9, color=INK2)
fig.subplots_adjust(left=0.08, right=0.98, top=0.95, bottom=0.14)
fig.savefig(os.path.join(OUTDIR, "bd-qos-aar.png"), facecolor=SURFACE)
print("ok")
