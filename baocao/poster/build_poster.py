# -*- coding: utf-8 -*-
"""Build the project poster from the faculty poster template (keeps background, header, footer)."""
import os, re, shutil, sys, zipfile
from xml.sax.saxutils import escape
from PIL import Image
import qrcode

SP = os.path.dirname(os.path.abspath(__file__))
REPO = r"D:\New folder\Campus_Network_SDN_SD-WAN"
TPL = os.path.join(REPO, "baocao", "Mẫu_poster dự án CNTT.pptx")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SP, "poster.pptx")
WORK = os.path.join(SP, "poster_build")

shutil.rmtree(WORK, ignore_errors=True)
zipfile.ZipFile(TPL).extractall(WORK)
P = lambda *a: os.path.join(WORK, *a)
EMU = 12700  # per pt

# ---------- images ----------
IMG = {
    "topo": os.path.join(REPO, "baocao/slide_final/image/topo_logic_site.png"),
    "s100": os.path.join(REPO, "baocao/slide_final/image/topo_site100.png"),
    "fail": os.path.join(REPO, "baocao/cuoi-ky/image/bd-failover-4site-don-gian.png"),
}
media = {}
for i, (k, src) in enumerate(IMG.items()):
    im = Image.open(src).convert("RGB")
    im.thumbnail((2600, 2600))
    name = f"poster_{k}.png"
    im.save(P("ppt", "media", name), optimize=True)
    media[k] = (name, im.size, f"rIdP{i+1}")

# QR to the public GitHub repo replaces the template's QR (same file, same rel)
qr = qrcode.QRCode(border=1, box_size=10)
qr.add_data("https://github.com/nhanhuutran007/Campus_Network_SDN_SD-WAN")
qr.make(fit=True)
qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((600, 600), Image.NEAREST).save(P("ppt", "media", "image5.png"))

# drop template sample pictures
for f in ["image2.png", "image3.png", "image4.emf"]:
    os.remove(P("ppt", "media", f))
rels_p = P("ppt", "slides", "_rels", "slide1.xml.rels")
rels = open(rels_p, encoding="utf8").read()
for rid in ["rId4", "rId5", "rId6"]:
    rels = re.sub(r'<Relationship Id="%s"[^>]*/>' % rid, "", rels)
new_rels = "".join(
    f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{n}"/>'
    for n, _, rid in media.values())
rels = rels.replace("</Relationships>", new_rels + "</Relationships>")
open(rels_p, "w", encoding="utf8").write(rels)
ct_p = P("[Content_Types].xml")
ct = open(ct_p, encoding="utf8").read()
if 'Extension="png"' not in ct:
    ct = ct.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
ct = re.sub(r'<Default Extension="emf"[^>]*/>', "", ct)
open(ct_p, "w", encoding="utf8").write(ct)

# ---------- XML helpers ----------
FONT = '<a:latin typeface="SVN-Gilroy" panose="00000500000000000000" pitchFamily="50" charset="0"/>'
BLUE, DARK, GREY, TILE = "0070C0", "1F2937", "4B5563", "E3EFFA"
_id = [200]

def nid():
    _id[0] += 1
    return _id[0]

def run(text, sz, color=DARK, b=False, i=False, baseline=None, scheme=None):
    fill = f'<a:schemeClr val="{scheme}"/>' if scheme else f'<a:srgbClr val="{color}"/>'
    attrs = f'lang="vi-VN" sz="{int(sz*100)}"' + (' b="1"' if b else '') + (' i="1"' if i else '') + (f' baseline="{baseline}"' if baseline else '')
    t = escape(text)
    sp = ' xml:space="preserve"' if text != text.strip() else ''
    return f'<a:r><a:rPr {attrs} dirty="0"><a:solidFill>{fill}</a:solidFill>{FONT}</a:rPr><a:t{sp}>{t}</a:t></a:r>'

def para(runs, algn="l", bullet=False, after=0, line=None, sz=26):
    ppr = f'<a:pPr algn="{algn}"'
    if bullet:
        ppr += f' marL="{int(sz*1.1*EMU)}" indent="-{int(sz*1.1*EMU)}"'
    ppr += '>'
    if line:
        ppr += f'<a:lnSpc><a:spcPct val="{int(line*1000)}"/></a:lnSpc>'
    if after:
        ppr += f'<a:spcAft><a:spcPts val="{int(after*100)}"/></a:spcAft>'
    ppr += f'<a:buClr><a:srgbClr val="{BLUE}"/></a:buClr><a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>' if bullet else '<a:buNone/>'
    ppr += '</a:pPr>'
    return f'<a:p>{ppr}{"".join(runs)}</a:p>'

