"""Hình 4.9 bản dễ đọc: thời gian mất kết nối theo kịch bản cắt (trung bình 4 site).

Số liệu lấy từ Hình 4.9 gốc (trung bình từng site 200/300/400/500).
"""
import sys

import matplotlib.pyplot as plt
import numpy as np

OUT = sys.argv[1]

scenarios = [
    "Cắt đường\nMPLS",
    "Mất\nvEdge1",
    "Cắt đường\nInternet",
    "Mất\nvEdge2",
]
# [site 200, 300, 400, 500]
new = np.array([
    [8.5, 8.2, 8.3, 8.9],
    [8.7, 8.1, 8.5, 8.4],
    [9.3, 10.5, 12.2, 9.1],
    [4.0, 9.1, 9.6, 7.2],
])
old = np.array([
    [35.8, 36.3, 36.1, 34.8],
    [34.4, 33.5, 35.4, 36.1],
    [24.7, 26.0, 27.6, 24.5],
    [19.4, 24.5, 24.9, 22.6],
])

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#ffffff"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)

x = np.arange(len(scenarios))
width = 0.36
gap = 0.02  # khe nhỏ giữa 2 cột

for offset, data, color, label in [
    (-(width + gap) / 2, new, BLUE, "Kết nối mới (mở sau khi cắt)"),
    ((width + gap) / 2, old, ORANGE, "Kết nối đang chạy (có từ trước khi cắt)"),
]:
    mean = data.mean(axis=1)
    bars = ax.bar(x + offset, mean, width, color=color, label=label, zorder=2)
    # Vạch mảnh: khoảng chênh giữa các site (thấp nhất – cao nhất)
    ax.vlines(x + offset, data.min(axis=1), data.max(axis=1), color=INK, linewidth=1.2, zorder=3)
    for xi, m, hi in zip(x + offset, mean, data.max(axis=1)):
        ax.text(xi, hi + 0.8, f"{m:.0f} giây".replace(".", ","), ha="center", va="bottom",
                fontsize=12, fontweight="bold", color=INK)

ax.set_xticks(x, scenarios, fontsize=12, color=INK)
ax.set_ylabel("Thời gian mất kết nối (giây)", color=INK2)
ax.set_ylim(0, 44)
ax.yaxis.grid(True, color=GRID, linewidth=1, zorder=0)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color("#b8b7b0")
ax.tick_params(axis="y", colors=INK2, length=0)
ax.tick_params(axis="x", length=0, pad=8)

# Ghi chú nhóm lưu lượng phía dưới trục
for start, text in [(0.5, "Lưu lượng giữa các site"), (2.5, "Lưu lượng ra Internet")]:
    ax.annotate(text, xy=(start, 0), xycoords=("data", "axes fraction"), xytext=(0, -58),
                textcoords="offset points", ha="center", fontsize=11, color=INK2)
    ax.annotate("", xy=(start - 0.9, -0.17), xytext=(start + 0.9, -0.17), xycoords=("data", "axes fraction"),
                arrowprops=dict(arrowstyle="-", color="#b8b7b0", linewidth=1))

ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=2, frameon=False, fontsize=11.5,
          handlelength=1.2, handleheight=1.0, labelcolor=INK)
fig.text(0.01, 0.01, "Cột: trung bình 4 site (200, 300, 400, 500). Vạch đen: site thấp nhất – cao nhất.",
         fontsize=9.5, color=INK2)

fig.subplots_adjust(left=0.08, right=0.98, top=0.86, bottom=0.2)
fig.savefig(OUT, facecolor=SURFACE)
print("saved", OUT)
