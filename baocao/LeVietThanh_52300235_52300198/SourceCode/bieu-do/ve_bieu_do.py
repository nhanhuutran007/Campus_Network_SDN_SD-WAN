"""Charts for the final report, drawn from the measurement logs (and the SDN table already in the report)."""
import csv, json, re, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

R = "D:/New folder/Campus_Network_SDN_SD-WAN/"
OUT = R + "baocao/cuoi-ky/image/"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.dpi": 200})


def finish(ax, fig, name, xlabel=None, ylabel=None, xgrid=True):
    if xlabel: ax.set_xlabel(xlabel)
    if ylabel: ax.set_ylabel(ylabel)
    ax.grid(axis="x" if xgrid else "y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(OUT + name, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


# 1. SDN self-recovery scenarios (values from Table "Kết quả kịch bản tự phục hồi SDN")
sc = ["S1: D1-C1", "S2: A4-D1", "S3: D1-D2", "S4: D2-C1", "S5: A4-D1 + D2-C1", "S6: D1-C1 + D1-C2"]
cut = [3.2, 2.0, 0, 0, 3.5, 3.6]
rec = [0, 0, 0, 0, 0.1, 0]
fig, ax = plt.subplots(figsize=(7.2, 3.6))
y = range(len(sc))
h = 0.36
ax.barh([i - h / 2 - 0.02 for i in y], cut, height=h, color=S1, label="Gián đoạn khi cắt")
ax.barh([i + h / 2 + 0.02 for i in y], rec, height=h, color=S2, label="Gián đoạn khi khôi phục")
for i in y:
    ax.text(cut[i] + 0.08, i - h / 2 - 0.02, ("%.1f s" % cut[i]).replace(".", ","), va="center", fontsize=9, color=INK)
    ax.text(rec[i] + 0.08, i + h / 2 + 0.02, ("%.1f s" % rec[i]).replace(".", ","), va="center", fontsize=9, color=INK2)
ax.axvline(5, color=INK2, linestyle="--", linewidth=1)
ax.text(5.05, -0.75, "ngưỡng đạt khi cắt: 5 s", fontsize=8.5, color=INK2, va="center")
ax.set_yticks(list(y)); ax.set_yticklabels(sc); ax.invert_yaxis(); ax.set_xlim(0, 6.6); ax.set_ylim(len(sc) - 0.4, -1.1)
ax.legend(loc="lower right", frameon=False, fontsize=9)
finish(ax, fig, "bd-sdn-kichban.png", xlabel="Thời gian gián đoạn (giây)")

# 2. VLAN add end-to-end (3 runs, 07/11/2026)
runs = [json.loads(l) for l in open(R + "log/sdn-eval/vlan_dau_cuoi_20261107.jsonl", encoding="utf-8")]
ms = [("Controller SDN cấu hình xong", "t_sdn"), ("Hai Core-SW cấu hình xong", "t_core_done"),
      ("Máy trạm ping được gateway", "t_gw"), ("Máy trạm ping được DHCP-Server", "t_usable")]
fig, ax = plt.subplots(figsize=(7.2, 2.7))
for i, (lab, k) in enumerate(ms):
    vals = [r[k] for r in runs]
    m = st.mean(vals)
    ax.barh(i, m, height=0.5, color=S1)
    ax.scatter(vals, [i] * len(vals), s=16, color=INK, zorder=3, linewidths=0)
    ax.text(max(vals) + 0.8, i, ("%.1f s" % m).replace(".", ","), va="center", fontsize=9, color=INK)
ax.set_yticks(range(len(ms))); ax.set_yticklabels([m[0] for m in ms]); ax.invert_yaxis(); ax.set_xlim(0, 50)
finish(ax, fig, "bd-vlan-daucuoi.png", xlabel="Thời gian kể từ lúc gửi yêu cầu thêm VLAN (giây)")

# 3. Branch failover, per direction (07/11/2026, 4 valid runs)
rt = [json.loads(l) for l in open(R + "log/bfd-tuning/rto_2chieu_20261107.jsonl", encoding="utf-8")]
rt = [r for r in rt if "error" not in r]
# Each run is one timeline bar starting at the cut (t = 0): first the outage while the forward path is
# still broken, then the wait for the return path; the bar ends when the reply reaches the workstation.
vn = lambda v, nd=1: ("%.*f" % (nd, v)).replace(".", ",")
fig, ax = plt.subplots(figsize=(7.2, 3.1))
for i, r in enumerate(rt):
    f, b = r["fwd_vEdge2"], r["reply_at_vpc"]
    ax.barh(i, f, height=0.56, color=S1, edgecolor=SURF, linewidth=1.5,
            label="Giai đoạn 1: chiều đi còn đứt (chờ Brand-FW chuyển sang vEdge2)" if i == 0 else None)
    ax.barh(i, b - f, left=f, height=0.56, color=S2, edgecolor=SURF, linewidth=1.5,
            label="Giai đoạn 2: chiều đi đã thông, chờ chiều về (Site 100 bỏ đường cũ)" if i == 0 else None)
    ax.text(f / 2, i, vn(f) + " s", ha="center", va="center", fontsize=9, color="#ffffff", fontweight="bold")
    ax.text((f + b) / 2, i, vn(b - f) + " s", ha="center", va="center", fontsize=9, color="#ffffff", fontweight="bold")
    ax.text(b + 0.12, i, "thông lại sau " + vn(b) + " s", va="center", fontsize=9, color=INK)
ax.axvline(7, color=INK2, linestyle="--", linewidth=1, zorder=4)
ax.text(7.1, -0.62, "BFD mặc định: 7 s", fontsize=8.5, color=INK2, ha="left")
ax.set_yticks(range(len(rt))); ax.set_yticklabels(["Lần đo %d" % (i + 1) for i in range(len(rt))])
ax.set_xlim(0, 12); ax.set_ylim(len(rt) - 0.45, -0.85)
ax.set_xticks(range(0, 11, 2))
ax.legend(loc="lower left", frameon=False, fontsize=8.5, ncol=1, bbox_to_anchor=(-0.01, 1.0), handlelength=1.2)
finish(ax, fig, "bd-failover-2chieu.png", xlabel="Thời gian kể từ lúc cắt MPLS của vEdge1 Site 200 (giây)")

# 4a. UDP loss vs offered rate (06/11/2026, all measured directions)
rows = list(csv.DictReader(open(R + "log/thongluong/thongluong_vedge_20261106.csv", encoding="utf-8")))
rates = [(1, "udp_1m"), (2, "udp_2m"), (3, "udp_3m"), (5, "udp_5m"), (10, "udp_10m")]
loss = {r: [] for r, _ in rates}
for row in rows:
    for r, k in rates:
        m = re.search(r"loss (\d+)%", row[k])
        if m: loss[r].append(int(m.group(1)))
xs = [r for r, _ in rates]
med = [st.median(loss[r]) for r in xs]
fig, ax = plt.subplots(figsize=(7.2, 3.0))
ax.fill_between(xs, [min(loss[r]) for r in xs], [max(loss[r]) for r in xs], color=S1, alpha=0.15, linewidth=0, label="Khoảng nhỏ nhất -- lớn nhất")
ax.plot(xs, med, color=S1, linewidth=2, marker="o", markersize=6, label="Trung vị %d chiều đo" % len(loss[1]))
for x, m in zip(xs, med):
    ax.text(x, m + 5, "%g%%" % m, ha="center", fontsize=9, color=INK)
ax.set_xticks(xs); ax.set_xticklabels(["%d" % x for x in xs]); ax.set_ylim(0, 100); ax.set_xlim(0.5, 10.5)
ax.legend(loc="upper left", frameon=False, fontsize=9)
finish(ax, fig, "bd-udp-matgoi.png", xlabel="Tốc độ UDP gửi (Mbit/s)", ylabel="Mất gói (%)", xgrid=False)

# 4b. TCP throughput per direction (mean of the runs that returned a result)
pairs = []
for row in rows:
    v = [float(row[k].split()[0]) * (1 if "Mbit" in row[k] else 0.001) for k in ("tcp1", "tcp2", "tcp3") if "bit/s" in row[k]]
    if v:
        pairs.append(("%s → %s" % (row["src"], row["dst"]), st.mean(v)))
pairs.sort(key=lambda p: p[1])
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.barh(range(len(pairs)), [p[1] for p in pairs], height=0.6, color=S1)
for i, (_, v) in enumerate(pairs):
    ax.text(v + 0.04, i, ("%.2f" % v).replace(".", ","), va="center", fontsize=8.5, color=INK)
ax.set_yticks(range(len(pairs))); ax.set_yticklabels([p[0] for p in pairs]); ax.set_xlim(0, 2.6)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, p: ("%.1f" % v).replace(".", ",")))
finish(ax, fig, "bd-tcp-thongluong.png", xlabel="Thông lượng TCP trung bình (Mbit/s)")