def textbox(x, y, w, h, paras, anchor="t", fill=None, geom="rect", name="Text", inset=0):
    i = nid()
    sppr_fill = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else '<a:noFill/>'
    av = '<a:avLst><a:gd name="adj" fmla="val 8000"/></a:avLst>' if geom == "roundRect" else '<a:avLst/>'
    ins = int(inset * EMU)
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{name} {i}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{int(x*EMU)}" y="{int(y*EMU)}"/><a:ext cx="{int(w*EMU)}" cy="{int(h*EMU)}"/></a:xfrm>'
            f'<a:prstGeom prst="{geom}">{av}</a:prstGeom>{sppr_fill}<a:ln><a:noFill/></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="{ins}" tIns="{ins}" rIns="{ins}" bIns="{ins}" rtlCol="0" anchor="{anchor}"><a:noAutofit/></a:bodyPr><a:lstStyle/>'
            f'{"".join(paras)}</p:txBody></p:sp>')

def picture(key, x, y, w, descr):
    n, (pw, ph), rid = media[key]
    h = w * ph / pw
    i = nid()
    xml = (f'<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="Picture {i}" descr="{escape(descr)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
           f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
           f'<p:spPr><a:xfrm><a:off x="{int(x*EMU)}" y="{int(y*EMU)}"/><a:ext cx="{int(w*EMU)}" cy="{int(h*EMU)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
           f'<a:ln w="12700"><a:solidFill><a:srgbClr val="D1D5DB"/></a:solidFill></a:ln></p:spPr></p:pic>')
    return xml, h

# ---------- layout (pt) ----------
BODY = 25
HEAD = 32
CAP = 20
LX, RX, CW = 150, 866, 668
TOP = 622
shapes = []

def heading(x, y, text):
    shapes.append(textbox(x, y, CW, 44, [para([run(text, HEAD, BLUE, b=True)])], name="Heading"))
    return y + 56

def caption(x, y, w, text):
    shapes.append(textbox(x, y, w, 30, [para([run(text, CAP, GREY, i=True)], algn="ctr")], name="Caption"))
    return y + 36

# ----- left column -----
y = heading(LX, TOP, "TÓM TẮT")
abstract = ("Khi trường đại học mở rộng thêm nhiều cơ sở, mạng truyền thống cấu hình riêng trên từng thiết bị, "
            "thiếu cái nhìn toàn cục và phụ thuộc một đường WAN. Đề tài thiết kế, triển khai và kiểm chứng trên EVE-NG "
            "một mạng Campus đa cơ sở gồm 74 node: Campus chính (Site 100), ba cơ sở Cần Thơ, Đà Nẵng, Nha Trang, "
            "cơ sở mở rộng (Site 500) và trung tâm điều khiển SD-WAN (Site 900), kết hợp mô hình phân cấp truyền thống "
            "với SDN (Ryu, OpenFlow 1.3, Open vSwitch) và Cisco SD-WAN (Viptela).")
shapes.append(textbox(LX, y, CW, 290, [para([run(abstract, BODY)], algn="just", line=105)], name="Abstract"))
y += 305

y = heading(LX, y, "MÔ HÌNH TỔNG THỂ")
xml, h = picture("topo", LX, y, CW, "Sơ đồ kết nối các site qua Internet và MPLS")
shapes.append(xml); y += h + 8
y = caption(LX, y, CW, "Hình 1. Sáu site kết nối qua hai transport Internet và MPLS") + 14

y = heading(LX, y, "CAMPUS CHÍNH – SITE 100")
remain = 2140 - y - 44
pw, ph = media["s100"][1]
w = min(CW, remain * pw / ph)
xml, h = picture("s100", LX + (CW - w) / 2, y, w, "Sơ đồ Campus chính Site 100")
shapes.append(xml); y += h + 8
caption(LX, y, CW, "Hình 2. Ba tầng Core – Distribution – Access, Ryu điều khiển 6 OVS")

# ----- right column -----
y = heading(RX, TOP, "GIẢI PHÁP")
items = [
    ("SDN: ", "ứng dụng Ryu điều khiển 6 OVS – học MAC theo VLAN, cây chuyển tiếp tập trung, tự phục hồi khi mất liên kết, thêm VLAN và áp chính sách qua REST API."),
    ("SD-WAN: ", "10 vEdge trên hai transport, xác thực PKI, overlay IPsec; vSmart áp SLA, AAR, data/control policy tập trung."),
    ("Truyền thống: ", "VRRP, OSPF, BGP underlay; cặp ASAv HA bảo vệ DMZ và Server Farm; chi nhánh dùng Firewall-as-Core."),
    ("Vận hành: ", "vManage, Campus SDN Console và NetOps Bot (Telegram) giám sát, cảnh báo, chẩn đoán sự cố."),
]
shapes.append(textbox(RX, y, CW, 380, [para([run(a, BODY, BLUE, b=True), run(b, BODY)], bullet=True, after=8, sz=BODY) for a, b in items], name="Solution"))
y += 395

y = heading(RX, y, "KẾT QUẢ ĐẠT ĐƯỢC")
stats = [("30/30", "kịch bản kiểm thử đạt"), ("3,8 ms", "thêm VLAN qua API"), ("≤ 3,6 s", "SDN tự phục hồi"),
         ("99,957%", "khả dụng 112 tunnel"), ("10/10", "phép thử chính sách"), ("3,2–13,4 s", "luồng mới khôi phục")]
