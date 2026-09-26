#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
campus_ping_tool.py  –  Cong cu Do Luong Mang Campus SDN + SD-WAN
================================================================
Ho tro:
  * Ping noi bo (cung chi nhanh) va lien chi nhanh (SD-WAN)
  * Do Avg Latency / Avg Loss / Avg Jitter / Min-Max RTT
  * Ping don le, ping lien tuc, Batch Report (6 Cases)
  * Xuat bieu do PNG dark-theme + CSV ket qua
  * Che do SSH de ping tu host trong EVE-NG
  * [Kiem Thu Nang Cao] SD-WAN Failover Test: tu dong shutdown/no-shutdown
    1 mau WAN (mpls / biz-internet) tren 1 vEdge qua console Viptela CLI,
    do RTO (Recovery Time Objective) bang ping lien tuc qua tunnel con lai
  * [Kiem Thu Nang Cao] Quan ly VLAN: Them / Sua / Xoa / Khoi phuc VLAN + SVI
    (+VRRP) + OSPF network tren Core-SW1/2 qua console Cisco IOS, roi kiem
    chung qua SD-WAN va do thoi gian: SVI up -> FW-ASAv hoc OSPF -> vManage
    API xac nhan OMP+BFD -> VPC site khac ping thong (+traceroute qua vEdge)
  * [Kiem Thu Nang Cao] Chinh sach tap trung: kiem chung policy vSmart
    (data-policy / app-route / control-policy) bang traffic that tu VPC chi
    nhanh + counter policy tren vEdge qua vManage API; tu day lai whitelist

Cach chay:
  python campus_ping_tool.py

Cai thu vien:
  pip install matplotlib paramiko
================================================================
"""
import threading, time, subprocess, os, platform, re, csv, sys, json, ipaddress
from datetime import datetime

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ---------- optional deps ----------
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import paramiko
    HAS_SSH = True
except ImportError:
    HAS_SSH = False

# =========================================================
#  COLOR CONSTANTS  (GitHub dark theme – ala mpls_gui.py)
# =========================================================
BG      = '#0d1117'
BG2     = '#161b22'
BG3     = '#21262d'
BG4     = '#0a0f14'
GREEN   = '#39d353'
CYAN    = '#58a6ff'
YELLOW  = '#e3b341'
RED     = '#f85149'
ORANGE  = '#f0883e'
PURPLE  = '#a371f7'
WHITE   = '#c9d1d9'
GREY    = '#484f58'
TEAL    = '#3fb950'

FONT_MONO  = ('Courier New', 10)
FONT_UI    = ('Segoe UI', 10)
FONT_TITLE = ('Segoe UI', 13, 'bold')
FONT_SMALL = ('Segoe UI', 8)

IS_WINDOWS = platform.system() == 'Windows'

# =========================================================
#  PATH SETUP
# =========================================================
def _find_script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.path.abspath('.')

_SCRIPT_DIR = _find_script_dir()
LOG_DIR     = os.path.join(_SCRIPT_DIR, 'log')
os.makedirs(LOG_DIR, exist_ok=True)

# =========================================================
#  HOST REGISTRY  –  tu topology.png
# =========================================================
SITES = {
    'Site 100 - Campus Chinh': {
        'site_id': 100, 'color': CYAN,
        'vlans': {
            'VLAN 10 - CNTT':       {'subnet':'10.1.10.0/24','gateway':'10.1.10.1','hosts':{'VPC14':'10.1.10.100','VPC19':'10.1.10.101'}},
            'VLAN 20 - TTK':        {'subnet':'10.1.20.0/24','gateway':'10.1.20.1','hosts':{'VPC20':'10.1.20.100','VPC21':'10.1.20.101'}},
            'VLAN 30 - LUAT':       {'subnet':'10.1.30.0/24','gateway':'10.1.30.1','hosts':{'VPC15':'10.1.30.100','VPC16':'10.1.30.101'}},
            'VLAN 40 - HanhChinh':  {'subnet':'10.1.40.0/24','gateway':'10.1.40.1','hosts':{'VPC17':'10.1.40.100','VPC18':'10.1.40.101'}},
            'DMZ':                  {'subnet':'10.1.1.0/28', 'gateway':'10.1.1.1', 'hosts':{'WebServer':'10.1.1.10','MailServer':'10.1.1.11'}},
            'ServerFarm-VLAN90':    {'subnet':'10.1.90.0/24','gateway':'10.1.90.1','hosts':{'DHCP-Server':'10.1.90.10','Syslog-Server':'10.1.90.11','SDN-Controller':'10.1.99.10'}},
        },
    },
    'Site 200 - Can Tho': {
        'site_id': 200, 'color': GREEN,
        'vlans': {
            'VLAN 60 - NongNghiep': {'subnet':'10.2.60.0/24','gateway':'10.2.60.1','hosts':{'VPC43':'10.2.60.100','VPC44':'10.2.60.101'}},
            'VLAN 70 - YTe':        {'subnet':'10.2.70.0/24','gateway':'10.2.70.1','hosts':{'VPC46':'10.2.70.100','VPC47':'10.2.70.101'}},
            'Brand-FW-CT':          {'subnet':'10.2.1.0/30', 'gateway':'10.2.1.1', 'hosts':{'BrandFW-CT':'10.2.1.1'}},
        },
    },
    'Site 300 - Da Nang': {
        'site_id': 300, 'color': YELLOW,
        'vlans': {
            'VLAN 80 - DuLich':  {'subnet':'10.3.80.0/24','gateway':'10.3.80.1','hosts':{'VPC50':'10.3.80.100','VPC54':'10.3.80.101'}},
            'VLAN 90 - KyThuat': {'subnet':'10.3.90.0/24','gateway':'10.3.90.1','hosts':{'VPC53':'10.3.90.100','VPC48':'10.3.90.101'}},
            'Brand-FW-DN':       {'subnet':'10.3.1.0/30', 'gateway':'10.3.1.1', 'hosts':{'BrandFW-DN':'10.3.1.1'}},
        },
    },
    'Site 400 - Nha Trang': {
        'site_id': 400, 'color': ORANGE,
        'vlans': {
            'VLAN 50 - ThuySan': {'subnet':'10.4.50.0/24','gateway':'10.4.50.1','hosts':{'VPC51':'10.4.50.100','VPC45':'10.4.50.101'}},
            'VLAN 60 - LuHanh':  {'subnet':'10.4.60.0/24','gateway':'10.4.60.1','hosts':{'VPC49':'10.4.60.100','VPC52':'10.4.60.101'}},
            'Brand-FW-NT':       {'subnet':'10.4.1.0/30', 'gateway':'10.4.1.1', 'hosts':{'BrandFW-NT':'10.4.1.1'}},
        },
    },
}

HOST_IP   = {}
HOST_SITE = {}
HOST_VLAN = {}
for _sn, _sd in SITES.items():
    for _vn, _vd in _sd['vlans'].items():
        for _hn, _hip in _vd['hosts'].items():
            HOST_IP[_hn]   = _hip
            HOST_SITE[_hn] = _sn
            HOST_VLAN[_hn] = _vn

ALL_HOSTS = sorted(HOST_IP.keys())

# =========================================================
#  VPC NODE IDs  –  console port = 33536 + node_id (EVE-NG)
# =========================================================
VPC_NODE_IDS = {
    # Site 100 – Campus Chinh
    'VPC14': 14, 'VPC15': 15, 'VPC16': 16, 'VPC17': 17,
    'VPC18': 18, 'VPC19': 19, 'VPC20': 20, 'VPC21': 21,
    # Site 200 / 300 / 400
    'VPC43': 43, 'VPC44': 44, 'VPC45': 45, 'VPC46': 46,
    'VPC47': 47, 'VPC48': 48, 'VPC49': 49, 'VPC50': 50,
    'VPC51': 51, 'VPC52': 52, 'VPC53': 53, 'VPC54': 54,
    # VPC-DN aliases (removed – using actual node names)
}
EVE_CONSOLE_BASE = 33536

# =========================================================
#  CORE-SW / vEdge NODE IDs  –  cho Failover Test + Add-VLAN Test
#  (tra tu configs/README.md, muc "Bang anh xa ten thiet bi -> Node ID")
# =========================================================
CORE_SW_NODE_IDS = {'Core-SW1': 3, 'Core-SW2': 4}

VEDGE_NODE_IDS = {
    'vEdge1-S100': 28, 'vEdge2-S100': 6,
    'vEdge1-S200': 29, 'vEdge2-S200': 42,
    'vEdge1-S300': 30, 'vEdge2-S300': 40,
    'vEdge1-S400': 31, 'vEdge2-S400': 41,
    'vEdge65': 65,
}

# Interface WAN <-> mau (color) cua tung vEdge, doc truc tiep tu
# configs/0X-Site.../vEdgeX-SXXX/config.cfg (khoi "vpn 0"). KHONG dong nhat
# giua cac vEdge (S100 dual-color tren 1 thiet bi, chi nhanh mot vEdge/mau)
# nen phai tra bang that, khong doan theo pattern.
WAN_IFACE = {
    'vEdge1-S100': {'mpls': 'ge0/2', 'biz-internet': 'ge0/3'},
    'vEdge2-S100': {'biz-internet': 'ge0/2', 'mpls': 'ge0/3'},
    'vEdge1-S200': {'mpls': 'ge0/2'},
    'vEdge2-S200': {'biz-internet': 'ge0/0'},
    'vEdge1-S300': {'mpls': 'ge0/0'},
    'vEdge2-S300': {'biz-internet': 'ge0/0'},
    'vEdge1-S400': {'mpls': 'ge0/0'},
    'vEdge2-S400': {'biz-internet': 'ge0/0'},
}

# =========================================================
#  KIEM CHUNG VLAN QUA SD-WAN  (Quan ly VLAN)
#  Doc tu lab that 24/09/2026: moi vEdge co "vpn 1" (LAN) + static
#  10.X.0.0/16 -> FW, OMP "advertise static/connected" => VLAN moi o Core-SW
#  duoc overlay mang di nho route tong /16; chi can Core-SW dua subnet vao
#  OSPF de FW-ASAv hoc duong ve.
# =========================================================
CORE_SITE_ID   = 100          # Core-SW1/2 nam o Site 100
CORE_OSPF_PID  = 1
FW_ASA_NODE_IDS = {'FW-ASAv-Active': 1, 'FW-ASAv-Standby': 2}
VMANAGE_NODE_ID = 33
VMANAGE_IPS     = ('10.9.1.10', '10.9.0.10')

# system-ip vEdge theo site-id (vManage API: deviceId = system-ip)
SITE_VEDGES = {
    100: {'10.200.100.1': 'vEdge1-S100', '10.200.100.2': 'vEdge2-S100'},
    200: {'10.200.200.1': 'vEdge1-S200', '10.200.200.2': 'vEdge2-S200'},
    300: {'10.200.30.1': 'vEdge1-S300', '10.200.30.2': 'vEdge2-S300'},
    400: {'10.200.40.1': 'vEdge1-S400', '10.200.40.2': 'vEdge2-S400'},
}

# IP mat LAN (vpn 1) cua vEdge -> nhan dien hop vEdge trong traceroute
VEDGE_LAN_IPS = {
    '10.1.3.2': 'vEdge1-S100', '10.1.3.14': 'vEdge1-S100', '10.1.3.6': 'vEdge2-S100', '10.1.3.10': 'vEdge2-S100',
    '10.2.1.2': 'vEdge1-S200', '10.2.2.1': 'vEdge1-S200', '10.2.1.6': 'vEdge2-S200', '10.2.2.2': 'vEdge2-S200',
    '10.3.1.2': 'vEdge1-S300', '10.3.2.1': 'vEdge1-S300', '10.3.1.6': 'vEdge2-S300', '10.3.2.2': 'vEdge2-S300',
    '10.4.1.2': 'vEdge1-S400', '10.4.2.1': 'vEdge1-S400', '10.4.1.6': 'vEdge2-S400', '10.4.2.2': 'vEdge2-S400',
}


# =========================================================
#  PING RESULT
# =========================================================
class PingResult:
    __slots__ = ('avg_latency','min_latency','max_latency','jitter','loss','raw','success')
    def __init__(self):
        self.avg_latency = 0.0
        self.min_latency = 0.0
        self.max_latency = 0.0
        self.jitter      = 0.0
        self.loss        = 100.0
        self.raw         = ''
        self.success     = False


# =========================================================
#  VPCS TELNET PING ENGINE
#  SSH vào EVE → telnet vào console VPC → chạy ping từ đó
# =========================================================
def ping_via_vpcs(src_host, dst_ip, count=10, ssh_client=None):
    """Ping từ VPC node (VPCS) qua SSH+Telnet console."""
    result = PingResult()
    if ssh_client is None or not HAS_SSH:
        return ping_host(dst_ip, count)   # fallback

    node_id = VPC_NODE_IDS.get(src_host)
    if not node_id:
        # Host không phải VPCS → fallback ping thường từ EVE server
        return ping_host(dst_ip, count, ssh_client=ssh_client)

    port = EVE_CONSOLE_BASE + node_id
    try:
        # Dùng SSH direct-tcpip channel để kết nối thẳng vào VPCS console port
        # (tránh bash → telnet chain bị lẫn lộn output)
        transport = ssh_client.get_transport()
        chan = transport.open_channel(
            'direct-tcpip',
            dest_addr=('127.0.0.1', port),
            src_addr=('127.0.0.1', 0),
        )
        time.sleep(0.5)
        # Đọc banner VPCS
        _flush_chan(chan)
        # Wakeup VPCS (Enter) x2
        chan.send('\n'); time.sleep(0.3)
        chan.send('\n'); time.sleep(0.4)
        _flush_chan(chan)
        # Gửi lệnh ping – VPCS syntax: ping <ip> -c <n>
        cmd = 'ping {} -c {}\n'.format(dst_ip, count)
        chan.send(cmd)
        # Chờ: mỗi gói VPCS ~0.5s + 4s buffer
        wait_sec = count * 0.5 + 4
        time.sleep(wait_sec)
        raw = _read_chan(chan, timeout=5)
        chan.close()
        # Ghi debug port vào raw để log dễ đọc
        result.raw = '[VPCS port={}] {}\n{}'.format(port, cmd.strip(), raw)
        _parse_vpcs_ping(result, raw)

    except Exception as e:
        result.raw = 'VPCS channel error (port {}): {}'.format(port, e)

    return result


def _flush_chan(chan):
    """Đọc và bỏ buffer channel."""
    time.sleep(0.3)
    try:
        while chan.recv_ready():
            chan.recv(65535)
            time.sleep(0.1)
    except Exception:
        pass


def _read_chan(chan, timeout=8):
    """Đọc output từ channel – Windows-compatible (không dùng select)."""
    buf = b''
    deadline = time.time() + timeout
    empty_streak = 0
    while time.time() < deadline:
        try:
            if chan.recv_ready():
                chunk = chan.recv(65535)
                if chunk:
                    buf += chunk
                    empty_streak = 0
                else:
                    break
            else:
                empty_streak += 1
                # Nếu đã có data rồi và 2s không có thêm → thoát
                if buf and empty_streak > 13:
                    break
                time.sleep(0.15)
        except Exception:
            break
    return buf.decode('utf-8', errors='replace')


# Giữ lại các hàm cũ cho invoke_shell fallback
def _flush(shell):
    """Đọc và bỏ buffer hiện tại (invoke_shell)."""
    time.sleep(0.3)
    try:
        while shell.recv_ready():
            shell.recv(65535)
            time.sleep(0.1)
    except Exception:
        pass


def _read_all(shell):
    """Đọc toàn bộ output từ invoke_shell."""
    buf = b''
    for _ in range(20):
        time.sleep(0.2)
        if shell.recv_ready():
            buf += shell.recv(65535)
        else:
            break
    return buf.decode('utf-8', errors='replace')


def _parse_vpcs_ping(result, raw):
    """Parse VPCS ping output.
    VPCS chi in tung dong ket qua, KHONG co dong tong hop.
    Received: '84 bytes from X icmp_seq=N ttl=T time=X ms'
    Timeout:  'X.X.X.X icmp_seq=N timeout'
    """
    # Chi dong "bytes from" moi la reply that; ICMP unreachable (vd
    # '*10.2.60.1 icmp_seq=1 ttl=255 time=12 ms (ICMP type:3 ... unreachable)')
    # cung co "time=" nhung la MAT goi.
    times    = [float(x) for x in re.findall(r'bytes from .*?time=([\d.]+)\s*ms', raw)]
    timeouts = len(re.findall(r'icmp_seq=\d+\s+timeout', raw, re.IGNORECASE)) + \
               len(re.findall(r'^(?!.*bytes from).*unreachable', raw, re.IGNORECASE | re.M))
    received = len(times)
    total    = received + timeouts

    # Tinh loss
    if total > 0:
        result.loss = round(timeouts / total * 100.0, 1)
    elif received > 0:
        result.loss = 0.0
    else:
        m_l = re.search(r'(\d+)%\s+packet\s+loss', raw)
        result.loss = float(m_l.group(1)) if m_l else 100.0

    # Tinh RTT
    if times:
        result.min_latency = round(min(times), 3)
        result.max_latency = round(max(times), 3)
        result.avg_latency = round(sum(times) / len(times), 3)
        result.jitter      = round(result.max_latency - result.min_latency, 3)
        result.success     = True
    else:
        m_rtt = re.search(
            r'round-trip\s+min/avg/max\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)\s*ms',
            raw, re.IGNORECASE)
        if m_rtt:
            result.min_latency = float(m_rtt.group(1))
            result.avg_latency = float(m_rtt.group(2))
            result.max_latency = float(m_rtt.group(3))
            result.jitter      = round(result.max_latency - result.min_latency, 3)
            result.success     = True
        else:
            result.success = False


# =========================================================
#  IP AUTO-DISCOVERY  –  Telnet vào VPC → "show ip" → lấy IP thực
# =========================================================
def discover_vpc_ip(host_name, ssh_client, timeout=6):
    """Telnet vào 1 VPC node qua SSH, chạy 'show ip', trả về IP thực tế."""
    node_id = VPC_NODE_IDS.get(host_name)
    if not node_id or ssh_client is None:
        return None
    port = EVE_CONSOLE_BASE + node_id
    try:
        shell = ssh_client.invoke_shell(width=200, height=50)
        time.sleep(0.5); _flush(shell)
        shell.send('telnet 127.0.0.1 {}\n'.format(port))
        time.sleep(1.5); _flush(shell)
        # Thử wakeup VPC (press Enter)
        shell.send('\n'); time.sleep(0.5)
        shell.send('show ip\n'); time.sleep(1.5)
        raw = _read_all(shell)
        # Thoát telnet
        shell.send('\x1d'); time.sleep(0.3)
        shell.send('quit\n'); time.sleep(0.3)
        shell.close()
        # Parse: "NAME  : VPC43[1]"  "IP    : 10.2.60.101/24"
        m = re.search(r'IP\s*:\s*(\d+\.\d+\.\d+\.\d+)', raw)
        if m:
            return m.group(1)
        # Fallback: parse DORA hoặc ip dhcp output
        m2 = re.search(r'(?:DORA|IP\s+)(?:IP\s+)?(\d+\.\d+\.\d+\.\d+)', raw, re.IGNORECASE)
        if m2:
            return m2.group(1)
    except Exception:
        pass
    return None


def discover_all_vpcs(ssh_client, callback=None):
    """Discover IP thực của tất cả VPC nodes. callback(host, ip, status) được gọi mỗi node."""
    results = {}
    hosts = [h for h in VPC_NODE_IDS.keys() if not h.startswith('VPC-DN')]
    for host in hosts:
        if callback:
            callback(host, None, 'scanning')
        ip = discover_vpc_ip(host, ssh_client)
        if ip:
            HOST_IP[host] = ip   # cập nhật registry toàn cục
            results[host] = ip
            if callback:
                callback(host, ip, 'ok')
        else:
            if callback:
                callback(host, None, 'fail')
    # Cập nhật aliases VPC-DN
    for alias, real_host in [('VPC-DN1','VPC53'),('VPC-DN2','VPC54'),('VPC-DN3','VPC52')]:
        r_host = 'VPC{}'.format(VPC_NODE_IDS.get(alias, 0))
        if r_host in results:
            HOST_IP[alias] = results[r_host]
            results[alias] = results[r_host]
    return results


# =========================================================
#  CONSOLE CLI ENGINE  –  Core-SW (Cisco IOS) / vEdge (Viptela CLI)
#  Dung chung co che direct-tcpip channel toi console EVE-NG nhu VPCS,
#  phuc vu Failover Test (shutdown/no-shutdown WAN) va Add-VLAN Test.
# =========================================================
def console_open(ssh_client, node_id):
    """Mo 1 channel direct-tcpip toi console EVE-NG cua node_id (Core-SW/vEdge)."""
    port = EVE_CONSOLE_BASE + node_id
    transport = ssh_client.get_transport()
    chan = transport.open_channel(
        'direct-tcpip', dest_addr=('127.0.0.1', port), src_addr=('127.0.0.1', 0))
    time.sleep(0.5)
    _flush_chan(chan)
    return chan


def console_send(chan, cmd, wait=0.8, read_timeout=4):
    """Gui 1 lenh CLI vao channel console, doi va tra ve output."""
    chan.send(cmd + '\n')
    time.sleep(wait)
    return _read_chan(chan, timeout=read_timeout)


def vedge_login(chan, user='admin', password='admin', timeout=5):
    """Dang nhap console vEdge (Viptela CLI) va DAM BAO dung o prompt exec '#'.
    console_open da xoa buffer nen prompt 'login:' cu khong con -> phai gui Enter
    de goi prompt ra truoc (neu chi cho 'login:' xuat hien, tool se go nham lenh
    vao prompt login ma khong bao loi). Thoat config mode / 'Uncommitted changes'
    con treo tu lan truoc. Nem RuntimeError neu khong vao duoc '#'."""
    banner = ''
    for _ in range(3):
        chan.send('\n')
        banner += _read_chan(chan, timeout=timeout)
        tail = _last_line(banner)
        if re.search(r'uncommitted changes', banner, re.IGNORECASE):
            chan.send('no\n'); time.sleep(0.8)
            banner += _read_chan(chan, timeout=3); continue
        if '(config' in tail:
            chan.send('end\n'); time.sleep(0.8)
            banner += _read_chan(chan, timeout=3); continue
        if tail.endswith('#'):
            return banner
        if re.search(r'login\s*:\s*$', tail, re.IGNORECASE):
            chan.send(user + '\n')
            banner += _read_until(chan, 'assword', timeout)
            chan.send(password + '\n'); time.sleep(1.5)
            banner += _read_chan(chan, timeout=timeout)
            if _last_line(banner).endswith('#'):
                return banner
            if re.search(r'login incorrect', banner, re.IGNORECASE):
                raise RuntimeError('sai user/password vEdge ({})'.format(user))
    raise RuntimeError('khong vao duoc prompt # tren vEdge (cuoi: {!r})'.format(_last_line(banner)[-60:]))


VEDGE_LAB_PASSWORDS = ('vnpro@123', 'vnpro@2026', 'okok')   # mat khau lab da ghi nhan (S200-S400 / S100 / node 65)


def vedge_config(ssh, node_id, user, password, cmds):
    """Dang nhap vEdge (thu password nhap vao roi cac password lab), chay cmds
    trong config mode, commit va XAC NHAN 'Commit complete'. Tra ve output;
    nem RuntimeError neu dang nhap hoac commit that bai."""
    chan = console_open(ssh, node_id)
    try:
        for pw in [password] + [p for p in VEDGE_LAB_PASSWORDS if p != password]:
            try:
                vedge_login(chan, user, pw); break
            except RuntimeError as e:
                if 'sai user/password' not in str(e): raise
        else:
            raise RuntimeError('khong dang nhap duoc vEdge node {} (sai password?)'.format(node_id))
        out = console_send(chan, 'config', wait=1.0)
        for cmd in cmds:
            out += console_send(chan, cmd)
        res = console_send(chan, 'commit', wait=2.0, read_timeout=8)
        if 'Commit complete' not in res and 'No modifications to commit' not in res:
            console_send(chan, 'abort')     # bo thay doi chua commit, ve exec mode
            raise RuntimeError('commit khong thanh cong: {!r}'.format(_last_line(res)[-120:]))
        return out + res + console_send(chan, 'end')
    finally:
        chan.close()


def cidr_to_mask(prefix):
    """Doi prefix CIDR (vd '24') -> subnet mask dotted-decimal (Cisco IOS can)."""
    prefix = int(prefix)
    bits = '1' * prefix + '0' * (32 - prefix)
    return '.'.join(str(int(bits[i:i+8], 2)) for i in range(0, 32, 8))


def _last_line(text):
    lines = [l for l in text.replace('\r', '').split('\n') if l.strip()]
    return lines[-1].strip() if lines else ''


def _read_until(chan, marker, timeout=25):
    """Doc channel cho toi khi thay marker (hoac het timeout)."""
    buf = ''
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chan.recv_ready():
            buf += chan.recv(65535).decode('utf-8', errors='replace')
            if marker in buf:
                break
        else:
            time.sleep(0.15)
    return buf


def ios_wake(chan, timeout=12):
    """IOL console bo qua lenh go ngay sau khi ket noi -> gui Enter va CHO
    prompt ('>' hoac '#') truoc khi gui lenh that. Tra ve prompt, nem loi neu im."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        chan.send('\r\n')
        tail = _last_line(_read_chan(chan, timeout=2.5))
        if tail.endswith(('>', '#')):
            return tail
    raise RuntimeError('console khong tra prompt sau {}s'.format(timeout))