# 5. Branch failover per site and scenario (43 cuts, ICMP 5 packets/s)
fo = [json.loads(l) for l in open(R + "log/failover-chinhanh/failover.jsonl", encoding="utf-8")]
groups = [("Cắt MPLS", [("Site 200", "s200-mpls"), ("Site 300", "s300-mpls"), ("Site 400", "s400-mpls"), ("Site 500", "s500-mpls")]),
          ("Mất vEdge1", [("Site 200", "s200-vedge1-mat"), ("Site 300", "s300-vedge1-mat"), ("Site 400", "s400-vedge1-mat"), ("Site 500", "s500-vedge1-mat")]),
          ("Cắt Internet", [("Site 200", "s200-internet"), ("Site 300", "s300-internet"), ("Site 400", "s400-internet"), ("Site 500", "s500-internet-sau-nat")]),
          ("Mất vEdge2", [("Site 200", "s200-vedge2-mat"), ("Site 300", "s300-vedge2-mat"), ("Site 400", "s400-vedge2-mat"), ("Site 500", "s500-vedge2-mat")])]
# One panel per failure scenario; per site two bars = mean outage of new flows and of running flows,
# labelled with the mean, with one small dot per individual cut.
titles = {"Cắt MPLS": "Cắt đường MPLS (lưu lượng liên site)", "Mất vEdge1": "Mất vEdge1 (lưu lượng liên site)",
          "Cắt Internet": "Cắt đường Internet (lưu lượng ra Internet)", "Mất vEdge2": "Mất vEdge2 (lưu lượng ra Internet)"}
