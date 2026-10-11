#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
campus_throughput.py  –  Do thong luong (throughput) tren vEdge
================================================================
Dung chung co che console cua campus_ping_tool.py (SSH -> direct-tcpip toi
console EVE-NG), khong can cai them gi tren lab:
  * Doc bo dem octet cua interface vEdge ("show interface statistics | notab")
    theo chu ky -> RX/TX Mbps tung interface = delta octet * 8 / delta thoi gian
  * (tuy chon) Bom tai bang VPCS: ping goi lon lien tuc tu 1 VPC sang 1 IP o
    site khac -> traffic di qua overlay SD-WAN, dong thoi tinh goodput ICMP
    dau-cuoi (so goi tra loi * kich thuoc / thoi gian)
Luu CSV + PNG vao log/ (giong Failover Test). Ban web doc trang thai truc tiep
qua ThroughputTest.snapshot() de ve bieu do song.
"""
import csv, os, re, threading, time
from datetime import datetime

from campus_ping_tool import (
    VEDGE_NODE_IDS, VPC_NODE_IDS, WAN_IFACE, VEDGE_LAB_PASSWORDS, LOG_DIR, HAS_MPL,
    ChartEngine, console_open, vedge_login, _flush_chan, _last_line,
)
if HAS_MPL:
    import matplotlib.pyplot as plt

STATS_CMD = 'show interface statistics | notab | nomore'
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
ICMP_HDR = 28               # IP 20 + ICMP 8 byte, cong vao payload VPCS (-l)
# Mau series (dataviz categorical, co dinh theo thu tu interface)
SERIES_COLORS = ('#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300')


def parse_iface_stats(raw):
    """Parse output notab cua 'show interface statistics' -> {(vpn, ifname): (rx_octets, tx_octets)}.
    Chap nhan ca 2 kieu dong tieu de ConfD:
      'interface vpn 0 interface ge0/0 af-type ipv4'  hoac  'interface 0 ge0/0 ipv4'."""
    out, key, rx, tx = {}, None, None, None

    def flush():
        if key and rx is not None and tx is not None and key not in out:
            out[key] = (rx, tx)

    for line in raw.replace('\r', '').split('\n'):
        m = re.match(r'^interface\s+(?:vpn\s+)?(\d+)\s+(?:interface\s+)?(\S+)', line)
        if m:
            flush()
            key, rx, tx = (int(m.group(1)), m.group(2)), None, None
            continue
        m = re.match(r'^\s+(rx|tx)-octets\s+(\d+)', line)
        if m and key:
            if m.group(1) == 'rx': rx = int(m.group(2))
            else: tx = int(m.group(2))
    flush()
    return out


class VedgeCounterReader:
    """1 phien console vEdge giu mo suot bai do; moi lan read() chay STATS_CMD."""

    def __init__(self, ssh, vname, user, password):
        self.chan = console_open(ssh, VEDGE_NODE_IDS[vname])
        banner = None
        for pw in [password] + [p for p in VEDGE_LAB_PASSWORDS if p != password]:
            try:
                banner = vedge_login(self.chan, user, pw); break
            except RuntimeError as e:
                if 'sai user/password' not in str(e): raise
        if banner is None:
            self.close()
            raise RuntimeError('khong dang nhap duoc {} (sai password?)'.format(vname))
        self.prompt = _last_line(banner)          # vd 'vEdge1-S200#'

    def read(self, timeout=15):
        """-> (thoi diem doc xong, {(vpn, ifname): (rx, tx)}, raw).
        Ket thuc khi dong cuoi la 1 prompt exec ('...#', bo ma ANSI) sau khi da co du lieu
        interface, hoac khi im lang 1.2s sau khi da nhan du lieu (khong cho het timeout)."""
        _flush_chan(self.chan)
        self.chan.send(STATS_CMD + '\n')
        buf, deadline, last_rx = '', time.time() + timeout, None
        while time.time() < deadline:
            if self.chan.recv_ready():
                buf += self.chan.recv(65535).decode('utf-8', errors='replace')
                last_rx = time.time()
                clean = ANSI_RE.sub('', buf).replace('\r', '')
                if 'octets' in clean and re.search(r'\n[^\n]*#\s*$', clean):
                    break
            elif last_rx and time.time() - last_rx > 1.2:
                break
            else:
                time.sleep(0.05)
        return time.time(), parse_iface_stats(ANSI_RE.sub('', buf)), buf

    def close(self):
        try: self.chan.close()
        except Exception: pass


class LoadGenerator(threading.Thread):
    """Ping goi lon lien tuc tu console VPCS (-t), dem goi tra loi de tinh goodput."""

    def __init__(self, ssh, src, target, size, interval_ms):
        super().__init__(daemon=True)
        self.ssh, self.src, self.target = ssh, src, target
        self.size, self.interval_ms = size, interval_ms
        self.replies = self.timeouts = 0
        self.t_start = self.t_end = None
        self.error = None
        self._halt = threading.Event()

    def run(self):
        chan = None
        try:
            chan = console_open(self.ssh, VPC_NODE_IDS[self.src])
            chan.send('\n'); time.sleep(0.4); _flush_chan(chan)
            opt = ' -i {}'.format(self.interval_ms) if self.interval_ms else ''
            chan.send('ping {} -l {}{} -t\n'.format(self.target, self.size, opt))
            self.t_start, tail = time.time(), ''
            while not self._halt.is_set():
                if chan.recv_ready():
                    tail += chan.recv(65535).decode('utf-8', errors='replace')
                    lines = tail.split('\n')
                    tail = lines.pop()               # dong chua tron -> giu lai
                    for l in lines:
                        if re.search(r'bytes from .*time=', l): self.replies += 1
                        elif re.search(r'timeout|unreachable', l, re.I): self.timeouts += 1
                        elif re.search(r'invalid|usage|bad', l, re.I) and not self.replies:
                            raise RuntimeError('VPCS khong nhan lenh ping: {!r}'.format(l.strip()[:80]))
                else:
                    time.sleep(0.05)
        except Exception as e:
            self.error = str(e)
        finally:
            self.t_end = time.time()
            if chan is not None:
                try:
                    chan.send('\x03'); time.sleep(0.5); chan.close()
                except Exception:
                    pass

    def stop(self):
        self._halt.set()

    def stats(self):
        el = ((self.t_end or time.time()) - self.t_start) if self.t_start else 0.0
        total = self.replies + self.timeouts
        bits = self.replies * (self.size + ICMP_HDR) * 8
        return {'src': self.src, 'target': self.target, 'size': self.size,
                'replies': self.replies, 'timeouts': self.timeouts, 'elapsed': round(el, 1),
                'loss': round(self.timeouts / total * 100, 1) if total else 0.0,
                'pps': round(self.replies / el, 1) if el else 0.0,
                'mbps': round(bits / el / 1e6, 3) if el else 0.0, 'error': self.error}


class ThroughputTest:
    """Worker do thong luong; trang thai doc qua snapshot() (thread-safe)."""

    def __init__(self, gui):
        self.gui = gui
        self._lock = threading.Lock()
        self.state = {'running': False, 'series': [], 'samples': [], 'gen': None, 'summary': None}
        self._gen = None

    def snapshot(self, since=0):
        with self._lock:
            st = dict(self.state)
            st['samples'] = [s for s in self.state['samples'] if s['i'] > since]
        if self._gen is not None:
            st['gen'] = self._gen.stats()
        return st

    @staticmethod
    def _label(vname, vpn, ifname):
        colors = {i: c for c, i in WAN_IFACE.get(vname, {}).items()}
        if vpn == 0 and ifname in colors:
            return '{} ({})'.format(ifname, colors[ifname])
        return '{} (vpn {})'.format(ifname, vpn)

    @staticmethod
    def _pick(vname, keys, scope):
        """Chon interface can ve: 'wan' = cong WAN (vpn 0) + LAN vpn 1; 'all' = moi interface
        tru system/loopback/mgmt."""
        wan = set(WAN_IFACE.get(vname, {}).values())
        if scope == 'all':
            sel = [k for k in keys if not re.match(r'(system|loopback|lo|eth0|mgmt)', k[1])]
        else:
            sel = [k for k in keys if (k[0] == 0 and k[1] in wan) or k[0] == 1]
        return sorted(sel)

    def _thread(self, ssh, opts):
        log = self.gui._log
        stop = self.gui._stop_event
        vname = opts['vedge']
        reader = gen = None
        samples = []                                   # (elapsed, label, rx_mbps, tx_mbps)
        with self._lock:
            self.state = {'running': True, 'vedge': vname, 'interval': opts['interval'],
                          'duration': opts['duration'], 'series': [], 'samples': [], 'gen': None,
                          'summary': None, 'started': datetime.now().strftime('%H:%M:%S')}
        self._gen = None

        log('\n' + '=' * 55 + '\n', 'sep')
        log('[THROUGHPUT] {} | chu ky {}s | thoi gian {}s{}\n'.format(
            vname, opts['interval'], opts['duration'],
            ' | tai VPCS {} -> {} ({} byte)'.format(opts['gen_src'], opts['gen_target'], opts['gen_size'])
            if opts.get('gen_src') else ''), 'hdr')
        try:
            self.gui._set_status('Dang nhap console {}...'.format(vname), True)
            reader = VedgeCounterReader(ssh, vname, opts['user'], opts['password'])
            t_prev, prev, raw = reader.read()
            keys = self._pick(vname, prev, opts['scope'])
            if not keys:
                log('  [!] Khong doc duoc bo dem interface. Output vEdge (cuoi):\n{}\n'.format(
                    raw[-600:]), 'err')
                return
            labels = {k: self._label(vname, *k) for k in keys}
            with self._lock:
                self.state['series'] = [{'key': '{}/{}'.format(*k), 'label': labels[k],
                                         'color': SERIES_COLORS[i % len(SERIES_COLORS)]}
                                        for i, k in enumerate(keys)]
            log('  [*] Interface: {}\n'.format(', '.join(labels[k] for k in keys)), 'info')

            if opts.get('gen_src'):
                gen = self._gen = LoadGenerator(ssh, opts['gen_src'], opts['gen_target'],
                                                opts['gen_size'], opts['gen_interval'])
                gen.start()
                log('  [*] Bat dau bom tai tu {} (ping -l {} -t)\n'.format(opts['gen_src'], opts['gen_size']), 'info')

            t0, n = t_prev, 0
            while t_prev - t0 < opts['duration']:
                if stop.wait(max(0.0, opts['interval'] - (time.time() - t_prev))):
                    log('  [i] Dung theo yeu cau.\n', 'info'); break
                t_now, cur, raw = reader.read()
                dt = t_now - t_prev
                if not cur or dt <= 0:
                    log('  [!] Lan doc loi (bo qua): {!r}\n'.format(_last_line(raw)[-80:]), 'err'); continue
                n += 1
                el = t_now - t0
                row, parts = {}, []
                for k in keys:
                    if k not in cur or k not in prev:
                        continue
                    drx, dtx = cur[k][0] - prev[k][0], cur[k][1] - prev[k][1]
                    if drx < 0 or dtx < 0:              # counter bi xoa / vEdge reboot
                        continue
                    rx, tx = drx * 8 / dt / 1e6, dtx * 8 / dt / 1e6
                    row['{}/{}'.format(*k)] = [round(rx, 4), round(tx, 4)]
                    samples.append((round(el, 2), labels[k], rx, tx))
                    parts.append('{} RX {:.3f} / TX {:.3f}'.format(labels[k], rx, tx))
                with self._lock:
                    self.state['samples'].append({'i': n, 't': round(el, 2), 'v': row})
                g = '  | tai {:.3f} Mbps'.format(gen.stats()['mbps']) if gen else ''
                log('    t={:6.1f}s  {} Mbps{}\n'.format(el, ' | '.join(parts), g), 'data')
                self.gui._set_status('Thong luong {} t={:.0f}/{}s'.format(vname, el, opts['duration']), True)
                t_prev, prev = t_now, cur
        except Exception as e:
            log('  [!] Loi do thong luong: {}\n'.format(e), 'err')
        finally:
            if gen is not None:
                gen.stop(); gen.join(3)
            if reader is not None:
                reader.close()
            summary = self._summarize(samples, gen)
            with self._lock:
                self.state['running'] = False
                self.state['summary'] = summary
                if gen is not None:
                    self.state['gen'] = gen.stats()
            self._gen = None

        self._report(vname, samples, summary, gen)

    @staticmethod
    def _summarize(samples, gen):
        per = {}
        for _, lab, rx, tx in samples:
            per.setdefault(lab, []).append((rx, tx))
        rows = []
        for lab, v in per.items():
            rxs, txs = [a for a, _ in v], [b for _, b in v]
            rows.append({'iface': lab, 'rx_avg': round(sum(rxs) / len(rxs), 4), 'rx_max': round(max(rxs), 4),
                         'tx_avg': round(sum(txs) / len(txs), 4), 'tx_max': round(max(txs), 4), 'n': len(v)})
        return {'ifaces': rows, 'gen': gen.stats() if gen else None}

    def _report(self, vname, samples, summary, gen):
        log = self.gui._log
        if not samples:
            log('  [!] Khong co mau nao -> khong xuat bao cao.\n', 'err')
            log('=' * 55 + '\n\n', 'sep'); return
        log('  ---- Tong ket (Mbps) ----\n', 'hdr')
        for r in summary['ifaces']:
            log('    {:<24} RX avg {:8.3f} max {:8.3f} | TX avg {:8.3f} max {:8.3f}\n'.format(
                r['iface'], r['rx_avg'], r['rx_max'], r['tx_avg'], r['tx_max']), 'ok')
        if gen:
            g = gen.stats()
            if g['error']:
                log('  [!] Bom tai loi: {}\n'.format(g['error']), 'err')
            log('    Goodput ICMP {} -> {}: {:.3f} Mbps ({} pps, {} goi tra loi, loss {}%)\n'.format(
                g['src'], g['target'], g['mbps'], g['pps'], g['replies'], g['loss']), 'ok')

        base = 'throughput_{}_{}'.format(vname, datetime.now().strftime('%Y%m%d_%H%M%S'))
        csv_path = os.path.join(LOG_DIR, base + '.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['Elapsed_s', 'Interface', 'RX_Mbps', 'TX_Mbps'])
            for el, lab, rx, tx in samples:
                w.writerow([el, lab, round(rx, 4), round(tx, 4)])
        log('  [OK] CSV: {}\n'.format(csv_path), 'ok')
        if HAS_MPL:
            png_path = os.path.join(LOG_DIR, base + '.png')
            self._chart(vname, samples, summary, png_path)
            log('  [OK] PNG: {}\n'.format(png_path), 'ok')
        log('=' * 55 + '\n\n', 'sep')

    @staticmethod
    def _chart(vname, samples, summary, path):
        labs = [r['iface'] for r in summary['ifaces']]
        fig, ax = plt.subplots(figsize=(11, 5))
        fig.patch.set_facecolor(ChartEngine.BG_DARK)
        title = 'Thong luong {} (Mbps)'.format(vname)
        if summary['gen']:
            title += ' - tai VPCS {:.3f} Mbps'.format(summary['gen']['mbps'])
        ChartEngine._dark(ax, title)
        for i, lab in enumerate(labs):
            pts = [(el, rx, tx) for el, l, rx, tx in samples if l == lab]
            c = SERIES_COLORS[i % len(SERIES_COLORS)]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=c, linewidth=1.6, label=lab + ' RX')
            ax.plot([p[0] for p in pts], [p[2] for p in pts], color=c, linewidth=1.6, linestyle='--',
                    label=lab + ' TX')
        ax.set_xlabel('Thoi gian (s)'); ax.set_ylabel('Mbps')
        ax.set_ylim(bottom=0)
        ax.legend(facecolor=ChartEngine.BG_DARK2, edgecolor=ChartEngine.EDGE, labelcolor=ChartEngine.TXT, fontsize=8)
        plt.tight_layout()
        plt.savefig(path, dpi=130, bbox_inches='tight')
        plt.close('all')