def vpcs_cmd(chan, cmd, timeout=10):
    """Gui 1 lenh VPCS va doc toi khi prompt 'VPCS>' xuat hien lai (nhanh hon
    cho 2s im lang; ping 1 goi ~1s neu co reply, ~2s neu timeout)."""
    chan.send(cmd + '\n')
    return _read_until(chan, 'VPCS>', timeout)


def asa_open_active(ssh_client, enable_pw='', log=None):
    """Mo console FW-ASAv dang Active (failover), vao privileged mode.
    Tra ve (ten, chan, da_enable_tu_user_mode) hoac None."""
    for name, nid in FW_ASA_NODE_IDS.items():
        try:
            chan = console_open(ssh_client, nid)
            chan.send('\r\n'); time.sleep(1.2)
            tail = _last_line(_read_chan(chan, timeout=3))
            if '(config' in tail:
                if log: log('  [!] {} dang o config mode -> bo qua\n'.format(name), 'err')
                chan.close(); continue
            was_user = tail.endswith('>')
            if was_user:
                if not enable_pw:
                    if log: log('  [!] {} can enable password (chua nhap) -> bo qua\n'.format(name), 'err')
                    chan.close(); continue
                chan.send('enable\r\n'); time.sleep(1.0)
                chan.send(enable_pw + '\r\n'); time.sleep(1.5)
                if not _last_line(_read_chan(chan, timeout=3)).endswith('#'):
                    if log: log('  [!] {}: sai enable password\n'.format(name), 'err')
                    chan.close(); continue
            console_send(chan, 'terminal pager 0', wait=0.5)
            fo = console_send(chan, 'show failover | include This host', wait=1.2, read_timeout=3)
            if 'This host' not in fo or re.search(r'This host:.*Active', fo):
                return name, chan, was_user
            if was_user:
                console_send(chan, 'disable', wait=0.4)
            chan.close()
        except Exception as e:
            if log: log('  [!] Loi console {}: {}\n'.format(name, e), 'err')
    return None


class VManageAPI:
    """Doc REST API vManage (GET; POST chi cho day whitelist). Uu tien curl tu host EVE; neu host khong
    co route toi 10.9.x (Switch61 down) thi di qua console vManage -> vshell ->
    curl https://127.0.0.1:8443 ngay tren vManage."""
    CJ = '/tmp/.vm_cj_campus_tool'

    def __init__(self, ssh_client, user, password):
        self.ssh, self.user, self.password = ssh_client, user, password
        self.chan = None; self.base = None; self._logged_in = False

    def _host(self, cmd, timeout=40):
        _, out, _ = self.ssh.exec_command(cmd, timeout=timeout)
        return out.read().decode('utf-8', errors='replace')

    def _login_cmd(self):
        import shlex
        return "rm -f {cj}; curl -sk --max-time 20 -c {cj} --data-urlencode {u} --data-urlencode {p} " \
               "{base}/j_security_check -o /dev/null".format(
                   cj=self.CJ, base=self.base,
                   u=shlex.quote('j_username=' + self.user), p=shlex.quote('j_password=' + self.password))

    def open(self):
        for ip in VMANAGE_IPS:
            code = self._host("curl -sk -o /dev/null -w '%{http_code}' --max-time 4 https://" + ip + "/", 15).strip()
            if code and code != '000':
                self.base = 'https://' + ip
                self._host(self._login_cmd())
                return 'host->' + ip
        # fallback: console vManage
        self.chan = console_open(self.ssh, VMANAGE_NODE_ID)
        self.chan.send('\n'); time.sleep(1.5)
        tail = _last_line(_read_chan(self.chan, timeout=3))
        if '(config' in tail:
            raise RuntimeError('console vManage dang o config mode')
        if re.search(r'login\s*:', tail, re.I):
            self.chan.send(self.user + '\n'); time.sleep(1)
            self.chan.send(self.password + '\n'); time.sleep(3)
            if not _last_line(_read_chan(self.chan, timeout=4)).endswith('#'):
                raise RuntimeError('dang nhap console vManage that bai (sai user/pass?)')
            self._logged_in = True
        console_send(self.chan, 'vshell', wait=1.5, read_timeout=3)
        console_send(self.chan, 'stty -echo cols 500; export PS1="VSH# "', wait=0.8, read_timeout=2)
        self.base = 'https://127.0.0.1:8443'
        self.chan.send(self._login_cmd() + '; echo "@@""L@@"\n')
        _read_until(self.chan, '@@L@@', 25)
        return 'console vManage (node {})'.format(VMANAGE_NODE_ID)

    def _exec(self, cmd, timeout=40):
        """Chay 1 lenh shell tren host EVE hoac trong vshell vManage -> stdout."""
        if self.chan is None:
            return self._host(cmd, timeout)
        self.chan.send('echo "@@""B@@"; {}; echo; echo "@@""E@@"\n'.format(cmd))
        buf = _read_until(self.chan, '@@E@@', timeout)
        m = re.search(r'@@B@@(.*)@@E@@', buf, re.S)
        return m.group(1).replace('\r', '') if m else ''

    def get(self, path, grep=None):
        """GET /dataservice/<path> -> list cac dong (dict) trong 'data'.
        Loc NGAY TREN vManage: tach moi object JSON phang ra 1 dong (grep -o) va
        chi giu dong khop regex `grep` -> output nho; console serial lam rot ky
        tu khi output dai (>~10KB) nen parse tung dong, bo dong hong."""
        cmd = "curl -sk --max-time 30 -b {} '{}/dataservice/{}' | grep -o '{{[^{{}}]*}}'".format(
            self.CJ, self.base, path)
        if grep:
            cmd += " | grep -E '{}'".format(grep)
        raw = self._exec(cmd)
        rows = []
        for line in raw.replace('\r', '').split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try: rows.append(json.loads(line))
                except ValueError: pass
        return rows

    def post(self, path, body='{}'):
        """POST /dataservice/<path> (can XSRF token) -> chuoi response tho.
        Chi dung cho thao tac an toan, idempotent (vd day whitelist vEdge)."""
        tok = self._exec("curl -sk --max-time 20 -b {} '{}/dataservice/client/token'".format(
            self.CJ, self.base)).strip().split('\n')[-1].strip()
        if not tok or '<' in tok:
            raise RuntimeError('khong lay duoc XSRF token vManage')
        return self._exec("curl -sk --max-time 30 -b {} -X POST -H 'X-XSRF-TOKEN: {}' "
                          "-H 'Content-Type: application/json' '{}/dataservice/{}' -d '{}'".format(
                              self.CJ, tok, self.base, path, body)).strip()

    def close(self):
        try:
            if self.chan is None:
                self._host('rm -f ' + self.CJ, 10)
            else:
                console_send(self.chan, 'rm -f {}; stty echo; exit'.format(self.CJ), wait=0.8, read_timeout=2)
                if self._logged_in:
                    console_send(self.chan, 'exit', wait=0.8, read_timeout=2)
                self.chan.close()
        except Exception:
            pass


# =========================================================
#  PING ENGINE
# =========================================================
def ping_host(target_ip, count=10, timeout_sec=2, ssh_client=None):
    result = PingResult()
    raw    = ''

    if ssh_client is not None and HAS_SSH:
        cmd = 'ping -c {} -i 0.2 -W {} {}'.format(count, timeout_sec, target_ip)
        try:
            _, stdout, stderr = ssh_client.exec_command(cmd, timeout=count*3+8)
            raw = stdout.read().decode('utf-8','replace') + stderr.read().decode('utf-8','replace')
        except Exception as e:
            result.raw = 'SSH error: {}'.format(e); return result

    elif IS_WINDOWS:
        cmd = ['ping', '-n', str(count), '-w', str(timeout_sec*1000), target_ip]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding='cp437', errors='replace',
                                  timeout=count*(timeout_sec+1)+5)
            raw = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            result.raw = 'Ping timeout'; return result
        except Exception as e:
            result.raw = str(e); return result

    else:
        cmd = ['ping', '-c', str(count), '-i', '0.2', '-W', str(timeout_sec), target_ip]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=count*(timeout_sec+1)+5)
            raw = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            result.raw = 'Ping timeout'; return result
        except Exception as e:
            result.raw = str(e); return result

    result.raw = raw
    _parse_ping(result, raw)
    return result


def _parse_ping(result, raw):
    raw_l = raw.lower()
    if IS_WINDOWS:
        m = re.search(r'minimum\s*=\s*([\d.]+)\s*ms.*?maximum\s*=\s*([\d.]+)\s*ms.*?average\s*=\s*([\d.]+)\s*ms', raw_l, re.DOTALL)
        if m:
            result.min_latency = float(m.group(1))
            result.max_latency = float(m.group(2))
            result.avg_latency = float(m.group(3))
            result.jitter      = round(result.max_latency - result.min_latency, 3)
            result.success     = True
        m2 = re.search(r'\((\d+)%\s+loss\)', raw_l)
        result.loss = float(m2.group(1)) if m2 else (0.0 if result.success else 100.0)
    else:
        m = re.search(r'rtt\s+min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms', raw_l)
        if m:
            result.min_latency = float(m.group(1))
            result.avg_latency = float(m.group(2))
            result.max_latency = float(m.group(3))
            result.jitter      = float(m.group(4))
            result.success     = True
        m2 = re.search(r'([\d.]+)%\s+packet\s+loss', raw)
        result.loss = float(m2.group(1)) if m2 else (0.0 if result.success else 100.0)
    if result.success and result.jitter is None:
        result.jitter = round(result.max_latency - result.min_latency, 3)