gap = 14
tw = (CW - 2 * gap) / 3
th = 118
for k, (big, lab) in enumerate(stats):
    tx = RX + (k % 3) * (tw + gap)
    ty = y + (k // 3) * (th + gap)
    shapes.append(textbox(tx, ty, tw, th, [para([run(big, 38, BLUE, b=True)], algn="ctr"),
                                           para([run(lab, 19, DARK)], algn="ctr")],
                          anchor="ctr", fill=TILE, geom="roundRect", name="Stat", inset=6))
y += 2 * th + gap + 22
xml, h = picture("fail", RX, y, CW, "Biểu đồ thời gian mất kết nối khi sự cố")
shapes.append(xml); y += h + 8
y = caption(RX, y, CW, "Hình 3. Thời gian mất kết nối khi sự cố (46 lần cắt thật)") + 14

y = heading(RX, y, "KẾT LUẬN")
concl = [
    para([run("SDN và SD-WAN kết hợp được với VRRP, OSPF, tường lửa HA trong một hệ thống thống nhất: "
              "lập trình được, tự phục hồi và tự chọn đường theo chất lượng.", BODY)], algn="just", after=8, line=105),
    para([run("Hướng phát triển: ", BODY, BLUE, b=True),
          run("Controller dự phòng, giảm thời gian failover, 802.1X/AAA, chuẩn hóa SD-WAN bằng template vManage.", BODY)],
         algn="just", line=105),
]
shapes.append(textbox(RX, y, CW, 2135 - y, concl, name="Conclusion"))
print("right column ends at", y, "conclusion box h", 2150 - y)

# ---------- slide XML ----------
sp = P("ppt", "slides", "slide1.xml")
s = open(sp, encoding="utf8").read()

# remove sample table and the three sample pictures (keep QR pic rId7)
s = re.sub(r"<p:graphicFrame>.*?</p:graphicFrame>", "", s, flags=re.S)
for rid in ["rId4", "rId5", "rId6"]:
    s = re.sub(r'<p:pic>(?:(?!</p:pic>).)*?r:embed="%s".*?</p:pic>' % rid, "", s, flags=re.S)

def set_tx(s, shape_id, paras_xml):
    m = re.search(r'<p:sp><p:nvSpPr><p:cNvPr id="%s" .*?</p:sp>' % shape_id, s, re.S)
    blk = m.group(0)
    first_p = re.search(r"<a:p>.*</a:p>", blk, re.S)
    new = blk[:first_p.start()] + paras_xml + blk[first_p.end():]
    return s.replace(blk, new)

def hrun(text, sz, b=False, i=False, baseline=None):
    return run(text, sz, b=b, i=i, baseline=baseline, scheme="bg1")

lnsp = '<a:pPr><a:lnSpc><a:spcPts val="5900"/></a:lnSpc></a:pPr>'
s = set_tx(s, "43", '<a:p>' + hrun("Năm triển khai: 2026", 36) + '</a:p>') if 'id="43"' in s else s
# find which of 43/44 is which by text
s = s.replace(">Năm </a:t>", ">Năm </a:t>")
s = set_tx(s, "51", f'<a:p>{lnsp}' + hrun("Đề tài: Xây Dựng Campus Network", 46, b=True) + '<a:br><a:rPr lang="vi-VN" sz="4600"/></a:br>' + hrun("Sử Dụng SDN Và SD-WAN", 46, b=True) + '</a:p>')
s = set_tx(s, "53", f'<a:p>{lnsp}' + hrun("Trần Hữu Nhân", 40, i=True) + hrun("1", 40, i=True, baseline="30000")
           + hrun(", Nguyễn Nhật Hào", 40, i=True) + hrun("1", 40, i=True, baseline="30000")
           + hrun(", Lê Viết Thanh", 40, i=True) + hrun("*", 40, i=True, baseline="30000") + '</a:p>')
s = set_tx(s, "2", '<a:p>' + hrun("1 ", 28, i=True, baseline="30000") + hrun("Sinh viên ngành Mạng máy tính và Truyền thông dữ liệu, ", 28, i=True)
           + hrun("*", 28, i=True, baseline="30000") + hrun("GVHD Khoa Công nghệ thông tin", 28, i=True) + '</a:p>')

s = s.replace("</p:spTree>", "".join(shapes) + "</p:spTree>")
open(sp, "w", encoding="utf8").write(s)

# notes slide of the template carries sample notes: blank it
nsp = P("ppt", "notesSlides", "notesSlide1.xml")
n = open(nsp, encoding="utf8").read()
n = re.sub(r"<a:t>[^<]*</a:t>", "<a:t></a:t>", n)
open(nsp, "w", encoding="utf8").write(n)

if os.path.exists(OUT):
    os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    # [Content_Types].xml first
    z.write(P("[Content_Types].xml"), "[Content_Types].xml")
    for root, _, files in os.walk(WORK):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, WORK).replace(os.sep, "/")
            if arc != "[Content_Types].xml":
                z.write(full, arc)
print("wrote", OUT)
