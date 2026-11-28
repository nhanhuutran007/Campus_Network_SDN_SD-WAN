"""Biểu đồ radar 8 mục tiêu kỹ thuật: đề xuất (SDN + SD-WAN) so với mạng truyền thống trên cùng topology.

Quy tắc chấm (thang 0-10), giải thích đầy đủ ở Bảng tab:co_so_cham_diem của báo cáo:
  - Trục có số đo: bên tốt hơn = 10, bên kia = 10 x (giá trị tốt nhất / giá trị của nó).
      Khả dụng : gián đoạn lớn nhất S1-S6, 3,6 s (SDN) và 5,9 s (RSTP giả lập xóa MAC đúng, biến thể thuận lợi nhất)
      Sử dụng  : tỷ lệ mất gói của người dùng trong 6 kịch bản cắt, 2,45 % và 7,62 %
      Thích ứng: % thời gian thoại thỏa SLA khi đường đang dùng bị thêm 200 ms trong 150 s, 95,3 % (có AAR) và 0,7 %
  - Trục dấu †: chấm định tính theo bằng chứng trong báo cáo, không phải tỉ lệ từ số đo.
Chạy: python ve_bieu_do_radar.py <out.png>
"""
import sys

import matplotlib.pyplot as plt
import numpy as np

OUT = sys.argv[1]
# (nhãn, truyền thống, đề xuất, định tính?)
axes = [
    ("Mở rộng", 5.0, 10.0, True),
    ("Khả dụng", round(10 * 3.6 / 5.9, 1), 10.0, False),
    ("Hiệu suất", 10.0, 10.0, True),
    ("Bảo mật", 4.0, 7.0, True),
    ("Quản lý", 4.0, 10.0, True),
    ("Sử dụng", round(10 * 2.45 / 7.62, 1), 10.0, False),
    ("Thích ứng", round(10 * 0.7 / 95.3, 1), 10.0, False),
    ("Kinh tế", 10.0, 8.0, True),
]
TRAD, PROP = "#f47230", "#257de0"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#d9d8d2"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})

n = len(axes)
ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
fig = plt.figure(figsize=(9, 9), dpi=200)
ax = fig.add_subplot(111, polar=True)
ax.set_theta_offset(np.pi / 2)
ax.set_theta_direction(-1)
ax.set_ylim(0, 10)
ax.set_yticks([])
ax.set_xticks(ang)
ax.set_xticklabels([])
ax.grid(False)
ax.spines["polar"].set_visible(False)
# lưới bát giác như mẫu
for r in (2, 4, 6, 8, 10):
    ax.plot(np.append(ang, ang[0]), [r] * (n + 1), color=GRID, linewidth=1, zorder=1)
    if r in (2, 6, 10):
        ax.text(0, r, str(r), ha="center", va="center", fontsize=12, color=INK2,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"), zorder=5)
for th in ang:
    ax.plot([th, th], [0, 10], color=GRID, linewidth=1, zorder=1)


def close(v):
    return np.append(v, v[0])


a = close(ang)
trad = close(np.array([x[1] for x in axes]))
prop = close(np.array([x[2] for x in axes]))
ax.fill(a, prop, color=PROP, alpha=0.14, zorder=2)
ax.plot(a, prop, color=PROP, linewidth=2, marker="o", markersize=5, zorder=4, label="Đề xuất (SDN + SD-WAN)")
ax.fill(a, trad, color=TRAD, alpha=0.14, zorder=2)
ax.plot(a, trad, color=TRAD, linewidth=2, linestyle="--", marker="o", markersize=5, markerfacecolor="white", zorder=3,
        label="Mạng truyền thống (đối chứng)")

for th, (name, t, p, q) in zip(ang, axes):
    lab = name + (" †" if q else "")
    val = "%s / %s" % (("%g" % t).replace(".", ","), ("%g" % p).replace(".", ","))
    x = np.sin(th)
    ha = "center" if abs(x) < 0.3 else ("left" if x > 0 else "right")
    ax.text(th, 11.3, lab + chr(10) + val, ha=ha, va="center", fontsize=16, color=INK, clip_on=False,
            linespacing=1.4)

ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=2, frameon=False, fontsize=15, labelcolor=INK)
fig.text(0.5, 0.025, "Số dưới tên trục: truyền thống / đề xuất.  † chấm định tính, không phải tỉ lệ từ số đo.",
         ha="center", fontsize=13, color=INK2)
fig.subplots_adjust(left=0.2, right=0.8, top=0.86, bottom=0.18)
fig.savefig(OUT, facecolor="white", bbox_inches="tight", pad_inches=0.15)
print("saved", OUT)