fig, axes = plt.subplots(2, 2, figsize=(7.4, 5.4), sharey=True, sharex=True)
bh = 0.36
for ax, (title, rows) in zip(axes.flat, groups):
    for i, (lab, name) in enumerate(rows):
        x = [r for r in fo if r["name"] == name]
        for vals, off, col, leg in (([r["rto_new"] for r in x], -bh / 2 - 0.02, S1, "Luồng mới (kết nối mở sau khi cắt)"),
                                    ([r["rto_same"] for r in x], bh / 2 + 0.02, S2, "Luồng đang chạy (kết nối có từ trước khi cắt)")):
            m = st.mean(vals)
            ax.barh(i + off, m, height=bh, color=col, label=leg if i == 0 else None)
            ax.scatter(vals, [i + off] * len(vals), s=9, color=INK, zorder=3, linewidths=0)
            ax.text(max(vals) + 1.0, i + off, ("%.1f s" % m).replace(".", ","), va="center", fontsize=8.5, color=INK)
    ax.set_title(titles[title], fontsize=9.5, color=INK, loc="left")
    ax.set_yticks(range(4)); ax.set_yticklabels(["Site 200", "Site 300", "Site 400", "Site 500"]); ax.set_ylim(3.55, -0.55); ax.set_xlim(0, 48)
    ax.set_xticks(range(0, 41, 10))
    ax.grid(axis="x", color=GRID, linewidth=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
h, l = axes.flat[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=2, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 1.045))
fig.supxlabel("Thời gian mất kết nối kể từ lúc cắt (giây) – thanh: trung bình, chấm đen: từng lần cắt", fontsize=9.5, color=INK2)
fig.tight_layout()
fig.savefig(OUT + "bd-failover-4site.png", bbox_inches="tight")
plt.close(fig)
print("saved bd-failover-4site.png")