# =========================================================
#  CHART ENGINE
# =========================================================
class ChartEngine:
    BG_DARK  = '#0d1117'
    BG_DARK2 = '#161b22'
    TXT      = '#c9d1d9'
    GRID     = '#30363d'
    EDGE     = '#484f58'

    @classmethod
    def _dark(cls, ax, title):
        ax.set_facecolor(cls.BG_DARK2)
        ax.tick_params(colors=cls.TXT, labelsize=8)
        for sp in ax.spines.values(): sp.set_edgecolor(cls.EDGE)
        ax.grid(True, color=cls.GRID, linewidth=0.6, alpha=0.7, axis='y')
        ax.set_title(title, color=CYAN, fontsize=10, pad=10)
        ax.xaxis.label.set_color(cls.TXT)
        ax.yaxis.label.set_color(cls.TXT)

    @classmethod
    def bar_chart(cls, labels, values, title, ylabel, path, color=YELLOW, horiz=False):
        if not HAS_MPL: return
        fig, ax = plt.subplots(figsize=(10, 5))
        fig.patch.set_facecolor(cls.BG_DARK)
        cls._dark(ax, title)
        idx = list(range(len(labels)))
        if horiz:
            bars = ax.barh(idx, values, color=color, edgecolor=cls.EDGE, linewidth=0.5)
            ax.set_yticks(idx)
            ax.set_yticklabels(labels, color=cls.TXT, fontsize=8)
            ax.set_xlabel(ylabel, color=cls.TXT)
            ax.invert_yaxis()
            for bar in bars:
                w = bar.get_width()
                ax.text(w + (max(values)*0.01 if values else 0), bar.get_y()+bar.get_height()/2,
                        '{:.2f}'.format(w), va='center', ha='left', color=cls.TXT, fontsize=7)
        else:
            bars = ax.bar(idx, values, color=color, edgecolor=cls.EDGE, linewidth=0.5)
            ax.set_xticks(idx)
            ax.set_xticklabels(labels, rotation=25, ha='right', color=cls.TXT, fontsize=8)
            ax.set_ylabel(ylabel, color=cls.TXT)
            max_v = max(values) if values and max(values) > 0 else 1
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x()+bar.get_width()/2, h+max_v*0.01,
                        '{:.2f}'.format(h), va='bottom', ha='center', color=cls.TXT, fontsize=7)
        plt.tight_layout()
        plt.savefig(path, dpi=130, bbox_inches='tight')
        plt.close('all')

    @classmethod
    def dashboard(cls, data_rows, path):
        if not HAS_MPL or not data_rows: return
        labels  = [r['label']   for r in data_rows]
        latency = [r['latency'] for r in data_rows]
        loss    = [r['loss']    for r in data_rows]
        jitter  = [r['jitter']  for r in data_rows]
        idx     = list(range(len(labels)))

        fig = plt.figure(figsize=(18, 10))
        fig.patch.set_facecolor(cls.BG_DARK)
        fig.suptitle('  CAMPUS NETWORK SDN + SD-WAN  -  BAO CAO DO LUONG MANG  ',
                     color=CYAN, fontsize=14, fontweight='bold', y=0.99,
                     bbox=dict(boxstyle='round,pad=0.4', facecolor='#1f6feb', edgecolor=CYAN, linewidth=1.2))

        gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.52, wspace=0.35,
                               left=0.05, right=0.97, top=0.93, bottom=0.30)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[0, 2])
        ax4 = fig.add_subplot(gs[1, :])

        # Chart 1: Latency
        cls._dark(ax1, 'Avg Latency (ms)')
        ax1.bar(idx, latency, color=CYAN, edgecolor=cls.EDGE, linewidth=0.5)
        ax1.set_xticks(idx); ax1.set_xticklabels(labels, rotation=35, ha='right', color=cls.TXT, fontsize=6.5)
        ax1.set_ylabel('ms', color=cls.TXT)
        for i, v in enumerate(latency):
            if v > 0: ax1.text(i, v, '{:.1f}'.format(v), ha='center', va='bottom', color=cls.TXT, fontsize=6)

        # Chart 2: Loss
        cls._dark(ax2, 'Avg Loss (%)')
        bar_c2 = [RED if v > 0 else TEAL for v in loss]
        ax2.bar(idx, loss, color=bar_c2, edgecolor=cls.EDGE, linewidth=0.5)
        ax2.set_xticks(idx); ax2.set_xticklabels(labels, rotation=35, ha='right', color=cls.TXT, fontsize=6.5)
        ax2.set_ylabel('%', color=cls.TXT)
        for i, v in enumerate(loss):
            ax2.text(i, v, '{:.1f}'.format(v), ha='center', va='bottom', color=cls.TXT, fontsize=6)

        # Chart 3: Jitter
        cls._dark(ax3, 'Avg Jitter (ms)')
        ax3.bar(idx, jitter, color=YELLOW, edgecolor=cls.EDGE, linewidth=0.5)
        ax3.set_xticks(idx); ax3.set_xticklabels(labels, rotation=35, ha='right', color=cls.TXT, fontsize=6.5)
        ax3.set_ylabel('ms', color=cls.TXT)
        for i, v in enumerate(jitter):
            if v > 0: ax3.text(i, v, '{:.1f}'.format(v), ha='center', va='bottom', color=cls.TXT, fontsize=6)

        # Table
        ax4.set_facecolor(cls.BG_DARK2); ax4.axis('off')
        ax4.set_title('Bang Tong Hop Ket Qua Do Luong', color=CYAN, fontsize=10, pad=10)
        col_hdrs = ['Tuyen duong','Avg Latency (ms)','Avg Loss (%)','Avg Jitter (ms)','Min RTT','Max RTT','QoS']
        cell_data = []
        for r in data_rows:
            if r['loss'] == 0 and r['latency'] < 50 and r['jitter'] < 10: qos = 'Tot'
            elif r['loss'] < 5 and r['latency'] < 150: qos = 'Trung binh'
            else: qos = 'Kem'
            cell_data.append([r['label'], '{:.2f}'.format(r['latency']), '{:.1f}'.format(r['loss']),
                               '{:.2f}'.format(r['jitter']), '{:.2f}'.format(r['min']),
                               '{:.2f}'.format(r['max']), qos])
        tbl = ax4.table(cellText=cell_data, colLabels=col_hdrs, loc='center', cellLoc='center')
        tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1, 1.9)
        for (row, col), cell in tbl.get_celld().items():
            cell.set_edgecolor(cls.EDGE); cell.set_linewidth(0.7)
            if row == 0:
                cell.set_facecolor('#1f6feb'); cell.set_text_props(weight='bold', color='white')
            elif col == 6:
                txt = cell.get_text().get_text()
                fc = '#1a472a' if 'Tot' in txt else ('#5c4d03' if 'Trung' in txt else '#4a1515')
                cell.set_facecolor(fc); cell.set_text_props(color='white', weight='bold')
            else:
                cell.set_facecolor(cls.BG_DARK2); cell.set_text_props(color=cls.TXT)
        fig.text(0.99, 0.01, 'Tao luc: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                 ha='right', va='bottom', color=GREY, fontsize=7)
        plt.savefig(path, dpi=140, bbox_inches='tight')
        plt.close('all')

    @classmethod
    def timeseries_chart(cls, t, latency, loss, cut_t, recover_t, title, path):
        """Bieu do Latency/Loss theo thoi gian, danh dau moc CUT (cat lien ket)
        va RECOVER (khoi phuc) – dung cho Failover Test."""
        if not HAS_MPL or not t: return
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
        fig.patch.set_facecolor(cls.BG_DARK)
        cls._dark(ax1, title + ' - Latency (ms)')
        ax1.plot(t, latency, color=CYAN, marker='o', markersize=3, linewidth=1)
        ax1.set_ylabel('ms', color=cls.TXT)
        cls._dark(ax2, 'Packet Loss (%)')
        ax2.plot(t, loss, color=RED, marker='o', markersize=3, linewidth=1)
        ax2.set_ylabel('%', color=cls.TXT); ax2.set_xlabel('Thoi gian (s)', color=cls.TXT)
        for ax in (ax1, ax2):
            if cut_t is not None:
                ax.axvline(cut_t, color=ORANGE, linestyle='--', linewidth=1.2)
            if recover_t is not None:
                ax.axvline(recover_t, color=GREEN, linestyle='--', linewidth=1.2)
        if cut_t is not None:
            ax1.text(cut_t, ax1.get_ylim()[1]*0.92, ' CUT', color=ORANGE, fontsize=8, va='top')
        if recover_t is not None:
            ax1.text(recover_t, ax1.get_ylim()[1]*0.92, ' RECOVER', color=GREEN, fontsize=8, va='top')
        fig.text(0.99, 0.01, 'Tao luc: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                 ha='right', va='bottom', color=GREY, fontsize=7)
        plt.tight_layout()
        plt.savefig(path, dpi=130, bbox_inches='tight')
        plt.close('all')

# =========================================================
#  MAIN GUI
# =========================================================
class CampusPingGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Campus Network SDN+SD-WAN  -  He Thong Do Luong Mang  v1.0')
        self.configure(bg=BG)
        self.geometry('1350x800')
        self.minsize(1100, 680)
        self.resizable(True, True)
        self._stop_event = threading.Event()
        self._ssh_client = None
        self._build_ui()
        self._boot_log()
        self._update_src_hosts()
        self._update_dst_hosts()

    # ---- UI BUILD -----------------------------------------------------------
    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill='x', padx=12, pady=(8,3))
        tk.Label(hdr, text='HE THONG DO LUONG MANG CAMPUS SDN + SD-WAN',
                 bg=BG, fg=CYAN, font=FONT_TITLE).pack(side='left')
        tk.Label(hdr, text='  |  Site 100  Site 200  Site 300  Site 400',
                 bg=BG, fg=GREY, font=('Segoe UI',9)).pack(side='left')
        tk.Label(hdr, text=datetime.now().strftime('%Y-%m-%d'),
                 bg=BG, fg=WHITE, font=FONT_UI).pack(side='right')
        content = tk.Frame(self, bg=BG)
        content.pack(fill='both', expand=True, padx=10, pady=4)
        self._build_left(content)
        self._build_center(content)
        self._build_right(content)

    def _build_left(self, parent):
        lf = tk.LabelFrame(parent, text='  Quick Ping Test  ',
                           bg=BG2, fg=YELLOW, font=FONT_UI, bd=1, relief='solid')
        lf.pack(side='left', fill='y', padx=(0,5))
        lf.configure(width=305); lf.pack_propagate(False)

        # SSH toggle
        ssh_row = tk.Frame(lf, bg=BG2); ssh_row.pack(fill='x', padx=8, pady=(6,2))
        self.ssh_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ssh_row, text='SSH Mode', variable=self.ssh_var, bg=BG2, fg=PURPLE,
                       selectcolor=BG3, activebackground=BG2, font=FONT_UI,
                       command=self._toggle_ssh).pack(side='left')
        tk.Label(ssh_row, text='(ping tu remote host)', bg=BG2, fg=GREY,
                 font=FONT_SMALL).pack(side='left', padx=6)

        self.ssh_frame = tk.LabelFrame(lf, text='  SSH Config  ', bg=BG3, fg=PURPLE,
                                       font=FONT_SMALL, bd=1, relief='solid')
        sf = tk.Frame(self.ssh_frame, bg=BG3); sf.pack(fill='x', padx=6, pady=4)
        for i, (lbl, attr, default, show) in enumerate([
            ('Host IP:', 'ssh_host', '10.215.28.26', ''),
            ('User:',    'ssh_user', 'root',        ''),
            ('Password:','ssh_pass', '#PKT@2026#',             '*'),
            ('Port:',    'ssh_port', '22',           ''),
        ]):
            tk.Label(sf, text=lbl, bg=BG3, fg=WHITE, font=FONT_SMALL, width=9,
                     anchor='w').grid(row=i, column=0, padx=2, pady=1)
            var = tk.StringVar(value=default); setattr(self, attr, var)
            tk.Entry(sf, textvariable=var, bg=BG4, fg=WHITE, insertbackground=WHITE,
                     font=('Courier New',9), show=show, width=18, relief='flat',
                     bd=1).grid(row=i, column=1, padx=4, pady=1)
        self._mkbtn(self.ssh_frame, 'Ket noi SSH', PURPLE, self._connect_ssh, full=True)
        self.ssh_lbl = tk.Label(self.ssh_frame, text='Chua ket noi', bg=BG3, fg=GREY, font=FONT_SMALL)
        self.ssh_lbl.pack(pady=(0,4))

        tk.Frame(lf, bg=BG3, height=1).pack(fill='x', padx=8, pady=4)

        # VPCS Mode toggle
        vpcs_row = tk.Frame(lf, bg=BG2); vpcs_row.pack(fill='x', padx=8, pady=(0,2))
        self.vpcs_var = tk.BooleanVar(value=False)
        tk.Checkbutton(vpcs_row, text='VPCS Mode', variable=self.vpcs_var,
                       bg=BG2, fg=TEAL, selectcolor=BG3, activebackground=BG2,
                       font=FONT_UI).pack(side='left')
        tk.Label(vpcs_row, text='(ping tu ben trong VPC node)',
                 bg=BG2, fg=GREY, font=FONT_SMALL).pack(side='left', padx=4)

        # Src / Dst
        ctrl = tk.Frame(lf, bg=BG2); ctrl.pack(fill='x', padx=8, pady=2)
        site_names = list(SITES.keys())
        rows = [
            ('Site Nguon:', 'src_site_var','src_site_cb', 0, self._update_src_hosts),
            ('Host Nguon:', 'src_var',      'src_cb',       1, None),
            ('Site Dich:',  'dst_site_var','dst_site_cb', 2, self._update_dst_hosts),
            ('Host Dich:',  'dst_var',      'dst_cb',       3, None),
        ]
        for lbl, va, ca, row, cmd in rows:
            tk.Label(ctrl, text=lbl, bg=BG2, fg=WHITE, font=FONT_UI,
                     anchor='w', width=12).grid(row=row, column=0, sticky='w', pady=3)
            var = tk.StringVar(); setattr(self, va, var)
            vals = site_names if 'site' in va else []
            cb = ttk.Combobox(ctrl, textvariable=var, values=vals, width=20, state='readonly')
            setattr(self, ca, cb)
            cb.grid(row=row, column=1, padx=4, pady=3)
            if cmd: cb.bind('<<ComboboxSelected>>', cmd)
            if 'site' in va: cb.current(0)

        tk.Label(ctrl, text='So goi:', bg=BG2, fg=WHITE, font=FONT_UI,
                 width=12, anchor='w').grid(row=4, column=0, sticky='w', pady=3)
        self.count_var = tk.IntVar(value=10)
        tk.Spinbox(ctrl, from_=4, to=300, textvariable=self.count_var, bg=BG3, fg=WHITE,
                   insertbackground=WHITE, buttonbackground=BG3, font=FONT_UI,
                   width=8, relief='flat').grid(row=4, column=1, sticky='w', padx=4)

        tk.Label(ctrl, text='Timeout (s):', bg=BG2, fg=WHITE, font=FONT_UI,
                 width=12, anchor='w').grid(row=5, column=0, sticky='w', pady=3)
        self.timeout_var = tk.IntVar(value=2)
        tk.Spinbox(ctrl, from_=1, to=10, textvariable=self.timeout_var, bg=BG3, fg=WHITE,
                   insertbackground=WHITE, buttonbackground=BG3, font=FONT_UI,
                   width=8, relief='flat').grid(row=5, column=1, sticky='w', padx=4)

        tk.Frame(lf, bg=BG3, height=1).pack(fill='x', padx=8, pady=6)
        bf = tk.Frame(lf, bg=BG2); bf.pack(fill='x', padx=8, pady=2)
        self._mkbtn(bf, 'Ping Test',      GREEN,  self._do_ping,           full=True)
        self._mkbtn(bf, 'Ping Lien Tuc', CYAN,   self._do_continuous_ping, full=True)
        self._mkbtn(bf, 'Dung',           RED,    self._stop_ping,          full=True)
        self._mkbtn(bf, 'Auto-Discover IPs', TEAL, self._do_discover,         full=True)
        tk.Frame(lf, bg=BG3, height=1).pack(fill='x', padx=8, pady=6)

        mf = tk.LabelFrame(lf, text='  Ket qua do luong  ', bg=BG3, fg=CYAN,
                           font=FONT_UI, bd=1, relief='solid')
        mf.pack(fill='x', padx=8, pady=4)
        self.metric_vars = {}
        for key, lbl, default, col in [
            ('avg_lat','Avg Latency','-- ms', CYAN),
            ('loss',   'Avg Loss',   '-- %',  RED),
            ('jitter', 'Avg Jitter', '-- ms', YELLOW),
            ('min_lat','Min RTT',    '-- ms', TEAL),
            ('max_lat','Max RTT',    '-- ms', ORANGE),
        ]:
            r = tk.Frame(mf, bg=BG3); r.pack(fill='x', padx=8, pady=3)
            tk.Label(r, text=lbl+':', bg=BG3, fg=WHITE, font=('Segoe UI',9),
                     width=14, anchor='w').pack(side='left')
            var = tk.StringVar(value=default); self.metric_vars[key] = var
            tk.Label(r, textvariable=var, bg=BG3, fg=col,
                     font=('Courier New',10,'bold')).pack(side='right', padx=6)

    def _build_center(self, parent):
        cf = tk.LabelFrame(parent, text='  KET QUA / LOGS  ', bg=BG2, fg=WHITE,
                           font=FONT_UI, bd=1, relief='solid')
        cf.pack(side='left', fill='both', expand=True, padx=5)
        self.term = scrolledtext.ScrolledText(cf, bg=BG4, fg=GREEN, font=FONT_MONO,
                                              insertbackground=GREEN, bd=0, relief='flat',
                                              wrap='word', selectbackground=BG3)
        self.term.pack(fill='both', expand=True, padx=4, pady=(4,2))
        for tag, col in [('hdr',CYAN),('ok',GREEN),('err',RED),('info',YELLOW),
                         ('data',PURPLE),('sep',GREY),('ts','#484f58')]:
            self.term.tag_config(tag, foreground=col)
        bar = tk.Frame(cf, bg=BG2); bar.pack(fill='x', padx=4, pady=(0,4))
        self._mkbtn(bar, 'Xoa Log',  GREY, self._clear_log)
        self._mkbtn(bar, 'Luu Log',  GREY, self._save_log)

    def _build_right(self, parent):
        rf = tk.LabelFrame(parent, text='  Batch Report Cases  ', bg=BG2, fg=YELLOW,
                           font=FONT_UI, bd=1, relief='solid')
        rf.pack(side='right', fill='y', padx=(5,0))
        rf.configure(width=295); rf.pack_propagate(False)

        cases = [
            ('Case 1','Ping noi bo tung Site'),
            ('Case 2','Ping lien chi nhanh (SD-WAN)'),
            ('Case 3','Bieu do Avg Latency'),
            ('Case 4','Bieu do Avg Loss (%)'),
            ('Case 5','Bieu do Avg Jitter'),
            ('Case 6','Dashboard tong hop (PNG)'),
        ]
        self.case_vars = []
        for tag, desc in cases:
            var = tk.BooleanVar(); self.case_vars.append(var)
            fr = tk.Frame(rf, bg=BG3, bd=0); fr.pack(fill='x', padx=8, pady=3)
            tk.Checkbutton(fr, variable=var, bg=BG3, fg=WHITE, selectcolor=BG3,
                           activebackground=BG3, font=FONT_UI).pack(side='left')
            tk.Label(fr, text='{}: {}'.format(tag, desc), bg=BG3, fg=WHITE,
                     font=('Segoe UI',9), wraplength=225, justify='left').pack(side='left')

        bcp = tk.Frame(rf, bg=BG2); bcp.pack(fill='x', padx=8, pady=4)
        tk.Label(bcp, text='Goi/tuyen:', bg=BG2, fg=WHITE, font=FONT_UI).pack(side='left')
        self.batch_count_var = tk.IntVar(value=10)
        tk.Spinbox(bcp, from_=4, to=200, textvariable=self.batch_count_var, bg=BG3, fg=WHITE,
                   font=FONT_UI, width=6, buttonbackground=BG3, relief='flat').pack(side='left', padx=8)

        tk.Frame(rf, bg=BG3, height=1).pack(fill='x', padx=8, pady=4)
        self._mkbtn(rf, 'Chay TAT CA Cases',   YELLOW, self._run_all_cases,  full=True)
        self._mkbtn(rf, 'Chay Cases Da Chon',  PURPLE, self._run_sel_cases,  full=True)
        self._mkbtn(rf, 'Mo Thu Muc Log',       CYAN,   self._open_log_dir,   full=True)
        tk.Frame(rf, bg=BG3, height=1).pack(fill='x', padx=8, pady=4)
        self._mkbtn(rf, 'Kiem Thu Nang Cao...', ORANGE, self._open_advanced,  full=True)
        tk.Label(rf, text='(SD-WAN Failover Test / Them VLAN Test)', bg=BG2, fg=GREY,
                 font=FONT_SMALL, wraplength=265, justify='left').pack(fill='x', padx=8)
        tk.Frame(rf, bg=BG3, height=1).pack(fill='x', padx=8, pady=4)

        self.status_var = tk.StringVar(value='San sang')
        tk.Label(rf, textvariable=self.status_var, bg=BG2, fg=GREEN,
                 font=FONT_UI, anchor='w').pack(fill='x', padx=8, pady=(4,2))
        self.progress = ttk.Progressbar(rf, mode='indeterminate', length=265)
        self.progress.pack(padx=8, pady=(0,8))
        tk.Frame(rf, bg=BG3, height=1).pack(fill='x', padx=8, pady=2)

        lgf = tk.LabelFrame(rf, text='  QoS Legend  ', bg=BG2, fg=WHITE,
                            font=FONT_SMALL, bd=1, relief='solid')
        lgf.pack(fill='x', padx=8, pady=4)
        for sym, desc, col in [
            ('Tot',        'Loss=0%, Lat<50ms, Jitter<10ms', TEAL),
            ('Trung binh', 'Loss<5%, Lat<150ms',             YELLOW),
            ('Kem',        'Loss>=5% hoac Lat>=150ms',       RED),
        ]:
            r = tk.Frame(lgf, bg=BG2); r.pack(fill='x', padx=6, pady=2)
            tk.Label(r, text=sym, bg=BG2, fg=col, font=('Segoe UI',9)).pack(side='left')
            tk.Label(r, text='  '+desc, bg=BG2, fg=WHITE, font=FONT_SMALL).pack(side='left')

    # ---- HELPERS ------------------------------------------------------------
    def _mkbtn(self, parent, text, color, cmd, full=False):
        b = tk.Button(parent, text=text, bg=BG3, fg=color, font=('Segoe UI',9,'bold'),
                      bd=0, relief='flat', activebackground='#2d333b', activeforeground=color,
                      cursor='hand2', command=cmd, pady=6, padx=10)
        b.pack(fill='x', padx=8, pady=2) if full else b.pack(side='left', padx=4, pady=3)
        return b

    def _log(self, msg, tag=None):
        self.after(0, self._log_main, msg, tag)

    def _log_main(self, msg, tag):
        ts = datetime.now().strftime('%H:%M:%S')
        if tag and tag not in ('sep','ts'):
            self.term.insert('end', '[{}] '.format(ts), 'ts')
        self.term.insert('end', msg, tag)
        self.term.see('end')

    def _clear_log(self):
        self.term.delete('1.0','end')

    def _save_log(self):
        path = os.path.join(LOG_DIR, 'log_{}.txt'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
        with open(path,'w',encoding='utf-8') as f: f.write(self.term.get('1.0','end'))
        self._log('[OK] Log luu: {}\n'.format(path),'ok')

    def _set_status(self, msg, busy=False):
        self.after(0, self._set_status_main, msg, busy)

    def _set_status_main(self, msg, busy):
        self.status_var.set(msg)
        self.progress.start(10) if busy else self.progress.stop()

    def _update_metric(self, key, val):
        self.after(0, lambda: self.metric_vars[key].set(val))

    def _reset_metrics(self):
        for k in self.metric_vars: self._update_metric(k, '--')

    def _show_metrics(self, result):
        if result.success:
            self._update_metric('avg_lat', '{:.3f} ms'.format(result.avg_latency))
            self._update_metric('loss',    '{:.1f} %'.format(result.loss))
            self._update_metric('jitter',  '{:.3f} ms'.format(result.jitter))
            self._update_metric('min_lat', '{:.3f} ms'.format(result.min_latency))
            self._update_metric('max_lat', '{:.3f} ms'.format(result.max_latency))
        else:
            for k in ('avg_lat','jitter','min_lat','max_lat'): self._update_metric(k,'N/A')
            self._update_metric('loss','100.0 %')

    def _boot_log(self):
        self._log('='*55+'\n','sep')
        self._log(' HE THONG DO LUONG MANG CAMPUS SDN + SD-WAN\n','hdr')
        self._log('='*55+'\n','sep')
        self._log(' Platform : {}\n'.format('Windows' if IS_WINDOWS else 'Linux/Unix'),'info')
        self._log(' Log dir  : {}\n'.format(LOG_DIR),'info')
        self._log(' matplotlib: {}\n'.format('OK' if HAS_MPL else 'MISSING - pip install matplotlib'),
                  'ok' if HAS_MPL else 'err')
        self._log(' paramiko  : {}\n'.format('OK' if HAS_SSH else 'optional - pip install paramiko'),
                  'ok' if HAS_SSH else 'info')
        self._log('='*55+'\n\n','sep')

    # ---- SSH ----------------------------------------------------------------
    def _toggle_ssh(self):
        if self.ssh_var.get():
            self.ssh_frame.pack(fill='x', padx=8, pady=4)
        else:
            self.ssh_frame.pack_forget()
            if self._ssh_client:
                try: self._ssh_client.close()
                except: pass
                self._ssh_client = None
                self.ssh_lbl.config(text='Chua ket noi', fg=GREY)

    def _connect_ssh(self):
        if not HAS_SSH:
            messagebox.showerror('Thieu thu vien','pip install paramiko'); return
        host=self.ssh_host.get(); user=self.ssh_user.get()
        pwd=self.ssh_pass.get(); port=int(self.ssh_port.get())
        def _do():
            try:
                import paramiko as _pm
                c = _pm.SSHClient(); c.set_missing_host_key_policy(_pm.AutoAddPolicy())
                c.connect(host, port=port, username=user, password=pwd, timeout=10)
                self._ssh_client = c
                self._log('[SSH] Ket noi OK -> {}@{}:{}\n'.format(user,host,port),'ok')
                self.after(0, lambda: self.ssh_lbl.config(text='{}@{}'.format(user,host), fg=GREEN))
                self._set_status('SSH: {}'.format(host))
            except Exception as e:
                self._log('[SSH] Loi: {}\n'.format(e),'err')
                self.after(0, lambda: self.ssh_lbl.config(text='Loi ket noi', fg=RED))
        threading.Thread(target=_do, daemon=True).start()

    # ---- HOST SELECTION -----------------------------------------------------
    def _get_site_hosts(self, site_name):
        site = SITES.get(site_name, {}); hosts = []
        for vd in site.get('vlans',{}).values(): hosts.extend(vd['hosts'].keys())
        return sorted(hosts)

    def _update_src_hosts(self, event=None):
        h = self._get_site_hosts(self.src_site_var.get())
        self.src_cb['values'] = h
        if h: self.src_cb.current(0)

    def _update_dst_hosts(self, event=None):
        h = self._get_site_hosts(self.dst_site_var.get())
        self.dst_cb['values'] = h
        if h: self.dst_cb.current(0)

    # ---- QUICK PING ---------------------------------------------------------
    def _do_ping(self):
        self._stop_event.clear()
        threading.Thread(target=self._ping_thread, daemon=True).start()

    def _do_continuous_ping(self):
        self._stop_event.clear()
        threading.Thread(target=self._continuous_ping_thread, daemon=True).start()

    def _stop_ping(self):
        self._stop_event.set(); self._set_status('San sang')

    def _ping_thread(self):
        sn=self.src_var.get(); dn=self.dst_var.get()
        dst_ip=HOST_IP.get(dn,''); count=self.count_var.get(); tmo=self.timeout_var.get()
        if not dn: self._log('[!] Chua chon host dich!\n','err'); return
        if not dst_ip: self._log('[!] Khong tim thay IP cho "{}"\n'.format(dn),'err'); return
        self._set_status('Dang ping {} -> {}...'.format(sn,dn), True)
        self._log('\n'+'='*55+'\n','sep')
        self._log('[PING] {} ({}) -> {} ({})  x{} goi\n'.format(sn,HOST_IP.get(sn,'local'),dn,dst_ip,count),'hdr')
        self._reset_metrics()
        ssh = self._ssh_client if (self.ssh_var.get() and self._ssh_client) else None
        if getattr(self, 'vpcs_var', None) and self.vpcs_var.get() and ssh:
            r = ping_via_vpcs(sn, dst_ip, count=count, ssh_client=ssh)
        else:
            r = ping_host(dst_ip, count=count, timeout_sec=tmo, ssh_client=ssh)
        self._log('+ Output:\n','info')
        for line in r.raw.strip().splitlines(): self._log('  {}\n'.format(line),'data')
        self._log('\n',None)
        if r.success:
            self._log('[OK] Ket qua do luong:\n','ok')
            self._log('  Avg Latency : {:.3f} ms\n'.format(r.avg_latency),'ok')
            self._log('  Avg Loss    : {:.1f} %\n'.format(r.loss),'ok' if r.loss==0 else 'err')
            self._log('  Avg Jitter  : {:.3f} ms\n'.format(r.jitter),'ok')
            self._log('  Min RTT     : {:.3f} ms\n'.format(r.min_latency),'ok')
            self._log('  Max RTT     : {:.3f} ms\n'.format(r.max_latency),'ok')
            if r.loss==0 and r.avg_latency<50 and r.jitter<10:   self._log('  Danh gia    : TOT\n','ok')
            elif r.loss<5 and r.avg_latency<150:                  self._log('  Danh gia    : TRUNG BINH\n','info')
            else:                                                  self._log('  Danh gia    : KEM\n','err')
        else:
            self._log('[FAIL] {} ({}) khong phan hoi!\n'.format(dn,dst_ip),'err')
        self._show_metrics(r); self._set_status('San sang')

    def _continuous_ping_thread(self):
        dn=self.dst_var.get(); dst_ip=HOST_IP.get(dn,''); tmo=self.timeout_var.get()
        if not dst_ip: self._log('[!] Chua chon host dich!\n','err'); return
        self._log('\n[PING LIEN TUC] -> {} ({}) | Nhan Dung de ngung\n'.format(dn,dst_ip),'hdr')
        self._set_status('Ping lien tuc -> {}'.format(dn), True)
        seq=0; ssh=self._ssh_client if (self.ssh_var.get() and self._ssh_client) else None
        while not self._stop_event.is_set():
            seq+=1; r=ping_host(dst_ip, count=4, timeout_sec=tmo, ssh_client=ssh)
            if r.success:
                tag='ok' if r.loss==0 else 'err'
                self._log('  #{:04d}  Lat={:7.2f} ms  Loss={:5.1f}%  Jitter={:6.2f} ms\n'.format(
                    seq,r.avg_latency,r.loss,r.jitter), tag)
                self._show_metrics(r)
            else:
                self._log('  #{:04d}  TIMEOUT - khong phan hoi\n'.format(seq),'err')
                self._update_metric('loss','100.0 %')
            for _ in range(20):
                if self._stop_event.is_set(): break
                time.sleep(0.1)
        self._log('[DUNG ping lien tuc]\n','info'); self._set_status('San sang')

    # ---- BATCH CASES --------------------------------------------------------
    def _run_all_cases(self):
        for v in self.case_vars: v.set(True)
        self._run_sel_cases()

    def _run_sel_cases(self):
        selected=[i+1 for i,v in enumerate(self.case_vars) if v.get()]
        if not selected: messagebox.showwarning('Chu y','Chon it nhat 1 Case!'); return
        threading.Thread(target=self._cases_thread, args=(selected,), daemon=True).start()

    def _cases_thread(self, cases):
        self._set_status('Dang chay Cases {}...'.format(cases), True)
        self._log('\n'+'='*55+'\n','sep')
        self._log('BAT DAU BATCH REPORT - Cases: {}\n'.format(cases),'hdr')
        ssh=self._ssh_client if (self.ssh_var.get() and self._ssh_client) else None
        count=self.batch_count_var.get(); cache={}
        for c in cases:
            self._log('\n'+'-'*40+'\n','sep')
            self._log('Case {}...\n'.format(c),'info')
            try:
                cache = getattr(self,'_case{}'.format(c))(ssh, count, cache)
            except Exception as e:
                import traceback
                self._log('[!] Loi Case {}: {}\n'.format(c,e),'err')
                self._log(traceback.format_exc()+'\n','err')
        self._set_status('Hoan thanh')
        self._log('\n'+'='*55+'\n','sep')
        self._log('HOAN THANH. Bieu do & CSV luu tai: {}\n'.format(LOG_DIR),'ok')

    def _ping_pair(self, sn, dn, count, ssh):
        dst_ip=HOST_IP.get(dn, dn); label='{}>{}'.format(sn,dn)
        if getattr(self, 'vpcs_var', None) and self.vpcs_var.get() and ssh:
            r = ping_via_vpcs(sn, dst_ip, count=count, ssh_client=ssh)
        else:
            r=ping_host(dst_ip, count=count, ssh_client=ssh)
        if r.success:
            self._log('  OK {:<35} Lat={:7.2f}ms Loss={:5.1f}% Jitter={:6.2f}ms\n'.format(
                label,r.avg_latency,r.loss,r.jitter),'ok')
            return {'label':label,'latency':r.avg_latency,'loss':r.loss,
                    'jitter':r.jitter,'min':r.min_latency,'max':r.max_latency}
        else:
            self._log('  FAIL {}\n'.format(label),'err')
            return {'label':label,'latency':0.0,'loss':100.0,'jitter':0.0,'min':0.0,'max':0.0}

    def _save_csv(self, name, data):
        path=os.path.join(LOG_DIR,'{}.csv'.format(name))
        with open(path,'w',newline='',encoding='utf-8') as f:
            w=csv.writer(f)
            w.writerow(['Tuyen_Duong','Avg_Latency_ms','Avg_Loss_pct','Avg_Jitter_ms','Min_RTT_ms','Max_RTT_ms','Thoi_gian'])
            ts=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for r in data:
                w.writerow([r['label'],round(r['latency'],3),round(r['loss'],2),
                            round(r['jitter'],3),round(r['min'],3),round(r['max'],3),ts])
        self._log('  [OK] CSV: {}\n'.format(path),'ok')

    def _case1(self, ssh, count, cache):
        pairs=[('VPC14','VPC19'),('VPC20','VPC21'),('VPC15','VPC16'),('VPC17','VPC18'),
               ('WebServer','MailServer'),('DHCP-Server','Syslog-Server'),
               ('VPC43','VPC44'),('VPC-DN1','VPC-DN2'),('VPC54','VPC-DN3'),
               ('VPC49','VPC51'),('VPC45','VPC48')]
        data=[self._ping_pair(s,d,count,ssh) for s,d in pairs]
        if HAS_MPL:
            ChartEngine.bar_chart([r['label'] for r in data],[r['latency'] for r in data],
                'Case 1 - Avg Latency Noi Bo Tung Chi Nhanh (ms)','Avg Latency (ms)',
                os.path.join(LOG_DIR,'case1_intra_latency.png'), color=CYAN)
            self._log('  [OK] PNG: case1_intra_latency.png\n','ok')
        self._save_csv('case1_intra', data); cache['intra']=data; return cache

    def _case2(self, ssh, count, cache):
        pairs=[('VPC14','VPC43'),('VPC14','VPC-DN1'),('VPC14','VPC49'),
               ('VPC20','VPC47'),('VPC15','VPC54'),('VPC17','VPC45'),
               ('VPC43','VPC-DN1'),('VPC43','VPC49'),('VPC-DN1','VPC49'),
               ('WebServer','VPC43')]
        data=[self._ping_pair(s,d,count,ssh) for s,d in pairs]
        if HAS_MPL:
            ChartEngine.bar_chart([r['label'] for r in data],[r['latency'] for r in data],
                'Case 2 - Avg Latency Lien Chi Nhanh SD-WAN (ms)','Avg Latency (ms)',
                os.path.join(LOG_DIR,'case2_inter_latency.png'), color=PURPLE)
            self._log('  [OK] PNG: case2_inter_latency.png\n','ok')
        self._save_csv('case2_inter', data); cache['inter']=data; return cache

    def _case3(self, ssh, count, cache):
        data=self._ensure_all(ssh, count, cache)
        if HAS_MPL:
            ChartEngine.bar_chart([r['label'] for r in data],[r['latency'] for r in data],
                'Case 3 - So Sanh Avg Latency Toan Mang (ms)','Avg Latency (ms)',
                os.path.join(LOG_DIR,'case3_latency.png'), color=CYAN, horiz=True)
            self._log('  [OK] PNG: case3_latency.png\n','ok')
        self._save_csv('case3_latency', data); cache['all']=data; return cache

    def _case4(self, ssh, count, cache):
        data=self._ensure_all(ssh, count, cache)
        if HAS_MPL:
            ChartEngine.bar_chart([r['label'] for r in data],[r['loss'] for r in data],
                'Case 4 - So Sanh Avg Loss % Toan Mang','Loss (%)',
                os.path.join(LOG_DIR,'case4_loss.png'), color=RED)
            self._log('  [OK] PNG: case4_loss.png\n','ok')
        self._save_csv('case4_loss', data); cache['all']=data; return cache

    def _case5(self, ssh, count, cache):
        data=self._ensure_all(ssh, count, cache)
        if HAS_MPL:
            ChartEngine.bar_chart([r['label'] for r in data],[r['jitter'] for r in data],
                'Case 5 - So Sanh Avg Jitter Toan Mang (ms)','Jitter (ms)',
                os.path.join(LOG_DIR,'case5_jitter.png'), color=YELLOW)
            self._log('  [OK] PNG: case5_jitter.png\n','ok')
        self._save_csv('case5_jitter', data); cache['all']=data; return cache

    def _case6(self, ssh, count, cache):
        data=self._ensure_all(ssh, count, cache)
        if HAS_MPL:
            path=os.path.join(LOG_DIR,'case6_dashboard.png')
            ChartEngine.dashboard(data, path)
            self._log('  [OK] Dashboard PNG: {}\n'.format(path),'ok')
        self._save_csv('case6_dashboard', data); cache['all']=data; return cache

    def _ensure_all(self, ssh, count, cache):
        if 'all' in cache:
            self._log('  [i] Su dung du lieu da co tu Case truoc.\n','info')
            return cache['all']
        self._log('  [*] Thu thap du lieu toan mang...\n','info')
        pairs=[('VPC14','VPC19'),('VPC20','VPC21'),('VPC15','VPC16'),('VPC17','VPC18'),
               ('WebServer','MailServer'),('VPC43','VPC44'),('VPC-DN1','VPC-DN2'),
               ('VPC49','VPC51'),('VPC45','VPC48'),
               ('VPC14','VPC43'),('VPC14','VPC-DN1'),('VPC14','VPC49'),
               ('VPC43','VPC-DN1'),('VPC43','VPC49'),('VPC-DN1','VPC49')]
        data=[self._ping_pair(s,d,count,ssh) for s,d in pairs]
        cache['all']=data; return data


    def _do_discover(self):
        """Auto-discover IP thực của tất cả VPC nodes."""
        ssh = self._ssh_client if (self.ssh_var.get() and self._ssh_client) else None
        if not ssh:
            messagebox.showwarning('SSH chua ket noi',
                'Vui long ket noi SSH truoc (root@10.215.28.26)\n'
                'roi moi chay Auto-Discover IPs.')
            return
        threading.Thread(target=self._discover_thread, args=(ssh,), daemon=True).start()

    def _discover_thread(self, ssh):
        self._set_status('Dang discover IP cac VPC node...', True)
        self._log('\n' + '='*55 + '\n', 'sep')
        self._log('AUTO-DISCOVER VPC IPs – Telnet vao tung node...\n', 'hdr')

        def cb(host, ip, status):
            if status == 'ok':
                self._log('  OK  {:<12} -> {}\n'.format(host, ip), 'ok')
            elif status == 'fail':
                self._log('  --  {:<12} -> khong co IP (off/chua dhcp)\n'.format(host), 'info')
            else:
                self._log('  ... {}\n'.format(host), 'data')

        results = discover_all_vpcs(ssh, callback=cb)

        self._log('\nHoan thanh! Da cap nhat {} IPs.\n'.format(len(results)), 'ok')
        self._log('IP moi co the dung ngay cho Ping Test / Batch Cases.\n', 'info')
        self._log('='*55 + '\n', 'sep')

        # Cap nhat dropdown host list
        self.after(0, self._update_src_hosts)
        self.after(0, self._update_dst_hosts)
        self._set_status('Discover xong – {} VPC co IP'.format(len(results)))

    def _open_log_dir(self):
        try:
            if IS_WINDOWS: os.startfile(LOG_DIR)
            elif platform.system()=='Darwin': subprocess.Popen(['open',LOG_DIR])
            else: subprocess.Popen(['xdg-open',LOG_DIR])
        except Exception as e:
            self._log('[!] Khong mo duoc: {}\n'.format(e),'err')

    # ---- ADVANCED TESTS (Failover / Add-VLAN) --------------------------------
    def _open_advanced(self):
        if not HAS_SSH:
            messagebox.showerror('Thieu thu vien', 'pip install paramiko'); return
        AdvancedToolsWindow(self)


# =========================================================
#  ADVANCED TOOLS WINDOW  –  SD-WAN Failover Test + Add-VLAN Test
#  Ca 2 tab deu dung self.gui._ssh_client (SSH toi host EVE-NG da ket noi
#  o man hinh chinh) + console_open/console_send/vedge_login o tren de dieu
#  khien truc tiep console Cisco IOS (Core-SW) / Viptela CLI (vEdge).
# =========================================================
class AdvancedToolsWindow(tk.Toplevel):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.title('Kiem Thu Nang Cao - Failover SD-WAN, Quan ly VLAN & Chinh sach tap trung')
        self.configure(bg=BG)
        self.geometry('960x780')
        self.minsize(860, 700)

        tk.Label(self, text='KIEM THU NANG CAO', bg=BG, fg=CYAN, font=FONT_TITLE).pack(
            anchor='w', padx=12, pady=(10, 2))
        tk.Label(self, text='Dung ket noi SSH da mo o man hinh chinh de dieu khien console thiet bi.',
                 bg=BG, fg=GREY, font=FONT_SMALL).pack(anchor='w', padx=12, pady=(0, 6))

        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.failover_tab = FailoverTab(nb, gui)
        self.vlan_tab = VlanTab(nb, gui)
        self.policy_tab = PolicyTab(nb, gui)
        nb.add(self.failover_tab, text='  SD-WAN Failover Test  ')
        nb.add(self.vlan_tab, text='  Quan ly VLAN  ')
        nb.add(self.policy_tab, text='  Chinh sach tap trung  ')


class FailoverTab(tk.Frame):
    """Tu dong shutdown 1 mau WAN tren 1 vEdge (console Viptela CLI), ping
    lien tuc qua tunnel de do RTO (Recovery Time Objective), roi tu khoi
    phuc (no shutdown). Tra loi tieu chi de bai: 'Thoi gian khoi phuc khi
    mat lien ket'."""
    def __init__(self, parent, gui):
        super().__init__(parent, bg=BG2)
        self.gui = gui
        self._build()

    def _build(self):
        tk.Label(self, bg=BG2, fg=GREY, font=FONT_SMALL, justify='left', anchor='w', wraplength=680,
                 text='Chon 1 vEdge + 1 mau WAN de cat (shutdown interface qua console), ping lien tuc '
                      'sang 1 host o site khac qua tunnel con lai, do thoi gian tu luc cat den luc ping '
                      'thong tro lai (RTO). Lien ket duoc TU DONG khoi phuc (no shutdown) sau khi test, '
                      'du thanh cong hay loi.'
                 ).pack(fill='x', padx=10, pady=(10, 6))

        row = tk.Frame(self, bg=BG2); row.pack(fill='x', padx=10, pady=2)

        tk.Label(row, text='vEdge nguon:', bg=BG2, fg=WHITE, width=16, anchor='w').grid(
            row=0, column=0, sticky='w', pady=4)
        self.vedge_var = tk.StringVar(value='vEdge1-S200')
        self.vedge_cb = ttk.Combobox(row, textvariable=self.vedge_var, values=sorted(WAN_IFACE.keys()),
                                      width=18, state='readonly')
        self.vedge_cb.grid(row=0, column=1, padx=4, pady=4, sticky='w')
        self.vedge_cb.bind('<<ComboboxSelected>>', self._update_colors)

        tk.Label(row, text='Mau WAN cat:', bg=BG2, fg=WHITE, width=16, anchor='w').grid(
            row=1, column=0, sticky='w', pady=4)
        self.color_var = tk.StringVar()
        self.color_cb = ttk.Combobox(row, textvariable=self.color_var, width=18, state='readonly')
        self.color_cb.grid(row=1, column=1, padx=4, pady=4, sticky='w')

        tk.Label(row, text='Ping tu (VPC nguon):', bg=BG2, fg=WHITE, width=16, anchor='w').grid(
            row=2, column=0, sticky='w', pady=4)
        self.src_var = tk.StringVar()
        self.src_cb = ttk.Combobox(row, textvariable=self.src_var, width=18, state='readonly')
        self.src_cb.grid(row=2, column=1, padx=4, pady=4, sticky='w')
        tk.Label(row, text='(chieu ping nguon->dich phai di qua vEdge bi cat)', bg=BG2,
                 fg=GREY, font=FONT_SMALL).grid(row=2, column=2, sticky='w', padx=6)

        tk.Label(row, text='Ping toi (IP dich):', bg=BG2, fg=WHITE, width=16, anchor='w').grid(
            row=5, column=0, sticky='w', pady=4)
        self.target_var = tk.StringVar(value='10.1.10.1')
        tk.Entry(row, textvariable=self.target_var, bg=BG3, fg=WHITE, insertbackground=WHITE,
                 width=20).grid(row=5, column=1, padx=4, pady=4, sticky='w')
        tk.Label(row, text='(host o site khac; KHONG dung system-ip 10.200.x - khong ping duoc)', bg=BG2,
                 fg=GREY, font=FONT_SMALL).grid(row=5, column=2, sticky='w', padx=6)

        tk.Label(row, text='Giam sat sau cat (s):', bg=BG2, fg=WHITE, width=16, anchor='w').grid(
            row=3, column=0, sticky='w', pady=4)
        self.duration_var = tk.IntVar(value=60)
        tk.Spinbox(row, from_=20, to=300, textvariable=self.duration_var, width=8, bg=BG3, fg=WHITE,
                   insertbackground=WHITE, buttonbackground=BG3, relief='flat').grid(
            row=3, column=1, padx=4, pady=4, sticky='w')

        tk.Label(row, text='User / Pass vEdge:', bg=BG2, fg=WHITE, width=16, anchor='w').grid(
            row=4, column=0, sticky='w', pady=4)
        upf = tk.Frame(row, bg=BG2); upf.grid(row=4, column=1, sticky='w')
        self.vuser_var = tk.StringVar(value='admin')
        self.vpass_var = tk.StringVar(value='vnpro@123')
        tk.Entry(upf, textvariable=self.vuser_var, width=9, bg=BG3, fg=WHITE,
                 insertbackground=WHITE, relief='flat').pack(side='left', padx=2)
        tk.Entry(upf, textvariable=self.vpass_var, width=9, bg=BG3, fg=WHITE,
                 insertbackground=WHITE, show='*', relief='flat').pack(side='left', padx=2)

        self.confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self, text='Toi hieu day la shutdown/no-shutdown THAT tren vEdge trong lab cua toi',
                       variable=self.confirm_var, bg=BG2, fg=YELLOW, selectcolor=BG3,
                       activebackground=BG2, font=FONT_UI).pack(anchor='w', padx=10, pady=(8, 2))

        bf = tk.Frame(self, bg=BG2); bf.pack(fill='x', padx=10, pady=6)
        tk.Button(bf, text='Chay Failover Test', bg=BG3, fg=ORANGE, font=('Segoe UI', 9, 'bold'),
                  bd=0, relief='flat', activebackground='#2d333b', cursor='hand2',
                  command=self._run, pady=6, padx=10).pack(side='left', padx=4)
        tk.Button(bf, text='Khoi Phuc Ngay (no shutdown)', bg=BG3, fg=GREEN, font=('Segoe UI', 9, 'bold'),
                  bd=0, relief='flat', activebackground='#2d333b', cursor='hand2',
                  command=self._restore_now, pady=6, padx=10).pack(side='left', padx=4)

        self._update_colors()

    @staticmethod
    def _site_of(vname):
        m = re.search(r'S(\d+)$', vname)
        return int(m.group(1)) if m else None

    def _update_colors(self, event=None):
        vname = self.vedge_var.get()
        colors = list(WAN_IFACE.get(vname, {}).keys())
        self.color_cb['values'] = colors
        if colors: self.color_var.set(colors[0])
        sid = self._site_of(vname)
        same = sorted(h for h in VPC_NODE_IDS if h in HOST_SITE and SITES[HOST_SITE[h]]['site_id'] == sid)
        srcs = same + sorted(h for h in VPC_NODE_IDS if h in HOST_SITE and h not in same)
        self.src_cb['values'] = srcs
        if event is not None or self.src_var.get() not in srcs:
            # mac dinh: VPC cung site; site 100 (SDN) mac dinh VPC43 vi traffic tu Can Tho ve
            # campus cung di qua vEdge-S100 bi cat
            self.src_var.set('VPC43' if sid == CORE_SITE_ID else (srcs[0] if srcs else ''))
        if event is not None:
            # dich mac dinh: gateway VLAN 10 campus (VPC nguon mac dinh luon o chi nhanh)
            self.target_var.set('10.1.10.1')

    def _run(self):
        if not self.confirm_var.get():
            messagebox.showwarning('Xac nhan truoc khi chay',
                'Vui long tick "Toi hieu day la shutdown/no-shutdown THAT..." truoc khi chay test.')
            return
        ssh = self.gui._ssh_client
        if not ssh:
            messagebox.showerror('Chua SSH', 'Ket noi SSH (man hinh chinh, SSH Mode) truoc khi chay test nay.')
            return
        target = self.target_var.get().strip()
        try:
            ipaddress.ip_address(target)
        except ValueError:
            messagebox.showerror('IP dich sai', '"{}" khong phai dia chi IP.'.format(target)); return
        sysips = {ip: n for d in SITE_VEDGES.values() for ip, n in d.items()}
        if target in sysips:
            messagebox.showerror('IP dich la system-ip',
                '{} la system-ip cua {} - chi la ma dinh danh trong fabric, KHONG ping duoc.\n'
                'Hay ping 1 host/gateway o site khac (vd 10.1.10.1, 10.3.80.100).'.format(target, sysips[target]))
            return
        if not self.src_var.get():
            messagebox.showerror('Thieu VPC nguon', 'Site cua vEdge nay khong co VPC trong danh sach.'); return
        threading.Thread(target=self._thread, args=(ssh,), daemon=True).start()

    def _restore_now(self):
        ssh = self.gui._ssh_client
        if not ssh:
            messagebox.showerror('Chua SSH', 'Ket noi SSH (man hinh chinh) truoc.'); return
        vname = self.vedge_var.get(); color = self.color_var.get()
        iface = WAN_IFACE.get(vname, {}).get(color)
        if not iface:
            messagebox.showerror('Thieu tham so', 'vEdge nay khong co mau "{}"'.format(color)); return
        threading.Thread(target=self._restore_thread, args=(ssh, vname, iface), daemon=True).start()

    def _restore_thread(self, ssh, vname, iface):
        log = self.gui._log
        log('[FAILOVER] Khoi phuc thu cong {} interface {}...\n'.format(vname, iface), 'info')
        try:
            vedge_config(ssh, VEDGE_NODE_IDS[vname], self.vuser_var.get(), self.vpass_var.get(),
                         ['vpn 0 interface {}'.format(iface), 'no shutdown'])
            log('[FAILOVER] Da no-shutdown (Commit complete) {} {}\n'.format(vname, iface), 'ok')
        except Exception as e:
            log('[FAILOVER] Loi khoi phuc: {}\n'.format(e), 'err')

    def _thread(self, ssh):
        log = self.gui._log
        vname = self.vedge_var.get(); color = self.color_var.get()
        iface = WAN_IFACE.get(vname, {}).get(color)
        target = self.target_var.get().strip()
        src = self.src_var.get()
        duration = self.duration_var.get()
        node_id = VEDGE_NODE_IDS.get(vname)
        user, pwd = self.vuser_var.get(), self.vpass_var.get()

        if not iface or not target or not node_id or src not in VPC_NODE_IDS:
            log('[FAILOVER] Thieu tham so (vEdge/mau WAN/VPC nguon/IP dich)\n', 'err'); return

        log('\n' + '='*55 + '\n', 'sep')
        log('[FAILOVER TEST] {} - cat mau "{}" (interface {}) | ping {} -> {}\n'.format(
            vname, color, iface, src, target), 'hdr')

        samples = []
        t_start = time.time()
        cut_t = None
        recover_t = None
        vpc = None
        cut_done = False
        saw_loss = False     # co goi nao mat SAU khi cat khong
        no_outage = False    # cat xong ma suot thoi gian giam sat khong mat goi nao

        def sample():
            """1 goi ping tu VPC nguon (console VPCS) -> (elapsed, latency, loss)."""
            r = PingResult()
            _parse_vpcs_ping(r, vpcs_cmd(vpc, 'ping {} -c 1'.format(target)))
            el = time.time() - t_start
            samples.append((el, r.avg_latency if r.success else 0.0, r.loss))
            return el, r

        try:
            vpc = console_open(ssh, VPC_NODE_IDS[src])
            vpc.send('\n'); time.sleep(0.4); _flush_chan(vpc)

            log('  [*] Baseline (6 goi) tu {} truoc khi cat...\n'.format(src), 'info')
            ok_base = 0
            for _ in range(6):
                el, r = sample()
                ok_base += r.success
                log('    t={:6.1f}s  Lat={:6.2f}ms  Loss={:5.1f}%\n'.format(el, r.avg_latency, r.loss),
                    'ok' if r.success else 'err')
            if ok_base < 3:
                log('  [!] Baseline chi {}/6 goi thong -> KHONG cat WAN (test vo nghia khi chua ping duoc).\n'
                    '      Kiem tra: {} co IP chua (show ip), {} co ton tai/ping duoc tu site nay khong.\n'.format(
                        ok_base, src, target), 'err')
                return

            log('  [*] Dang gui lenh shutdown {} tren {}...\n'.format(iface, vname), 'info')
            cut_done = True      # tu day tro di LUON khoi phuc, ke ca khi commit loi giua chung
            vedge_config(ssh, node_id, user, pwd, ['vpn 0 interface {}'.format(iface), 'shutdown'])
            cut_t = time.time() - t_start
            log('  [CUT] Da cat mau "{}" luc t={:.1f}s (vEdge xac nhan Commit complete)\n'.format(color, cut_t), 'err')

            consecutive_ok = 0
            while (time.time() - t_start) < cut_t + duration:
                el, r = sample()
                log('    t={:6.1f}s  Lat={:6.2f}ms  Loss={:5.1f}%\n'.format(el, r.avg_latency, r.loss),
                    'ok' if r.success else 'err')
                if r.success:
                    consecutive_ok += 1
                    if consecutive_ok >= 3 and saw_loss:
                        recover_t = samples[-3][0]   # goi dau tien cua chuoi thong lien tiep
                        log('  [RECOVER] Thong tro lai tu t={:.1f}s (RTO={:.1f}s)\n'.format(
                            recover_t, recover_t - cut_t), 'ok')
                        break
                else:
                    consecutive_ok = 0
                    saw_loss = True
            no_outage = not saw_loss
        except Exception as e:
            log('  [!] Loi trong qua trinh test: {}\n'.format(e), 'err')
        finally:
            if vpc is not None:
                try: vpc.close()
                except Exception: pass
            # LUON khoi phuc lien ket neu da gui lenh cat, du test thanh cong hay loi giua duong
            if cut_done:
                try:
                    vedge_config(ssh, node_id, user, pwd, ['vpn 0 interface {}'.format(iface), 'no shutdown'])
                    log('  [OK] Da khoi phuc (no-shutdown, Commit complete) {} tren {}\n'.format(iface, vname), 'ok')
                except Exception as e:
                    log('  [!] KHONG khoi phuc duoc tu dong ({}) -> bam "Khoi Phuc Ngay"!\n'.format(e), 'err')

        if not cut_done:
            log('=' * 55 + '\n\n', 'sep'); return
        if no_outage:
            log('  [!] KHONG MAT GOI NAO trong {}s sau khi cat mau "{}" cua {} -> KHONG do duoc RTO.\n'
                '      Co 2 kha nang: (1) luong ping khong di qua mau nay (vd FW chi nhanh dung vEdge1 lam\n'
                '      default, hoac tunnel cheo mau dang mang luong) -> cat mau khac hoac doi VPC/dich;\n'
                '      (2) chuyen duong nhanh hon chu ky lay mau ~1.2s (vEdge rut TLOC qua OMP ngay khi\n'
                '      interface down) -> ghi nhan "gian doan < 1.2s", khong phai RTO = 0.\n'.format(
                    duration, color, vname), 'err')
        elif recover_t is None:
            log('  [!] Khong ghi nhan khoi phuc trong {}s sau khi cat.\n'.format(duration), 'err')
            if len(WAN_IFACE.get(vname, {})) == 1:
                log('  [i] {} chi co 1 mau WAN: cat mau nay = vEdge mat het tunnel. Neu FW chi nhanh dung\n'
                    '      static route uu tien vEdge nay ma KHONG co "sla monitor"/"track", FW van day\n'
                    '      traffic vao vEdge da chet -> khong tu chuyen sang vEdge con lai.\n'.format(vname), 'info')

        ts = [s[0] for s in samples]; lats = [s[1] for s in samples]; losses = [s[2] for s in samples]
        base = 'failover_{}_{}_{}'.format(vname, color, datetime.now().strftime('%Y%m%d_%H%M%S'))
        csv_path = os.path.join(LOG_DIR, base + '.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['Elapsed_s', 'Avg_Latency_ms', 'Loss_pct'])
            for row in samples:
                w.writerow([round(row[0], 2), round(row[1], 3), round(row[2], 2)])
        log('  [OK] CSV: {}\n'.format(csv_path), 'ok')
        if HAS_MPL:
            png_path = os.path.join(LOG_DIR, base + '.png')
            ChartEngine.timeseries_chart(ts, lats, losses, cut_t, recover_t,
                'Failover {} - {}'.format(vname, color), png_path)
            log('  [OK] PNG: {}\n'.format(png_path), 'ok')
        if recover_t is not None:
            log('  === RTO (Recovery Time Objective) = {:.1f} giay ===\n'.format(recover_t - cut_t), 'hdr')
        log('=' * 55 + '\n\n', 'sep')


VLAN_REGISTRY = os.path.join(LOG_DIR, 'vlan_registry.json')
VLAN_OPS_CSV  = 'case_vlan_ops.csv'
VLAN_OPS_COLS = ['action', 'vlan_id', 'name', 'subnet', 'gateway', 'config_time_s', 'svi_up_s',
                 'fw_ospf_s', 'sdwan_check_s', 'e2e_s', 'remote_host', 'omp_route', 'bfd_up',
                 'via_sdwan', 'path', 'timestamp']
VERIFY_TIMEOUT = 90   # giay cho moi moc kiem chung


def vlan_network(cfg):
    """Subnet cua VLAN tu IP SVI Core-SW1 + prefix (vd 10.1.50.2/24 -> 10.1.50.0/24)."""
    return ipaddress.ip_interface('{}/{}'.format(cfg['ip1'], cfg['prefix'])).network


def ospf_network_cmd(net, remove=False):
    return '{}network {} {} area 0'.format('no ' if remove else '', net.network_address, net.hostmask)


class VlanTab(tk.Frame):
    """Quan ly VLAN + SVI (+VRRP du phong) tren Core-SW1/2 (console Cisco IOS):
    Them / Sua / Xoa / Khoi phuc, kem dua subnet vao OSPF de FW-ASAv hoc
    duong ve va SD-WAN (route tong 10.1.0.0/16 qua OMP) mang VLAN sang site
    khac. Sau moi thao tac, tool KIEM CHUNG va DO thoi gian (tinh tu luc gui
    lenh), 4 moc chay song song:
      T1 SVI up/up tren Core-SW1
      T2 FW-ASAv Active hoc (hoac go) route OSPF cua subnet
      T3 vManage API (chi GET): vEdge site dich co route OMP phu subnet (C,I)
         + BFD up toi site 100
      T4 VPC o site khac ping thong (hoac mat) toi SVI; traceroute chung minh
         di qua vEdge (overlay SD-WAN)
    Tra loi tieu chi de bai: 'Thoi gian them moi VLAN hoac khu vuc mang'.
      * Danh sach VLAN do tool quan ly luu o log/vlan_registry.json (kem lich
        su cau hinh cu) de Sua / Khoi phuc ca sau khi dong tool.
      * Xoa = xoa tren thiet bi nhung GIU ban sao cau hinh -> Khoi phuc tao lai.
      * Khoi phuc tren VLAN dang active = hoan tac lan Sua gan nhat.
    Ket qua: log/case_vlan_ops.csv (moi thao tac) + PNG timeline; Them con ghi
    log/case_addvlan.csv (dinh dang cu)."""
    def __init__(self, parent, gui):
        super().__init__(parent, bg=BG2)
        self.gui = gui
        self._busy = False
        self.registry = self._load_registry()
        self._build()
        self._refresh_tree()

    # ---- registry (JSON) ----------------------------------------------------
    @staticmethod
    def _load_registry():
        try:
            with open(VLAN_REGISTRY, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_registry(self):
        with open(VLAN_REGISTRY, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    # ---- UI -----------------------------------------------------------------
    def _build(self):
        tk.Label(self, bg=BG2, fg=GREY, font=FONT_SMALL, justify='left', anchor='w', wraplength=880,
                 text='Quan ly VLAN + SVI tren Core-SW1 (va Core-SW2 neu chon VRRP) qua console, tu dua subnet '
                      'vao OSPF de FW-ASAv hoc duong ve; SD-WAN mang VLAN sang site khac qua route tong '
                      '10.1.0.0/16 (OMP). Sau moi thao tac tool do: T1 SVI up, T2 FW hoc OSPF, T3 vManage '
                      'xac nhan OMP+BFD, T4 VPC site khac ping thong + traceroute qua vEdge. Chon 1 dong de '
                      'Sua / Xoa / Khoi phuc; Khoi phuc tren VLAN active = hoan tac lan Sua gan nhat.'
                 ).pack(fill='x', padx=10, pady=(10, 6))

        body = tk.Frame(self, bg=BG2); body.pack(fill='both', expand=True, padx=10)

        form = tk.Frame(body, bg=BG2); form.pack(side='left', fill='y', anchor='n')
        fields = [
            ('VLAN ID:', 'vid_var', '50'),
            ('Ten VLAN:', 'name_var', 'TEST_VLAN'),
            ('IP Core-SW1 (SVI):', 'ip1_var', '10.1.50.2'),
            ('IP Core-SW2 (SVI):', 'ip2_var', '10.1.50.3'),
            ('VRRP VIP (Gateway):', 'vip_var', '10.1.50.1'),
            ('Prefix (CIDR):', 'prefix_var', '24'),
            ('VRRP Group ID:', 'vrid_var', '50'),
        ]
        for i, (lbl, attr, default) in enumerate(fields):
            tk.Label(form, text=lbl, bg=BG2, fg=WHITE, width=18, anchor='w').grid(
                row=i, column=0, sticky='w', pady=2)
            var = tk.StringVar(value=default); setattr(self, attr, var)
            tk.Entry(form, textvariable=var, bg=BG3, fg=WHITE, insertbackground=WHITE,
                     width=18, relief='flat').grid(row=i, column=1, padx=4, pady=2, sticky='w')

        self.dual_var = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text='Ca Core-SW1 + Core-SW2 (VRRP)', variable=self.dual_var,
                       bg=BG2, fg=TEAL, selectcolor=BG3, activebackground=BG2,
                       font=FONT_UI).grid(row=len(fields), column=0, columnspan=2, sticky='w', pady=(4, 0))
        self.wr_var = tk.BooleanVar(value=False)
        tk.Checkbutton(form, text='Luu cau hinh (write memory)', variable=self.wr_var,
                       bg=BG2, fg=TEAL, selectcolor=BG3, activebackground=BG2,
                       font=FONT_UI).grid(row=len(fields) + 1, column=0, columnspan=2, sticky='w')

        lf = tk.Frame(body, bg=BG2); lf.pack(side='left', fill='both', expand=True, padx=(12, 0))
        tk.Label(lf, text='VLAN do tool quan ly', bg=BG2, fg=CYAN,
                 font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        cols = ('vid', 'name', 'subnet', 'vip', 'core', 'status', 'updated')
        heads = ('VLAN', 'Ten', 'Subnet', 'Gateway', 'Core-SW', 'Trang thai', 'Cap nhat')
        widths = (45, 100, 105, 90, 60, 85, 125)
        self.tree = ttk.Treeview(lf, columns=cols, show='headings', height=9, selectmode='browse')
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h); self.tree.column(c, width=w, anchor='w')
        self.tree.tag_configure('deleted', foreground=GREY)
        self.tree.pack(fill='both', expand=True, pady=(2, 0))
        self.tree.bind('<<TreeviewSelect>>', self._on_select)

        # ---- kiem chung SD-WAN ----
        vf = tk.LabelFrame(self, text=' Kiem chung qua SD-WAN ', bg=BG2, fg=CYAN,
                           font=('Segoe UI', 9, 'bold'), bd=1, relief='groove')
        vf.pack(fill='x', padx=10, pady=(8, 0))
        self.verify_var = tk.BooleanVar(value=True)
        tk.Checkbutton(vf, text='Bat kiem chung (T2 FW / T3 vManage / T4 ping lien site)',
                       variable=self.verify_var, bg=BG2, fg=TEAL, selectcolor=BG3,
                       activebackground=BG2, font=FONT_UI).grid(row=0, column=0, columnspan=6, sticky='w')
        remotes = sorted(h for h in VPC_NODE_IDS
                         if h in HOST_SITE and SITES[HOST_SITE[h]]['site_id'] != CORE_SITE_ID)
        self.remote_var = tk.StringVar(value='VPC43' if 'VPC43' in remotes else (remotes[0] if remotes else ''))
        self.fw_pw_var = tk.StringVar(value='')
        self.vm_user_var = tk.StringVar(value='admin')
        self.vm_pw_var = tk.StringVar(value='')
        row = [('VPC site khac:', None), ('FW enable pass:', self.fw_pw_var),
               ('vManage user:', self.vm_user_var), ('vManage pass:', self.vm_pw_var)]
        for i, (lbl, var) in enumerate(row):
            r, c = 1 + i // 2, (i % 2) * 2
            tk.Label(vf, text=lbl, bg=BG2, fg=WHITE, width=15, anchor='w').grid(row=r, column=c, sticky='w', padx=(4, 0), pady=2)
            if var is None:
                ttk.Combobox(vf, textvariable=self.remote_var, values=remotes, width=16,
                             state='readonly').grid(row=r, column=c + 1, sticky='w', padx=4)
            else:
                tk.Entry(vf, textvariable=var, bg=BG3, fg=WHITE, insertbackground=WHITE, width=18,
                         relief='flat', show='*' if 'pass' in lbl else '').grid(row=r, column=c + 1, sticky='w', padx=4)
        tk.Label(vf, bg=BG2, fg=GREY, font=FONT_SMALL, anchor='w',
                 text='De trong FW pass neu console FW da o "#"; de trong vManage pass = bo qua T3.').grid(
            row=3, column=0, columnspan=6, sticky='w', padx=4, pady=(0, 4))

        bf = tk.Frame(self, bg=BG2); bf.pack(fill='x', padx=10, pady=8)
        for text, color, cmd in [('Them VLAN', YELLOW, self._add),
                                 ('Sua VLAN', CYAN, self._edit),
                                 ('Xoa VLAN', RED, self._delete),
                                 ('Khoi phuc', TEAL, self._restore),
                                 ('Bo khoi danh sach', GREY, self._forget)]:
            tk.Button(bf, text=text, bg=BG3, fg=color, font=('Segoe UI', 9, 'bold'),
                      bd=0, relief='flat', activebackground='#2d333b', cursor='hand2',
                      command=cmd, pady=6, padx=10).pack(side='left', padx=4)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for key in sorted(self.registry, key=int):
            e = self.registry[key]
            deleted = e['status'] == 'deleted'
            status = 'Da xoa' if deleted else 'Active'
            if not deleted and e.get('history'):
                status += ' (sua {})'.format(len(e['history']))
            self.tree.insert('', 'end', iid=key, tags=('deleted',) if deleted else (),
                             values=(key, e['cfg']['name'], str(vlan_network(e['cfg'])), e['cfg']['vip'] or '-',
                                     '1+2' if e['cfg']['dual'] else '1',
                                     status, e.get('updated', '')))

    def _on_select(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        cfg = self.registry[sel[0]]['cfg']
        self.vid_var.set(sel[0])
        for k in ('name', 'ip1', 'ip2', 'vip', 'prefix', 'vrid'):
            getattr(self, k + '_var').set(cfg[k])
        self.dual_var.set(cfg['dual'])

    def _read_form(self):
        """Doc + kiem tra form -> (vid, cfg). Nem ValueError neu sai."""
        vid = int(self.vid_var.get())
        if not 1 <= vid <= 4094:
            raise ValueError('VLAN ID phai trong khoang 1-4094')
        cfg = {'name': self.name_var.get().strip() or 'TEST_VLAN',
               'ip1': self.ip1_var.get().strip(), 'ip2': self.ip2_var.get().strip(),
               'vip': self.vip_var.get().strip(), 'prefix': self.prefix_var.get().strip(),
               'vrid': self.vrid_var.get().strip(), 'dual': bool(self.dual_var.get())}
        if not 8 <= int(cfg['prefix']) <= 30:
            raise ValueError('Prefix phai trong khoang 8-30')
        net = vlan_network(cfg)   # nem ValueError neu IP sai
        for k in ('ip2', 'vip') if cfg['dual'] else ('vip',):
            if cfg[k] and ipaddress.ip_address(cfg[k]) not in net:
                raise ValueError('{} ({}) khong thuoc subnet {}'.format(k, cfg[k], net))
        if cfg['dual'] and not cfg['ip2']:
            raise ValueError('Thieu IP SVI Core-SW2')
        if cfg['vip'] and not cfg['vrid']:
            raise ValueError('Co VRRP VIP thi phai co VRRP Group ID')
        return vid, cfg

    def _read_opts(self):
        """Tuy chon kiem chung (doc o main thread, truyen vao worker)."""
        return {'verify': bool(self.verify_var.get()), 'remote': self.remote_var.get(),
                'fw_pw': self.fw_pw_var.get(), 'vm_user': self.vm_user_var.get().strip() or 'admin',
                'vm_pw': self.vm_pw_var.get(), 'wr': bool(self.wr_var.get())}

    # ---- button handlers (main thread) --------------------------------------
    def _start(self, target, *args):
        ssh = self.gui._ssh_client
        if not ssh:
            messagebox.showerror('Chua SSH', 'Ket noi SSH (man hinh chinh, SSH Mode) truoc khi thao tac.')
            return
        if self._busy:
            messagebox.showwarning('Dang chay', 'Dang co thao tac VLAN khac, vui long doi.'); return
        self._busy = True
        opts = self._read_opts()

        def _run():
            try: target(ssh, opts, *args)
            except Exception as e: self.gui._log('[VLAN] Loi: {}\n'.format(e), 'err')
            finally: self._busy = False
        threading.Thread(target=_run, daemon=True).start()

    def _add(self):
        try: vid, cfg = self._read_form()
        except ValueError as e:
            messagebox.showerror('Tham so khong hop le', str(e)); return
        e = self.registry.get(str(vid))
        if e and e['status'] == 'active':
            messagebox.showerror('Da ton tai', 'VLAN {} dang active. Dung "Sua VLAN" de thay doi.'.format(vid))
            return
        self._start(self._add_thread, vid, cfg)

    def _edit(self):
        try: vid, cfg = self._read_form()
        except ValueError as e:
            messagebox.showerror('Tham so khong hop le', str(e)); return
        e = self.registry.get(str(vid))
        if not e or e['status'] != 'active':
            messagebox.showerror('Khong tim thay',
                                 'VLAN {} khong co trong danh sach active (VLAN ID khong the sua; '
                                 'muon doi ID hay Xoa roi Them moi).'.format(vid)); return
        if cfg == e['cfg']:
            messagebox.showinfo('Khong doi', 'Cau hinh khong thay doi.'); return
        if not messagebox.askyesno('Xac nhan sua', 'Ap dung cau hinh moi cho VLAN {}?'.format(vid)): return
        self._start(self._edit_thread, vid, e['cfg'], cfg, True)

    def _delete(self):
        try: vid = int(self.vid_var.get())
        except ValueError:
            messagebox.showerror('Loi', 'VLAN ID khong hop le.'); return
        e = self.registry.get(str(vid))
        if e and e['status'] == 'deleted':
            messagebox.showinfo('Da xoa', 'VLAN {} da bi xoa truoc do.'.format(vid)); return
        if e:
            cfg = e['cfg']
        else:
            try: cfg = self._read_form()[1]
            except ValueError as ex:
                messagebox.showerror('Tham so khong hop le', 'Can IP/prefix dung de go OSPF: {}'.format(ex)); return
        msg = 'Xoa VLAN {} + SVI + OSPF network {} tren Core-SW1/2?'.format(vid, vlan_network(cfg))
        if not e:
            msg += '\n\nVLAN nay KHONG co trong danh sach -> khong the Khoi phuc sau khi xoa.'
        if not messagebox.askyesno('Xac nhan xoa', msg): return
        self._start(self._delete_thread, vid, cfg)

    def _restore(self):
        sel = self.tree.selection()
        key = sel[0] if sel else self.vid_var.get().strip()
        e = self.registry.get(key)
        if not e:
            messagebox.showerror('Khong tim thay', 'Chon 1 VLAN trong danh sach de khoi phuc.'); return
        if e['status'] == 'deleted':
            if not messagebox.askyesno('Khoi phuc', 'Tao lai VLAN {} ({}) voi cau hinh truoc khi xoa?'.format(
                    key, e['cfg']['name'])): return
            self._start(self._add_thread, int(key), dict(e['cfg']), True)
        elif e.get('history'):
            if not messagebox.askyesno('Khoi phuc', 'Hoan tac lan sua gan nhat cua VLAN {}?'.format(key)): return
            self._start(self._edit_thread, int(key), e['cfg'], dict(e['history'][-1]), False)
        else:
            messagebox.showinfo('Khong co gi de khoi phuc',
                                'VLAN {} dang active va chua tung bi sua.'.format(key))

    def _forget(self):
        sel = self.tree.selection()
        if not sel: return
        key = sel[0]
        if self.registry[key]['status'] == 'active' and not messagebox.askyesno(
                'Xac nhan', 'VLAN {} van dang active tren thiet bi. Chi bo khoi danh sach '
                            '(khong dong vao thiet bi)?'.format(key)): return
        del self.registry[key]
        self._save_registry(); self._refresh_tree()

    # ---- device commands -----------------------------------------------------
    @staticmethod
    def _targets(cfg):
        t = [('Core-SW1', CORE_SW_NODE_IDS['Core-SW1'], cfg['ip1'], 110)]
        if cfg['dual']:
            t.append(('Core-SW2', CORE_SW_NODE_IDS['Core-SW2'], cfg['ip2'], 90))
        return t

    @staticmethod
    def _tail(cmds, wr):
        return cmds + ['end'] + (['write memory'] if wr else [])

    @classmethod
    def _core_cmds_add(cls, vid, cfg, ip, priority, wr=False):
        cmds = ['', 'enable', 'configure terminal',
                'vlan {}'.format(vid), 'name {}'.format(cfg['name']), 'exit',
                'interface vlan {}'.format(vid),
                'description AUTO-TEST-{}'.format(cfg['name']),
                'ip address {} {}'.format(ip, cidr_to_mask(cfg['prefix']))]
        if cfg['vip']:
            cmds += ['vrrp {} ip {}'.format(cfg['vrid'], cfg['vip']),
                     'vrrp {} priority {}'.format(cfg['vrid'], priority)]
        cmds += ['no shutdown', 'exit',
                 'router ospf {}'.format(CORE_OSPF_PID), ospf_network_cmd(vlan_network(cfg)), 'exit']
        return cls._tail(cmds, wr)

    @classmethod
    def _core_cmds_edit(cls, vid, old, new, ip, priority, wr=False):
        cmds = ['', 'enable', 'configure terminal']
        if new['name'] != old['name']:
            cmds += ['vlan {}'.format(vid), 'name {}'.format(new['name']), 'exit']
        cmds += ['interface vlan {}'.format(vid),
                 'description AUTO-TEST-{}'.format(new['name']),
                 'ip address {} {}'.format(ip, cidr_to_mask(new['prefix']))]
        if old['vip'] and (old['vip'], old['vrid']) != (new['vip'], new['vrid']):
            cmds.append('no vrrp {}'.format(old['vrid']))
        if new['vip']:
            cmds += ['vrrp {} ip {}'.format(new['vrid'], new['vip']),
                     'vrrp {} priority {}'.format(new['vrid'], priority)]
        cmds += ['no shutdown', 'exit']
        old_net, new_net = vlan_network(old), vlan_network(new)
        if old_net != new_net:
            cmds += ['router ospf {}'.format(CORE_OSPF_PID), ospf_network_cmd(old_net, remove=True),
                     ospf_network_cmd(new_net), 'exit']
        return cls._tail(cmds, wr)

    @classmethod
    def _core_cmds_delete(cls, vid, cfg, wr=False):
        return cls._tail(['', 'enable', 'configure terminal',
                          'router ospf {}'.format(CORE_OSPF_PID),
                          ospf_network_cmd(vlan_network(cfg), remove=True), 'exit',
                          'no interface vlan {}'.format(vid), 'no vlan {}'.format(vid)], wr)

    def _push(self, ssh, dname, node_id, cmds, t0):
        log = self.gui._log
        log('  [*] Cau hinh {}...\n'.format(dname), 'info')
        try:
            chan = console_open(ssh, node_id)
            ios_wake(chan)
            out = ''
            for cmd in cmds:
                out += console_send(chan, cmd, wait=1.5 if cmd == 'write memory' else 0.5)
            chan.close()
            errs = re.findall(r'^\s*%\s*(?!Warning).*$', out, re.M)
            if errs:
                log('  [!] {} bao loi: {}\n'.format(dname, ' | '.join(e.strip() for e in errs[:3])), 'err')
            log('  [OK] {} da nhan lenh (t={:.2f}s)\n'.format(dname, time.time() - t0), 'ok')
            return True
        except Exception as e:
            log('  [!] Loi tren {}: {}\n'.format(dname, e), 'err')
            return False

    # ---- verification (T1..T4, chay song song) -------------------------------
    def _wait_svi_up(self, ssh, vid, t0, res):
        log = self.gui._log
        try:
            chan = console_open(ssh, CORE_SW_NODE_IDS['Core-SW1'])
            ios_wake(chan)
            deadline = time.time() + 40
            while time.time() < deadline:
                ts = time.time()
                out = console_send(chan, 'show interface vlan {}'.format(vid), wait=1.0)
                if re.search(r'line protocol is up', out, re.IGNORECASE):
                    res['svi'] = ts - t0
                    break
                time.sleep(1)
            chan.close()
        except Exception as e:
            log('  [!] T1 loi khi kiem tra SVI: {}\n'.format(e), 'err')
        if 'svi' in res:
            log('  [OK] T1 SVI VLAN {} up/up luc t={:.2f}s\n'.format(vid, res['svi']), 'ok')
        else:
            log('  [!] T1 SVI chua len "up/up" trong thoi gian cho.\n', 'err')

    def _prepare(self, ssh, opts, action):
        """Mo SAN cac phien console/API TRUOC moc t0 de thoi gian do khong bi
        cong them thoi gian dang nhap (ASA enable, vManage login, VPC wake)."""
        log = self.gui._log
        ctx = {}
        if not opts['verify']:
            return ctx
        remote = opts['remote']
        log('  [*] Chuan bi kiem chung SD-WAN ({} - site {}): mo console FW / VPC / vManage...\n'.format(
            remote, SITES[HOST_SITE[remote]]['site_id']), 'info')

        def _fw():
            ctx['fw'] = asa_open_active(ssh, opts['fw_pw'], log)
            if not ctx['fw']:
                log('  [!] T2 se bo qua: khong vao duoc console FW-ASAv Active.\n', 'err')

        def _vpc():
            try:
                chan = console_open(ssh, VPC_NODE_IDS[remote])
                chan.send('\n'); time.sleep(0.4); _flush_chan(chan)
                ctx['vpc'] = chan
            except Exception as e:
                log('  [!] T4 se bo qua: loi console {}: {}\n'.format(remote, e), 'err')

        def _vm():
            if not opts['vm_pw']:
                log('  [i] T3 bo qua (chua nhap vManage pass).\n', 'info'); return
            api = VManageAPI(ssh, opts['vm_user'], opts['vm_pw'])
            try:
                ctx['vm_via'] = api.open(); ctx['vm'] = api
            except Exception as e:
                log('  [!] T3 se bo qua: {}\n'.format(e), 'err'); api.close()

        jobs = [_fw, _vpc] + ([] if action == 'DELETE' else [_vm])
        threads = [threading.Thread(target=f, daemon=True) for f in jobs]
        for th in threads: th.start()
        for th in threads: th.join(90)
        return ctx

    @staticmethod
    def _cleanup(ctx):
        if ctx.get('fw'):
            _, chan, was_user = ctx['fw']
            try:
                if was_user: console_send(chan, 'disable', wait=0.4)
                chan.close()
            except Exception: pass
        if ctx.get('vpc'):
            try: ctx['vpc'].close()
            except Exception: pass
        if ctx.get('vm'):
            ctx['vm'].close()

    def _poll_fw(self, ctx, net, present, t0, res):
        log = self.gui._log
        name, chan, _ = ctx['fw']
        pat = re.compile(r'^\s*O\S*\s+{}\s+{}\b'.format(re.escape(str(net.network_address)),
                                                       re.escape(str(net.netmask))), re.M)
        try:
            deadline = time.time() + VERIFY_TIMEOUT
            while time.time() < deadline:
                ts = time.time()
                out = console_send(chan, 'show route ospf | include {}'.format(net.network_address),
                                   wait=0.8, read_timeout=3)
                if bool(pat.search(out)) == present:
                    res['fw'] = ts - t0
                    break
                time.sleep(0.5)
        except Exception as e:
            log('  [!] T2 loi console FW: {}\n'.format(e), 'err')
        if 'fw' in res:
            log('  [OK] T2 {} {} route OSPF {} luc t={:.2f}s\n'.format(
                name, 'da hoc' if present else 'da go', net, res['fw']), 'ok')
        else:
            log('  [!] T2 {} chua {} route OSPF {} sau {}s\n'.format(
                name, 'hoc' if present else 'go', net, VERIFY_TIMEOUT), 'err')

    def _check_vmanage(self, ctx, net, remote_host, t0, res):
        log = self.gui._log
        site_id = SITES[HOST_SITE[remote_host]]['site_id']
        api = ctx['vm']
        try:
            ts = time.time()
            omp, bfd = [], set()
            for sip, vname in SITE_VEDGES.get(site_id, {}).items():
                site_re = '"site-id":"?{}"?[,}}]'.format(CORE_SITE_ID)
                for r in api.get('device/omp/routes/received?deviceId={}'.format(sip), grep=site_re):
                    try: pfx = ipaddress.ip_network(r.get('prefix', ''))
                    except ValueError: continue
                    st = r.get('status', '')
                    if (str(r.get('vpn-id')) == '1' and str(r.get('site-id')) == str(CORE_SITE_ID)
                            and pfx.version == 4 and net.subnet_of(pfx) and 'C' in st and 'I' in st):
                        omp.append('{}@{}({})'.format(pfx, vname, r.get('color', '')))
                for r in api.get('device/bfd/sessions?deviceId={}'.format(sip), grep=site_re):
                    if str(r.get('site-id')) == str(CORE_SITE_ID) and r.get('state') == 'up':
                        bfd.add('{}>{}'.format(r.get('local-color'), r.get('color')))
            res['omp'] = ' '.join(sorted(set(omp)))
            res['bfd'] = ' '.join(sorted(bfd))
            if omp and bfd:
                res['sdwan'] = ts - t0
                log('  [OK] T3 vManage ({}): site {} co route OMP {} (C,I) + BFD up [{}] luc t={:.2f}s\n'.format(
                    ctx.get('vm_via'), site_id, sorted(set(o.split('@')[0] for o in omp)),
                    res['bfd'], res['sdwan']), 'ok')
            else:
                log('  [!] T3 vManage: OMP={} | BFD up={} -> overlay CHUA san sang cho {}\n'.format(
                    res['omp'] or 'khong co', res['bfd'] or 'khong co', net), 'err')
        except Exception as e:
            log('  [!] T3 loi vManage API: {}\n'.format(e), 'err')

    def _poll_e2e(self, ctx, remote_host, target, reach, t0, res):
        """reach=True: ping tu VPC site khac cho toi reply dau tien (+traceroute);
        reach=False: cho toi 3 lan timeout lien tiep (VLAN da bi go)."""
        log = self.gui._log
        chan = ctx['vpc']
        try:
            deadline = time.time() + VERIFY_TIMEOUT
            fail_since, fails = None, 0
            while time.time() < deadline:
                ts = time.time()
                ok = 'bytes from' in vpcs_cmd(chan, 'ping {} -c 1'.format(target))
                if reach and ok:
                    res['e2e'] = ts - t0; break
                if not reach:
                    if ok: fail_since, fails = None, 0
                    else:
                        fail_since = fail_since or ts; fails += 1
                        if fails >= 3:
                            res['e2e'] = fail_since - t0; break
            if reach and 'e2e' in res:
                out = vpcs_cmd(chan, 'trace {} -m 8'.format(target), timeout=40)
                hops = re.findall(r'^\s*\d+\s+\*?(\d+\.\d+\.\d+\.\d+)', out, re.M)
                vedges = [VEDGE_LAN_IPS[h] for h in hops if h in VEDGE_LAN_IPS]
                res['path'] = ' > '.join('{}({})'.format(h, VEDGE_LAN_IPS[h]) if h in VEDGE_LAN_IPS else h
                                         for h in hops)
                res['via_sdwan'] = len(set(vedges)) >= 2
        except Exception as e:
            log('  [!] T4 loi console {}: {}\n'.format(remote_host, e), 'err')
        if 'e2e' in res:
            log('  [OK] T4 {} -> {} {} luc t={:.2f}s\n'.format(
                remote_host, target, 'THONG' if reach else 'DA MAT KET NOI', res['e2e']), 'ok')
            if reach:
                log('       Path: {}  => {}\n'.format(res.get('path') or '?',
                    'DI QUA OVERLAY SD-WAN' if res.get('via_sdwan') else 'KHONG thay 2 hop vEdge'),
                    'ok' if res.get('via_sdwan') else 'err')
        else:
            log('  [!] T4 {} -> {} chua {} sau {}s (kiem tra ACL FW / route)\n'.format(
                remote_host, target, 'thong' if reach else 'mat', VERIFY_TIMEOUT), 'err')

    def _verify(self, ssh, ctx, opts, action, vid, cfg, t0):
        """Chay song song cac moc kiem chung (dung phien da mo o _prepare)."""
        res = {}
        removing = action == 'DELETE'
        net = vlan_network(cfg)
        jobs = []
        if not removing:
            jobs.append((self._wait_svi_up, (ssh, vid, t0, res)))
        if opts['verify']:
            res['remote'] = opts['remote']
            if ctx.get('fw'):
                jobs.append((self._poll_fw, (ctx, net, not removing, t0, res)))
            if ctx.get('vm'):
                jobs.append((self._check_vmanage, (ctx, net, opts['remote'], t0, res)))
            if ctx.get('vpc'):
                jobs.append((self._poll_e2e, (ctx, opts['remote'], cfg['ip1'], not removing, t0, res)))
        threads = [threading.Thread(target=f, args=a, daemon=True) for f, a in jobs]
        for th in threads: th.start()
        for th in threads: th.join(VERIFY_TIMEOUT + 60)
        self._cleanup(ctx)
        return res

    # ---- ket qua: CSV + PNG --------------------------------------------------
    @staticmethod
    def _append_csv(fname, row, cols=None):
        path = os.path.join(LOG_DIR, fname)
        cols = cols or list(row.keys())
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                header = f.readline().strip().split(',')
            if header != cols:   # file tu phien ban cu -> cat sang .bak
                os.replace(path, path + '.{}.bak'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
        write_header = not os.path.exists(path)
        with open(path, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=cols)
            if write_header: w.writeheader()
            w.writerow(row)
        return path

    def _timeline_png(self, action, vid, t_config, res):
        if not HAS_MPL: return None
        removing = action == 'DELETE'
        steps = [('Gui lenh Core-SW', t_config, GREY)]
        if not removing:
            steps.append(('T1 SVI up/up', res.get('svi'), CYAN))
        steps.append(('T2 FW {} route OSPF'.format('go' if removing else 'hoc'), res.get('fw'), PURPLE))
        if not removing:
            steps.append(('T3 vManage xac nhan OMP+BFD', res.get('sdwan'), ORANGE))
        steps.append(('T4 {} lien site'.format('Mat ket noi' if removing else 'Ping thong'), res.get('e2e'),
                      RED if removing else GREEN))
        fig, ax = plt.subplots(figsize=(9, 0.6 * len(steps) + 1.4))
        fig.patch.set_facecolor(ChartEngine.BG_DARK)
        ChartEngine._dark(ax, 'VLAN {} - {}: thoi gian co hieu luc qua SD-WAN'.format(vid, action))
        ax.grid(True, color=ChartEngine.GRID, linewidth=0.6, alpha=0.7, axis='x')
        ax.set_axisbelow(True)
        vmax = max([v for _, v, _ in steps if v] or [1])
        for i, (lbl, v, col) in enumerate(steps):
            ax.barh(i, v or 0, color=col, edgecolor=ChartEngine.EDGE)
            ax.text((v or 0) + vmax * 0.01, i, '{:.2f}s'.format(v) if v is not None else 'N/A',
                    va='center', color=ChartEngine.TXT, fontsize=8)
        ax.set_yticks(range(len(steps)))
        ax.set_yticklabels([s[0] for s in steps], color=ChartEngine.TXT, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel('giay (tinh tu luc gui lenh)', color=ChartEngine.TXT)
        ax.set_xlim(0, vmax * 1.15)
        plt.tight_layout()
        path = os.path.join(LOG_DIR, 'vlan_{}_{}_{}.png'.format(
            action.lower(), vid, datetime.now().strftime('%Y%m%d_%H%M%S')))
        plt.savefig(path, dpi=130, bbox_inches='tight')
        plt.close('all')
        return path

    def _record(self, action, vid, cfg, t_config, res):
        """Ghi 1 thao tac vao case_vlan_ops.csv + PNG timeline + in tong ket."""
        log = self.gui._log
        r2 = lambda k: round(res[k], 2) if res.get(k) is not None else ''
        row = {'action': action, 'vlan_id': vid, 'name': cfg['name'], 'subnet': str(vlan_network(cfg)),
               'gateway': cfg['vip'], 'config_time_s': round(t_config, 2), 'svi_up_s': r2('svi'),
               'fw_ospf_s': r2('fw'), 'sdwan_check_s': r2('sdwan'), 'e2e_s': r2('e2e'),
               'remote_host': res.get('remote', ''), 'omp_route': res.get('omp', ''),
               'bfd_up': res.get('bfd', ''), 'via_sdwan': res.get('via_sdwan', ''),
               'path': res.get('path', ''), 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        path = self._append_csv(VLAN_OPS_CSV, row, VLAN_OPS_COLS)
        log('  [OK] Ket qua ghi vao (append): {}\n'.format(path), 'ok')
        try:
            png = self._timeline_png(action, vid, t_config, res)
            if png: log('  [OK] PNG: {}\n'.format(png), 'ok')
        except Exception as e:
            log('  [!] Loi ve PNG: {}\n'.format(e), 'err')
        fmt = lambda k: '{:.2f}s'.format(res[k]) if res.get(k) is not None else 'N/A'
        log('  === {}: cau hinh {:.2f}s | SVI {} | FW OSPF {} | vManage {} | lien site {} ===\n'.format(
            action, t_config, fmt('svi'), fmt('fw'), fmt('sdwan'), fmt('e2e')), 'hdr')
        log('=' * 55 + '\n\n', 'sep')
        return row

    def _commit(self, key, entry):
        """Cap nhat registry tu worker thread -> luu file + ve lai bang o main thread."""
        def _do():
            entry['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.registry[key] = entry
            self._save_registry(); self._refresh_tree()
            self.tree.selection_set(key)
        self.after(0, _do)

    # ---- worker threads ------------------------------------------------------
    def _add_thread(self, ssh, opts, vid, cfg, restoring=False):
        log = self.gui._log
        action = 'RESTORE' if restoring else 'ADD'
        log('\n' + '='*55 + '\n', 'sep')
        log('[{}-VLAN] VLAN {} ({}) {} - Gateway {}\n'.format(
            action, vid, cfg['name'], vlan_network(cfg), cfg['vip']), 'hdr')
        ctx = self._prepare(ssh, opts, action)
        t0 = time.time()
        ok = all([self._push(ssh, dname, node_id, self._core_cmds_add(vid, cfg, ip, prio, opts['wr']), t0)
                  for dname, node_id, ip, prio in self._targets(cfg)])
        t_config = time.time() - t0
        res = self._verify(ssh, ctx, opts, action, vid, cfg, t0)
        row = self._record(action, vid, cfg, t_config, res)
        if not restoring:
            # giu nguyen dinh dang CSV cu cho bao cao "Thoi gian them moi VLAN"
            self._append_csv('case_addvlan.csv', {
                'vlan_id': vid, 'name': cfg['name'], 'gateway': cfg['vip'],
                'config_time_s': row['config_time_s'], 'svi_up_time_s': row['svi_up_s'],
                'timestamp': row['timestamp']})
        if ok:
            old = self.registry.get(str(vid), {})
            self._commit(str(vid), {'cfg': cfg, 'status': 'active',
                                    'history': old.get('history', []) if restoring else []})

    def _edit_thread(self, ssh, opts, vid, old, new, is_edit):
        """is_edit=True: Sua (luu cau hinh cu vao history); False: hoan tac (pop history)."""
        log = self.gui._log
        action = 'EDIT' if is_edit else 'UNDO-EDIT'
        log('\n' + '='*55 + '\n', 'sep')
        log('[{}-VLAN] VLAN {}: {} {} -> {} {}\n'.format(
            action, vid, old['name'], vlan_network(old), new['name'], vlan_network(new)), 'hdr')
        ctx = self._prepare(ssh, opts, action)
        t0 = time.time()
        ok = True
        if old['dual'] and not new['dual']:
            # bo du phong -> go SVI/VLAN/OSPF tren Core-SW2
            ok &= self._push(ssh, 'Core-SW2', CORE_SW_NODE_IDS['Core-SW2'],
                             self._core_cmds_delete(vid, old, opts['wr']), t0)
        for dname, node_id, ip, prio in self._targets(new):
            if dname == 'Core-SW2' and not old['dual']:
                # them du phong moi -> tao day du tren Core-SW2
                cmds = self._core_cmds_add(vid, new, ip, prio, opts['wr'])
            else:
                cmds = self._core_cmds_edit(vid, old, new, ip, prio, opts['wr'])
            ok &= self._push(ssh, dname, node_id, cmds, t0)
        t_config = time.time() - t0
        res = self._verify(ssh, ctx, opts, action, vid, new, t0)
        self._record(action, vid, new, t_config, res)
        if ok:
            hist = list(self.registry.get(str(vid), {}).get('history', []))
            if is_edit: hist.append(old)
            elif hist: hist.pop()
            self._commit(str(vid), {'cfg': new, 'status': 'active', 'history': hist})

    def _delete_thread(self, ssh, opts, vid, cfg):
        log = self.gui._log
        log('\n' + '='*55 + '\n', 'sep')
        log('[DELETE-VLAN] Xoa VLAN {} ({}) tren Core-SW1/2...\n'.format(vid, vlan_network(cfg)), 'hdr')
        ctx = self._prepare(ssh, opts, 'DELETE')
        t0 = time.time()
        ok = all([self._push(ssh, dname, CORE_SW_NODE_IDS[dname], self._core_cmds_delete(vid, cfg, opts['wr']), t0)
                  for dname in ('Core-SW1', 'Core-SW2')])
        t_config = time.time() - t0
        res = self._verify(ssh, ctx, opts, 'DELETE', vid, cfg, t0)
        self._record('DELETE', vid, cfg, t_config, res)
        e = self.registry.get(str(vid))
        if ok and e:
            log('  [i] Da luu ban sao cau hinh -> co the "Khoi phuc".\n', 'info')
            self._commit(str(vid), dict(e, status='deleted'))


# =========================================================
#  CHINH SACH TAP TRUNG  –  kiem chung policy vSmart (Centralized Policy)
#  Policy that tren vSmart (configs/05-Site900-SDWAN-Controllers/vSmart-34):
#    DP_BRANCH        data-policy from-service, site 200-400: drop telnet ->
#                     Server Farm, drop ssh/telnet -> DMZ, count ICMP
#    AAR_LAN          app-route-policy, site 100-400: ICMP/DSCP46 -> SLA_REALTIME,
#                     web/mail/Server Farm -> SLA_BUSINESS; KHONG ep mau: moi tunnel dat SLA
#                     deu dung, vi pham SLA thi bi loai, tat ca vi pham -> fallback tunnel tre
#                     thap nhat (fallback-best-tunnel latency loss); co count AAR_*
#    PREFER-VE1       control-policy out, site 100-400: route tu vEdge1 moi site
#                     preference 200 -> chi nhanh vao campus qua vEdge1
#  Tool KHONG sua policy: chi sinh traffic that tu VPC chi nhanh roi doc
#  counter policy tren vEdge qua vManage API (truoc/sau) de chung minh policy
#  do vSmart day xuong duoc thuc thi. Rieng whitelist vEdge (mat sau khi
#  reboot controller) co the day lai tu vManage (POST, idempotent).
# =========================================================
POLICY_CSV  = 'case_policy.csv'
POLICY_COLS = ['timestamp', 'test_id', 'policy', 'test', 'src_host', 'target',
               'check', 'delta', 'detail', 'result']
IP_SITE = {1: 100, 2: 200, 3: 300, 4: 400}     # octet thu 2 cua 10.X.0.0/16 -> site-id
VEDGE_REJOIN_TIMEOUT = 150                      # giay cho vEdge len lai sau khi day whitelist


def site_of_ip(ip):
    try:
        return IP_SITE.get(int(ip.split('.')[1]))
    except (IndexError, ValueError):
        return None


class PolicyTab(tk.Frame):
    """Kiem chung chinh sach tap trung SD-WAN (vSmart -> OMP -> vEdge).
    Tra loi tieu chi de bai: 'Kha nang quan ly chinh sach tap trung' va muc
    tieu 'Quan ly tap trung luong du lieu giua cac khu vuc'."""
    def __init__(self, parent, gui):
        super().__init__(parent, bg=BG2)
        self.gui = gui
        self._busy = False
        self._build()

    def _build(self):
        tk.Label(self, bg=BG2, fg=GREY, font=FONT_SMALL, justify='left', anchor='w', wraplength=880,
                 text='Kiem chung policy tap trung tren vSmart: W whitelist vEdge tren vBond (tu day lai tu '
                      'vManage neu thieu), DP data-policy DP_BRANCH (chan telnet/ssh), AAR app-route AAR_LAN '
                      '(chon tunnel dat SLA, fallback tunnel tre thap nhat), CP control-policy PREFER-VE1. '
                      'Tool sinh traffic that tu 1 VPC chi nhanh roi so counter policy tren vEdge (vManage API) '
                      'truoc/sau. Khong sua policy tren vSmart.'
                 ).pack(fill='x', padx=10, pady=(10, 6))

        row = tk.Frame(self, bg=BG2); row.pack(fill='x', padx=10, pady=2)
        srcs = sorted(h for h in VPC_NODE_IDS
                      if h in HOST_SITE and SITES[HOST_SITE[h]]['site_id'] != CORE_SITE_ID)
        self.src_var = tk.StringVar(value='VPC43' if 'VPC43' in srcs else (srcs[0] if srcs else ''))
        self.farm_var = tk.StringVar(value='10.1.90.10')
        self.dmz_var = tk.StringVar(value='10.1.1.10')
        self.icmp_var = tk.StringVar(value='10.1.10.1')
        self.count_var = tk.IntVar(value=10)
        self.vm_user_var = tk.StringVar(value='admin')
        self.vm_pw_var = tk.StringVar(value='')
        fields = [('VPC nguon (chi nhanh):', None, '(DP_BRANCH chi ap cho site 200-400)'),
                  ('IP Server Farm:', self.farm_var, '(dich test Telnet bi chan + ICMP)'),
                  ('IP DMZ (Web/Mail):', self.dmz_var, '(dich test SSH bi chan + HTTP cho qua)'),
                  ('IP dich ICMP lien site:', self.icmp_var, '(host/gateway o site KHAC, vd 10.1.10.1, 10.3.90.101)'),
                  ('So goi ICMP:', self.count_var, ''),
                  ('vManage user:', self.vm_user_var, ''),
                  ('vManage pass:', self.vm_pw_var, '(bat buoc - doc counter qua vManage API)')]
        for i, (lbl, var, hint) in enumerate(fields):
            tk.Label(row, text=lbl, bg=BG2, fg=WHITE, width=20, anchor='w').grid(row=i, column=0, sticky='w', pady=2)
            if var is None:
                ttk.Combobox(row, textvariable=self.src_var, values=srcs, width=18,
                             state='readonly').grid(row=i, column=1, padx=4, pady=2, sticky='w')
            elif var is self.count_var:
                tk.Spinbox(row, from_=3, to=100, textvariable=var, width=8, bg=BG3, fg=WHITE,
                           insertbackground=WHITE, buttonbackground=BG3, relief='flat').grid(
                    row=i, column=1, padx=4, pady=2, sticky='w')
            else:
                tk.Entry(row, textvariable=var, bg=BG3, fg=WHITE, insertbackground=WHITE, width=20,
                         relief='flat', show='*' if 'pass' in lbl else '').grid(row=i, column=1, padx=4, pady=2, sticky='w')
            if hint:
                tk.Label(row, text=hint, bg=BG2, fg=GREY, font=FONT_SMALL).grid(row=i, column=2, sticky='w', padx=6)

        cf = tk.LabelFrame(self, text=' Nhom kiem tra ', bg=BG2, fg=CYAN,
                           font=('Segoe UI', 9, 'bold'), bd=1, relief='groove')
        cf.pack(fill='x', padx=10, pady=(8, 0))
        self.chk = {}
        for i, (key, text) in enumerate([
                ('W', 'W  Whitelist vEdge tren vBond (tu dong day lai tu vManage neu thieu)'),
                ('DP', 'DP Data-policy DP_BRANCH: Telnet->Farm, SSH->DMZ bi chan; HTTP->DMZ, ICMP cho qua'),
                ('AAR', 'AAR App-route AAR_LAN: ICMP lien site khop luat SLA_REALTIME (AAR_ICMP)'),
                ('CP', 'CP Control-policy PREFER-VE1: chi nhanh chon route 10.1.0.0/16 cua vEdge1-S100')]):
            var = tk.BooleanVar(value=True); self.chk[key] = var
            tk.Checkbutton(cf, text=text, variable=var, bg=BG2, fg=TEAL, selectcolor=BG3,
                           activebackground=BG2, font=FONT_UI).grid(row=i, column=0, sticky='w', padx=4)

        bf = tk.Frame(self, bg=BG2); bf.pack(fill='x', padx=10, pady=8)
        for text, color, cmd in [('Chay kiem tra chinh sach', ORANGE, self._run_all),
                                 ('Chi kiem tra whitelist', CYAN, self._run_whitelist)]:
            tk.Button(bf, text=text, bg=BG3, fg=color, font=('Segoe UI', 9, 'bold'),
                      bd=0, relief='flat', activebackground='#2d333b', cursor='hand2',
                      command=cmd, pady=6, padx=10).pack(side='left', padx=4)

    # ---- button handlers (main thread) --------------------------------------
    def _read_opts(self):
        opts = {'src': self.src_var.get(), 'farm': self.farm_var.get().strip(),
                'dmz': self.dmz_var.get().strip(), 'icmp': self.icmp_var.get().strip(),
                'count': self.count_var.get(), 'vm_user': self.vm_user_var.get().strip() or 'admin',
                'vm_pw': self.vm_pw_var.get(), 'groups': {k for k, v in self.chk.items() if v.get()}}
        if not opts['vm_pw']:
            raise ValueError('Nhap vManage pass (counter policy doc qua vManage API).')
        for k in ('farm', 'dmz', 'icmp'):
            ipaddress.ip_address(opts[k])   # nem ValueError neu sai
        if opts['groups'] & {'DP', 'AAR'} and opts['src'] not in VPC_NODE_IDS:
            raise ValueError('Chon VPC nguon.')
        return opts

    def _start(self, only_whitelist=False):
        ssh = self.gui._ssh_client
        if not ssh:
            messagebox.showerror('Chua SSH', 'Ket noi SSH (man hinh chinh, SSH Mode) truoc khi chay.'); return
        if self._busy:
            messagebox.showwarning('Dang chay', 'Dang co 1 lan kiem tra khac, vui long doi.'); return
        try:
            opts = self._read_opts()
        except ValueError as e:
            messagebox.showerror('Tham so sai', str(e)); return
        if only_whitelist:
            opts['groups'] = {'W'}
        if not opts['groups']:
            messagebox.showwarning('Chua chon', 'Tick it nhat 1 nhom kiem tra.'); return
        self._busy = True

        def _run():
            try: self._thread(ssh, opts)
            except Exception as e: self.gui._log('[POLICY] Loi: {}\n'.format(e), 'err')
            finally: self._busy = False
        threading.Thread(target=_run, daemon=True).start()

    def _run_all(self):
        self._start()

    def _run_whitelist(self):
        self._start(only_whitelist=True)

    # ---- helpers (worker thread) ---------------------------------------------
    @staticmethod
    def _snapshot(api, edges):
        """Counter data-policy + app-route-policy tren cac vEdge -> {(edge, policy, counter): packets}."""
        d = {}
        for e in edges:
            for kind in ('datapolicyfilter', 'approutepolicyfilter'):
                for r in api.get('device/policy/{}?deviceId={}'.format(kind, e)):
                    if 'counter-name' in r and 'vdevice-name' in r:
                        try: d[(e, r.get('policy-name'), r['counter-name'])] = int(r.get('packets') or 0)
                        except ValueError: pass
        return d

    @staticmethod
    def _delta(before, after, policy, counter):
        """Tong delta 1 counter tren moi vEdge + chuoi chi tiet theo vEdge."""
        names = {ip: n for d in SITE_VEDGES.values() for ip, n in d.items()}
        total, parts = 0, []
        for k, v in after.items():
            if k[1] == policy and k[2] == counter:
                dv = v - before.get(k, 0)
                total += dv
                if dv: parts.append('{}+{}'.format(names.get(k[0], k[0]), dv))
        return total, ' '.join(parts)

    def _record(self, rows, test_id, policy, test, opts, target, check, delta, detail, ok):
        rows.append({'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'test_id': test_id,
                     'policy': policy, 'test': test, 'src_host': opts.get('src', ''), 'target': target,
                     'check': check, 'delta': delta, 'detail': detail, 'result': 'PASS' if ok else 'FAIL'})
        self.gui._log('    [{}] {} {} = {} {}\n'.format('PASS' if ok else 'FAIL', test_id, check, delta,
                                                      '({})'.format(detail) if detail else ''),
                      'ok' if ok else 'err')

    def _whitelist(self, api, rows, opts):
        log = self.gui._log
        log('  [W] Doi chieu whitelist vManage <-> vBond...\n', 'info')
        valid = {r.get('serialNumber'): r.get('host-name') for r in api.get('system/device/vedges', grep='validity')
                 if r.get('validity') == 'valid' and r.get('serialNumber')}
        vbond = next((r.get('system-ip') for r in api.get('device', grep='vbond') if r.get('system-ip')), None)
        if not vbond:
            self._record(rows, 'W-1', 'whitelist', 'vBond co mat trong vManage', opts, '-', 'vbond', 0, '', False)
            return
        onbond = {r.get('serial-number') for r in api.get('device/orchestrator/validvedges?deviceId=' + vbond)
                  if 'vdevice-name' in r}
        missing = {s: n for s, n in valid.items() if s not in onbond}
        log('      vManage valid={} | vBond {} co={} | thieu: {}\n'.format(
            len(valid), vbond, len(onbond), ', '.join(sorted(missing.values())) or 'khong'), 'info')
        if not missing:
            self._record(rows, 'W-1', 'whitelist', 'vBond du whitelist', opts, vbond, 'missing', 0, '', True)
            return
        log('  [W] Day whitelist tu vManage xuong controller (Send to Controllers)...\n', 'info')
        t0 = time.time()
        log('      vManage: {}\n'.format(api.post('certificate/vedge/list?action=push')[:120]), 'info')
        pending = set(missing.values())
        while pending and time.time() - t0 < VEDGE_REJOIN_TIMEOUT:
            time.sleep(10)
            up = {r.get('host-name') for r in api.get('device', grep='reachability')
                  if r.get('reachability') == 'reachable'}
            for n in sorted(pending & up):
                log('      {} reachable sau {:.0f}s\n'.format(n, time.time() - t0), 'ok')
            pending -= up
        ok = not pending
        self._record(rows, 'W-1', 'whitelist', 'Day lai whitelist -> vEdge len lai fabric', opts, vbond,
                     'rejoin_s', round(time.time() - t0, 1),
                     'thieu {}'.format(','.join(sorted(missing.values()))) +
                     ('' if ok else ' | chua len: ' + ','.join(sorted(pending))), ok)

    def _traffic_test(self, api, vpc, rows, opts, edges, test_id, name, cmd, target, checks, timeout=45):
        """Chup counter -> chay lenh VPCS -> chup lai -> danh gia tung check (policy, counter, 'gt0'|'eq0')."""
        log = self.gui._log
        log('  [{}] {}: {}\n'.format(test_id, name, cmd), 'info')
        before = self._snapshot(api, edges)
        out = vpcs_cmd(vpc, cmd, timeout)
        lines = [l.strip() for l in out.replace('\r', '').split('\n')
                 if l.strip() and 'VPCS>' not in l and not l.strip().startswith('ping ')]
        for l in lines[-6:]:
            log('      {}\n'.format(l), 'info')
        time.sleep(5)            # cho vEdge cap nhat counter
        after = self._snapshot(api, edges)
        replies = sum('bytes from' in l for l in lines)
        icmp = ' -P ' not in cmd
        for pol, counter, cond in checks:
            d, detail = self._delta(before, after, pol, counter)
            ok = d > 0 if cond == 'gt0' else d == 0
            if icmp:
                detail = (detail + ' | reply {}'.format(replies)).strip(' |')
            self._record(rows, test_id, pol, name, opts, target, counter, d, detail, ok)
        if icmp and replies == 0 and site_of_ip(target) != SITES[HOST_SITE[opts['src']]]['site_id']:
            log('    [i] 0 reply tu {}: policy da khop o chieu di, nhung dich khong tra loi (host/FW/Core site '
                'dich dang tat?) -> chua chung minh duoc thong dau-cuoi. Nen chon dich dang chay, '
                'vd VPC chi nhanh khac.\n'.format(target), 'info')

    def _control(self, api, rows, opts, edges):
        log = self.gui._log
        log('  [CP] Route OMP 10.1.0.0/16 tren vEdge site nguon...\n', 'info')
        for e in edges:
            routes = {r.get('originator'): r.get('status', '')
                      for r in api.get('device/omp/routes/received?deviceId=' + e, grep='"10\\.1\\.0\\.0/16"')
                      if r.get('prefix') == '10.1.0.0/16'}
            ve1, ve2 = routes.get('10.200.100.1', ''), routes.get('10.200.100.2', '')
            ok = 'C' in ve1 and 'C' not in ve2
            name = {ip: n for d in SITE_VEDGES.values() for ip, n in d.items()}.get(e, e)
            self._record(rows, 'CP-1', 'PREFER-VE1', 'Chi nhanh uu tien vEdge1-S100 ({})'.format(name),
                         opts, '10.1.0.0/16', 'status', 've1=[{}] ve2=[{}]'.format(ve1 or '-', ve2 or '-'),
                         '', ok)

    def _open_src_vpc(self, ssh, opts):
        """Mo console VPC nguon; neu node dang tat thi tu chon VPC chi nhanh khac
        dang chay (ghi ro vao log va opts['src']). Tra ve channel hoac None."""
        log = self.gui._log
        branch = sorted(h for h in VPC_NODE_IDS
                        if h in HOST_SITE and SITES[HOST_SITE[h]]['site_id'] != CORE_SITE_ID)
        for name in [opts['src']] + [h for h in branch if h != opts['src']]:
            try:
                chan = console_open(ssh, VPC_NODE_IDS[name])
            except Exception:
                if name == opts['src']:
                    log('  [!] Khong mo duoc console {} (node {} dang tat?) -> tim VPC chi nhanh khac...\n'.format(
                        name, VPC_NODE_IDS[name]), 'err')
                continue
            chan.send('\n'); time.sleep(0.4); _flush_chan(chan)
            if name != opts['src']:
                log('  [i] Dung {} lam VPC nguon thay cho {}.\n'.format(name, opts['src']), 'info')
                opts['src'] = name
            return chan
        log('  [!] Khong co VPC chi nhanh nao dang chay -> bo qua DP/AAR (can traffic that).\n', 'err')
        return None

    def _chart(self, rows):
        if not HAS_MPL: return None
        data = [r for r in rows if isinstance(r['delta'], (int, float)) and r['test_id'] != 'W-1']
        if not data: return None      # chi co whitelist -> khong co counter de ve
        path = os.path.join(LOG_DIR, 'policy_{}.png'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
        ChartEngine.bar_chart(['{} {}'.format(r['test_id'], r['check']) for r in data],
                              [r['delta'] for r in data],
                              'Chinh sach tap trung SD-WAN - delta counter (xanh=PASS, do=FAIL)',
                              'goi / giay', path, horiz=True,
                              color=[GREEN if r['result'] == 'PASS' else RED for r in data])
        return path

    # ---- worker ---------------------------------------------------------------
    def _thread(self, ssh, opts):
        log = self.gui._log
        groups = opts['groups']
        log('\n' + '='*55 + '\n', 'sep')
        log('[POLICY] Kiem chung chinh sach tap trung: {}\n'.format(' '.join(
            g for g in ('W', 'DP', 'AAR', 'CP') if g in groups)), 'hdr')
        rows, skipped = [], []
        api = VManageAPI(ssh, opts['vm_user'], opts['vm_pw'])
        vpc = None
        try:
            log('  [*] vManage API qua {}\n'.format(api.open()), 'info')
            if 'W' in groups:
                self._whitelist(api, rows, opts)
            if groups & {'DP', 'AAR'}:
                vpc = self._open_src_vpc(ssh, opts)
                if vpc is None:
                    skipped += [g for g in ('DP', 'AAR') if g in groups]
                    groups = groups - {'DP', 'AAR'}
            src_site = SITES[HOST_SITE[opts['src']]]['site_id'] if opts['src'] in HOST_SITE else None
            src_edges = sorted(SITE_VEDGES.get(src_site, {}))
            if vpc is not None:
                log('  [*] {} (site {}) - vEdge doc counter: {}\n'.format(
                    opts['src'], src_site, ', '.join(SITE_VEDGES[src_site][e] for e in src_edges)), 'info')
            if 'DP' in groups:
                dp = [('DP-1', 'Telnet -> Server Farm bi chan', 'ping {} -P 6 -p 23 -c 3'.format(opts['farm']),
                       opts['farm'], [('DP_BRANCH', 'TELNET_TO_FARM', 'gt0')]),
                      ('DP-2', 'SSH -> DMZ bi chan', 'ping {} -P 6 -p 22 -c 3'.format(opts['dmz']),
                       opts['dmz'], [('DP_BRANCH', 'ADMIN_TO_DMZ', 'gt0')]),
                      ('DP-3', 'HTTP -> DMZ cho qua (+AAR SLA_BUSINESS)',
                       'ping {} -P 6 -p 80 -c 3'.format(opts['dmz']), opts['dmz'],
                       [('DP_BRANCH', 'ADMIN_TO_DMZ', 'eq0'), ('DP_BRANCH', 'TELNET_TO_FARM', 'eq0'),
                        ('AAR_LAN', 'AAR_WEB', 'gt0')]),
                      ('DP-4', 'ICMP -> Server Farm duoc dem', 'ping {} -c 5'.format(opts['farm']),
                       opts['farm'], [('DP_BRANCH', 'ICMP_BRANCH', 'gt0')])]
                for tid, name, cmd, target, checks in dp:
                    self._traffic_test(api, vpc, rows, opts, src_edges, tid, name, cmd, target, checks)
            if 'AAR' in groups:
                dst_edges = sorted(SITE_VEDGES.get(site_of_ip(opts['icmp']), {}))
                edges = sorted(set(src_edges) | set(dst_edges))
                n = max(3, int(opts['count']))
                self._traffic_test(api, vpc, rows, opts, edges, 'AAR-1',
                                   'ICMP lien site -> luat SLA_REALTIME',
                                   'ping {} -c {}'.format(opts['icmp'], n), opts['icmp'],
                                   [('AAR_LAN', 'AAR_ICMP', 'gt0')], timeout=n * 2 + 20)
            if 'CP' in groups:
                if src_site == CORE_SITE_ID or not src_edges:
                    log('  [CP] Bo qua: control-policy chi ap cho chi nhanh (site 200-400).\n', 'info')
                else:
                    self._control(api, rows, opts, src_edges)
        except Exception as e:
            log('  [!] Loi: {}\n'.format(e), 'err')
        finally:
            if vpc is not None:
                try: vpc.close()
                except Exception: pass
            api.close()

        if not rows:
            log('=' * 55 + '\n\n', 'sep'); return
        fname = POLICY_CSV
        try:
            for r in rows:
                path = VlanTab._append_csv(fname, r, POLICY_COLS)
        except PermissionError:
            # file dang mo trong Excel (bi khoa) -> ghi sang file rieng, khong mat ket qua
            fname = 'case_policy_{}.csv'.format(datetime.now().strftime('%Y%m%d_%H%M%S'))
            log('  [!] {} dang bi khoa (dang mo trong Excel?) -> ghi sang {}\n'.format(POLICY_CSV, fname), 'err')
            for r in rows:
                path = VlanTab._append_csv(fname, r, POLICY_COLS)
        log('  [OK] Ket qua ghi vao (append): {}\n'.format(path), 'ok')
        try:
            png = self._chart(rows)
            if png: log('  [OK] PNG: {}\n'.format(png), 'ok')
        except Exception as e:
            log('  [!] Loi ve PNG: {}\n'.format(e), 'err')
        npass = sum(r['result'] == 'PASS' for r in rows)
        log('  === Chinh sach tap trung: {}/{} kiem tra PASS{} ===\n'.format(
            npass, len(rows), ' | BO QUA: {}'.format(', '.join(skipped)) if skipped else ''),
            'hdr' if npass == len(rows) and not skipped else 'err')
        log('=' * 55 + '\n\n', 'sep')


# =========================================================
#  ENTRY POINT
# =========================================================
if __name__ == '__main__':
    if sys.version_info < (3,7):
        print('[!] Can Python 3.7+'); sys.exit(1)
    app = CampusPingGUI()
    app.mainloop()