# 6. UDP loss on SDN paths: stressed host vs stable host (same configuration)
st_all = [json.loads(l) for l in open(R + "log/sdn-eval/stress_20261108.jsonl", encoding="utf-8")]
paths = [("Cùng VLAN, cùng Access", "a1", "a1b"), ("Liên VLAN qua Core", "a1", "a4"), ("VLAN 10 tới Server Farm", "a1", "farm")]
fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.6), sharey=True)
for ax, (title, a, b) in zip(axes, paths):
    u = [r for r in st_all if r["test"] == "udp" and r["src"] == a and r["dst"] == b and "lost_pct" in r]
    old = [r for r in u if r["ts"] < "2026-11-08 17"]
    new = [r for r in u if r["ts"] >= "2026-11-08 17"]
    rates = sorted({r["offered"] for r in u})
    pos = {v: i for i, v in enumerate(rates)}
    ax.scatter([pos[r["offered"]] for r in old], [r["lost_pct"] for r in old], s=42, color=S2, marker="D", zorder=3, edgecolors=SURF, linewidths=1, label="Máy chủ quá tải (1 lần mỗi mức)")
    ax.scatter([pos[r["offered"]] for r in new], [r["lost_pct"] for r in new], s=30, color=S1, zorder=4, edgecolors=SURF, linewidths=1, label="Máy chủ ổn định (3 lần mỗi mức)")
    ax.set_xticks(range(len(rates))); ax.set_xticklabels(["%g" % v for v in rates]); ax.set_xlim(-0.5, len(rates) - 0.5); ax.set_ylim(-1, 21)
    ax.set_title(title, fontsize=9, color=INK, loc="left"); ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
axes[0].set_ylabel("Mất gói (%)")
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=2, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 1.09))
fig.supxlabel("Tốc độ UDP phát (Mbit/s)", fontsize=10, color=INK2)
fig.tight_layout()
fig.savefig(OUT + "bd-sdn-udp-haitrangthai.png", bbox_inches="tight")
plt.close(fig)
print("saved bd-sdn-udp-haitrangthai.png")

# 7. Control-plane load: Ryu CPU vs new MACs per second (stable host)
mf = [r for r in st_all if r["test"] == "macflood" and r["ts"] >= "2026-11-08 17"]
mf.sort(key=lambda r: r["rate"])
xs, ys = [r["mon"]["pktin_max"] for r in mf], [r["mon"]["ryu_max"] for r in mf]
fig, ax = plt.subplots(figsize=(7.2, 2.7))
ax.plot(xs, ys, color=S1, linewidth=2, marker="o", markersize=6, markeredgecolor=SURF, markeredgewidth=1.5, zorder=3)
for r, x, y in zip(mf, xs, ys):
    low = r["rate"] == 1  # the first two points sit close together
    ax.text(x + (22 if low else -12), y + (-2.6 if low else 2.2), "%d MAC/s: %s%%" % (r["rate"], ("%.1f" % y).replace(".", ",")),
            fontsize=8.5, color=INK2, ha="left" if low else "right")
ax.set_xlim(0, 1250); ax.set_ylim(0, 52)
finish(ax, fig, "bd-sdn-packetin.png", xlabel="Packet-in tới Controller (gói/giây)", ylabel="CPU tiến trình Ryu (%)", xgrid=False)
