#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdwan_reliability.py  –  Do DO TIN CAY qua vManage REST API (chi DO, khong tu tat thiet bi)
================================================================
  1. Link Failover Time + Packet Recovery Rate: tong hop moi lan do o tab SD-WAN Failover
     (log/failover_*.csv) -> so lan, RTO min / TB / max, PRR theo vEdge bi cat.
  2. Controller Recovery Time: nguoi lam tu tat roi bat lai vSmart. Tool doc control
     connections cua moi vEdge (vManage hoi qua NETCONF, khong phu thuoc vSmart) + 1 vEdge
     ping lien tuc qua overlay -> thoi gian vEdge mat vSmart, thoi gian ket noi lai sau khi
     vSmart song lai, va data plane co mat goi khong (OMP graceful restart).
  3. Availability: theo doi dai han; moi chu ky vEdge cua tung site ping dich vu dao tao o
     campus chinh (mac dinh WebServer 10.1.1.10) -> % thoi gian dung duoc, su co, MTTR/MTBF.
Packet Recovery Rate = goi nhan / goi gui trong cua so su co x 100 %.
"""
import csv, glob, os, re, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from campus_ping_tool import LOG_DIR, HAS_MPL, ChartEngine, CYAN, GREEN, RED, ORANGE, PURPLE, YELLOW
from sdwan_monitor import VEDGE_NAMES, SITE_IDS, SITE_LABEL, vedge_ping, site_vedges, _save_png, _mean, _fmt


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _stamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _prr(pings, t_from, t_to):
    """(gui, mat, PRR %) cua cac goi trong [t_from, t_to]."""
    win = [p for p in pings if t_from <= p[0] <= t_to]
    lost = sum(1 for p in win if not p[1])
    return len(win), lost, (round((len(win) - lost) / len(win) * 100, 2) if win else None)


def _vline(ax, t, label, color):
    if t is not None:
        ax.axvline(t, color=color, linestyle='--', linewidth=1.2)
        ax.text(t, ax.get_ylim()[1], ' ' + label, color=color, fontsize=8, va='top')


# =========================================================
#  1. LINK FAILOVER TIME + PACKET RECOVERY RATE (tong hop tab Failover)
# =========================================================
def _read_failover(path):
    try:
        with open(path, encoding='utf-8') as f:
            rows = list(csv.reader(f))
    except OSError:
        return None
    last = next((r for r in reversed(rows) if r and r[0] == 'watch'), None)
    if not last:
        return None                         # file cua tool cu (console) - khong co dong tong ket
    d = dict(zip(last[0::2], last[1::2]))
    sent, lost = _num(d.get('sent')), _num(d.get('lost'))
    prr = _num(d.get('PRR_pct'))
    if prr is None and sent:
        prr = round((sent - (lost or 0)) / sent * 100, 2)
    m = re.search(r'_(\d{8}_\d{6})\.csv$', path)
    when = datetime.strptime(m.group(1), '%Y%m%d_%H%M%S') if m else datetime.fromtimestamp(os.path.getmtime(path))
    return {'file': os.path.basename(path), 'time': when, 'watch': d.get('watch', '?'), 'probe': d.get('probe', ''),
            'target': d.get('target', ''), 'rto': _num(d.get('RTO_s')), 'lost': lost, 'sent': sent, 'prr': prr}


def failover_summary_job(ctx, opts):
    """opts: since (datetime hoac None)."""
    log = ctx._log
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[TIN CAY] Link Failover Time + Packet Recovery Rate - tong hop log/failover_*.csv\n', 'hdr')
    runs, skipped = [], 0
    for p in sorted(glob.glob(os.path.join(LOG_DIR, 'failover_*.csv'))):
        r = _read_failover(p)
        if r is None:
            skipped += 1
        elif not opts.get('since') or r['time'] >= opts['since']:
            runs.append(r)
    if skipped:
        log('  [i] Bo qua {} file khong co dong tong ket (tool console cu)\n'.format(skipped), 'info')
    if not runs:
        log('  [!] Chua co lan do nao{} - chay tab SD-WAN Failover truoc.\n'.format(
            ' tu {:%d/%m/%Y %H:%M}'.format(opts['since']) if opts.get('since') else ''), 'err')
        return
    log('  {:<17} {:<14} {:<14} {:>8} {:>10} {:>8}\n'.format('Thoi diem', 'vEdge bi cat', 'vEdge do', 'RTO (s)',
                                                            'Mat/Gui', 'PRR %'), 'data')
    for r in runs:
        log('  {:%d/%m %H:%M:%S}    {:<14} {:<14} {:>8} {:>10} {:>8}\n'.format(
            r['time'], r['watch'], r['probe'], _fmt(r['rto']), '{:.0f}/{:.0f}'.format(r['lost'] or 0, r['sent'] or 0),
            _fmt(r['prr'])), 'ok' if r['rto'] is not None else 'err')
    groups = {}
    for r in runs:
        groups.setdefault(r['watch'], []).append(r)
    summ = []
    for w, rs in sorted(groups.items()):
        rtos = [r['rto'] for r in rs if r['rto'] is not None]
        prrs = [r['prr'] for r in rs if r['prr'] is not None]
        summ.append({'watch': w, 'n': len(rs), 'n_rto': len(rtos), 'min': min(rtos) if rtos else None,
                     'avg': _mean(rtos), 'max': max(rtos) if rtos else None, 'prr': _mean(prrs),
                     'lost': sum(r['lost'] or 0 for r in rs), 'sent': sum(r['sent'] or 0 for r in rs)})
    log('\n  Tong hop theo vEdge bi cat:\n', 'hdr')
    log('  {:<14} {:>6} {:>8} {:>8} {:>8} {:>8} {:>12}\n'.format('vEdge', 'So lan', 'RTO min', 'RTO TB', 'RTO max',
                                                               'PRR TB', 'Mat/Gui'), 'data')
    for s in summ:
        log('  {:<14} {:>6} {:>8} {:>8} {:>8} {:>8} {:>12}\n'.format(
            s['watch'], '{}/{}'.format(s['n_rto'], s['n']), _fmt(s['min']), _fmt(s['avg']), _fmt(s['max']),
            _fmt(s['prr']), '{:.0f}/{:.0f}'.format(s['lost'], s['sent'])), 'ok')
    log('  (So lan = lan xac dinh duoc RTO / tong so lan. Do phan giai ~1,2 s/goi.)\n', 'info')

    name = 'tin_cay_failover_{}'.format(_stamp())
    with open(os.path.join(LOG_DIR, name + '.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['vEdge_bi_cat', 'So_lan', 'Lan_co_RTO', 'RTO_min_s', 'RTO_TB_s', 'RTO_max_s', 'PRR_TB_pct',
                    'Goi_mat', 'Goi_gui'])
        for s in summ:
            w.writerow([s['watch'], s['n'], s['n_rto'], s['min'], s['avg'] and round(s['avg'], 2), s['max'],
                        s['prr'] and round(s['prr'], 2), s['lost'], s['sent']])
        w.writerow([])
        w.writerow(['Thoi_diem', 'File', 'vEdge_bi_cat', 'vEdge_do', 'Dich', 'RTO_s', 'Goi_mat', 'Goi_gui', 'PRR_pct'])
        for r in runs:
            w.writerow(['{:%Y-%m-%d %H:%M:%S}'.format(r['time']), r['file'], r['watch'], r['probe'], r['target'],
                        r['rto'], r['lost'], r['sent'], r['prr']])
    log('  [OK] CSV: {}.csv\n'.format(name), 'ok')
    if HAS_MPL:
        def draw(fig):
            ax1, ax2 = fig.add_subplot(1, 2, 1), fig.add_subplot(1, 2, 2)
            xs = list(range(len(summ)))
            labels = [s['watch'] for s in summ]
            ChartEngine._dark(ax1, 'Link Failover Time (s): min / TB / max')
            for i, (k, c) in enumerate((('min', GREEN), ('avg', CYAN), ('max', ORANGE))):
                vals = [s[k] or 0 for s in summ]
                bars = ax1.bar([x + (i - 1) * 0.27 for x in xs], vals, 0.27, color=c, label=k.upper().replace('AVG', 'TB'))
                for b, v in zip(bars, vals):
                    ax1.text(b.get_x() + b.get_width() / 2, v, '{:.1f}'.format(v), ha='center', va='bottom',
                             color=ChartEngine.TXT, fontsize=7)
            ax1.legend(facecolor=ChartEngine.BG_DARK2, labelcolor=ChartEngine.TXT, fontsize=8)
            ChartEngine._dark(ax2, 'Packet Recovery Rate TB (%)')
            vals = [s['prr'] or 0 for s in summ]
            bars = ax2.bar(xs, vals, 0.5, color=[GREEN if v >= 99 else YELLOW if v >= 90 else RED for v in vals])
            for b, v in zip(bars, vals):
                ax2.text(b.get_x() + b.get_width() / 2, v, '{:.1f}'.format(v), ha='center', va='bottom',
                         color=ChartEngine.TXT, fontsize=8)
            ax2.set_ylim(0, 105)
            for ax in (ax1, ax2):
                ax.set_xticks(xs)
                ax.set_xticklabels(labels, color=ChartEngine.TXT, fontsize=8)
        _save_png(os.path.join(LOG_DIR, name + '.png'), draw, size=(13, 5))
        log('  [OK] PNG: {}.png\n'.format(name), 'ok')


# =========================================================
#  2. CONTROLLER RECOVERY TIME (vSmart)
# =========================================================
def _vsmart_conns(vm, sysip):
    rows = vm.control(sysip, 20)
    return sum(1 for s in rows if s.get('peer-type') == 'vsmart' and s.get('state') == 'up')


def _vsmart_reachable(vm):
    vs = [d for d in vm.devices() if (d.get('personality') or d.get('device-type')) == 'vsmart']
    return bool(vs) and all(d.get('reachability') == 'reachable' for d in vs)


def controller_recovery_job(ctx, vm, opts):
    """opts: probe (sysip vEdge ping), target, wait_down, duration, interval.
    Moc: LOST = vEdge dau tien mat vSmart; BACK = vManage thay vSmart reachable lai;
    RESTORED = moi vEdge co lai vSmart. Recovery = RESTORED - BACK; Outage = RESTORED - LOST."""
    log, stop = ctx._log, ctx._stop_event
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[TIN CAY] Controller Recovery Time (vSmart)\n', 'hdr')
    ctx._set_status('Controller recovery: lay moc...', True)
    reach = [d.get('system-ip') for d in vm.vedges() if d.get('reachability') == 'reachable']

    def read_all(ips):
        def one(ip):
            try:
                return _vsmart_conns(vm, ip)
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=8) as ex:
            return dict(zip(ips, ex.map(one, ips)))

    base = read_all(reach)
    edges = [ip for ip, n in base.items() if n]
    for ip, n in base.items():
        if not n:
            log('  [i] Bo qua {}: hien khong co ket noi vSmart\n'.format(VEDGE_NAMES.get(ip, ip)), 'info')
    if not edges:
        log('  [!] Khong vEdge nao dang ket noi vSmart - khong co moc de do.\n', 'err')
        return
    if not _vsmart_reachable(vm):
        log('  [!] vManage dang thay vSmart unreachable - bat vSmart len truoc roi chay lai.\n', 'err')
        return
    r0 = vedge_ping(vm, opts['probe'], opts['target'], 3)
    if not r0.success:
        log('  [!] {} chua ping duoc {} - chon dich khac.\n'.format(VEDGE_NAMES.get(opts['probe']), opts['target']), 'err')
        return
    log('  [*] Moc: {}/{} vEdge ket noi vSmart | ping {} -> {} OK {:.2f} ms\n'.format(
        len(edges), len(reach), VEDGE_NAMES.get(opts['probe']), opts['target'], r0.avg_latency), 'ok')
    log('  >>> BAY GIO hay TAT vSmart (Stop node tren EVE), cho 1-3 phut roi BAT lai. Tool cho mat ket noi '
        'toi {} s. <<<\n'.format(opts['wait_down']), 'hdr')

    t0 = time.time()
    pings, samples = [], []           # (t, ok, rtt) | (t, so vEdge co vSmart, tong, vSmart reachable)
    halt = threading.Event()

    def pinger():
        while not halt.is_set():
            ts = round(time.time() - t0, 2)
            try:
                r = vedge_ping(vm, opts['probe'], opts['target'], 1)
                pings.append((ts, r.success, r.avg_latency if r.success else None))
            except Exception:
                pings.append((ts, False, None))
                halt.wait(1)

    th = threading.Thread(target=pinger, daemon=True)
    th.start()
    last = {ip: base[ip] for ip in edges}
    t_lost = t_back = t_rest = None
    vs_down_seen = False
    try:
        while not stop.is_set():
            cur = read_all(edges)
            for ip, n in cur.items():
                if n is not None:
                    last[ip] = n
            try:
                vs_ok = _vsmart_reachable(vm)
            except Exception:
                vs_ok = None
            ts = round(time.time() - t0, 2)
            conn = sum(1 for ip in edges if last[ip] >= 1)
            samples.append((ts, conn, len(edges), vs_ok))
            ctx._set_status('Controller recovery t={:.0f}s: {}/{} vEdge co vSmart'.format(ts, conn, len(edges)), True)
            log('    t={:6.1f}s  vEdge co vSmart {}/{} | vSmart {}\n'.format(
                ts, conn, len(edges), {True: 'reachable', False: 'UNREACHABLE', None: '?'}[vs_ok]),
                'data' if conn == len(edges) else 'err')
            if vs_ok is False:
                vs_down_seen = True
            if t_lost is None:
                if conn < len(edges) or vs_ok is False:
                    t_lost = ts
                    log('  [LOST] vEdge bat dau mat vSmart tai t={:.1f}s\n'.format(ts), 'hdr')
                elif ts > opts['wait_down']:
                    log('  [!] Het {} s ma vSmart van ket noi day du.\n'.format(opts['wait_down']), 'err')
                    break
            else:
                if t_back is None and vs_down_seen and vs_ok:
                    t_back = ts
                    log('  [BACK] vManage thay vSmart reachable lai tai t={:.1f}s\n'.format(ts), 'ok')
                if conn == len(edges) and (vs_ok or vs_ok is None) and ts > t_lost:
                    t_rest = ts
                    log('  [RESTORED] Moi vEdge da ket noi lai vSmart tai t={:.1f}s\n'.format(ts), 'ok')
                    break
                if ts - t_lost > opts['duration']:
                    log('  [!] Qua {} s sau khi mat ket noi ma chua phuc hoi du.\n'.format(opts['duration']), 'err')
                    break
            stop.wait(opts['interval'])
        if t_rest is not None:
            stop.wait(5)                  # them vai goi sau phuc hoi cho bieu do
    finally:
        halt.set()
        th.join(5)
    if stop.is_set():
        log('  [i] Dung theo yeu cau.\n', 'info')

    end = t_rest if t_rest is not None else (pings[-1][0] if pings else 0)
    sent, lost, prr = _prr(pings, t_lost if t_lost is not None else 0, end)
    outage = None if t_lost is None or t_rest is None else round(t_rest - t_lost, 1)
    recovery = None if t_back is None or t_rest is None else round(t_rest - t_back, 1)
    log('  ---- Ket qua ----\n', 'hdr')
    log('    Mat ket noi control (LOST -> RESTORED):        {}\n'.format(
        '{} s'.format(outage) if outage is not None else '--'), 'info')
    log('    Controller Recovery Time (vSmart song -> du vEdge): {}\n'.format(
        '{} s'.format(recovery) if recovery is not None else '-- (vManage khong thay vSmart down/up)'),
        'ok' if recovery is not None else 'err')
    log('    Data plane trong luc mat vSmart: mat {}/{} goi -> Packet Recovery Rate {}\n'.format(
        lost, sent, '{} %'.format(prr) if prr is not None else '--'), 'ok' if lost == 0 else 'err')
    log('    (Do phan giai: control ~{} s/lan doc, ping ~1,2 s/goi)\n'.format(opts['interval']), 'info')

    name = 'tin_cay_controller_{}'.format(_stamp())
    with open(os.path.join(LOG_DIR, name + '.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['t_s', 'vedge_co_vsmart', 'tong_vedge', 'vsmart_reachable'])
        w.writerows(samples)
        w.writerow([])
        w.writerow(['t_s', 'ping_ok', 'rtt_ms'])
        for ts, ok, rtt in pings:
            w.writerow([ts, int(ok), '' if rtt is None else round(rtt, 3)])
        w.writerow([])
        w.writerow(['LOST_s', t_lost, 'BACK_s', t_back, 'RESTORED_s', t_rest, 'Outage_s', outage,
                    'Recovery_s', recovery, 'lost', lost, 'sent', sent, 'PRR_pct', prr])
    log('  [OK] CSV: {}.csv\n'.format(name), 'ok')
    if HAS_MPL and samples:
        def draw(fig):
            ax1, ax2 = fig.add_subplot(2, 1, 1), fig.add_subplot(2, 1, 2, sharex=None)
            ChartEngine._dark(ax1, 'So vEdge co ket noi vSmart')
            ax1.step([s[0] for s in samples], [s[1] for s in samples], where='post', color=CYAN, linewidth=2)
            ax1.set_ylim(-0.3, max(s[2] for s in samples) + 0.8)
            ChartEngine._dark(ax2, 'Ping {} -> {} qua overlay (ms, x do = mat goi)'.format(
                VEDGE_NAMES.get(opts['probe']), opts['target']))
            ok = [p for p in pings if p[1]]
            ax2.plot([p[0] for p in ok], [p[2] for p in ok], 'o-', color=GREEN, markersize=3, linewidth=1)
            bad = [p[0] for p in pings if not p[1]]
            ax2.plot(bad, [0] * len(bad), 'x', color=RED, markersize=7)
            ax2.set_xlabel('t (s)')
            for ax in (ax1, ax2):
                _vline(ax, t_lost, 'LOST', RED)
                _vline(ax, t_back, 'vSmart BACK', YELLOW)
                _vline(ax, t_rest, 'RESTORED', GREEN)
        _save_png(os.path.join(LOG_DIR, name + '.png'), draw, size=(12, 7))
        log('  [OK] PNG: {}.png\n'.format(name), 'ok')
    log('=' * 55 + '\n\n', 'sep')


# =========================================================
#  3. AVAILABILITY (theo doi dai han)
# =========================================================
def availability_job(ctx, vm, opts):
    """opts: target, duration_s, interval. Moi chu ky: vEdge reachable dau tien cua tung site
    ping target 2 goi (site 100: qua LAN, chi nhanh: qua overlay). Site khong con vEdge
    reachable hoac ping mat het = DOWN."""
    log, stop = ctx._log, ctx._stop_event
    target, interval = opts['target'], opts['interval']
    log('\n' + '=' * 55 + '\n', 'sep')
    log('[TIN CAY] Availability - moi {} s, toi da {:.0f} phut, dich vu {} (bam Dung de ket thuc som)\n'.format(
        interval, opts['duration_s'] / 60, target), 'hdr')
    name = 'tin_cay_availability_{}'.format(_stamp())
    path = os.path.join(LOG_DIR, name + '.csv')
    rows = []                                   # (t, sid, ok, rtt, vedge)
    f = open(path, 'w', newline='', encoding='utf-8')
    w = csv.writer(f)
    w.writerow(['thoi_diem', 't_s', 'site', 'vedge', 'up', 'rtt_ms'])
    t0, cycle, prev = time.time(), 0, {}
    try:
        while not stop.is_set() and time.time() - t0 < opts['duration_s']:
            cycle += 1
            t_start = time.time()
            try:
                reach = {d.get('system-ip') for d in vm.vedges() if d.get('reachability') == 'reachable'}
            except Exception as e:
                log('  [!] vManage: {}\n'.format(str(e)[:120]), 'err')
                reach = None                    # khong biet -> van thu ping
            parts, changed = [], False
            for sid in SITE_IDS:
                if stop.is_set():
                    break
                cands = [ip for ip in site_vedges(sid) if reach is None or ip in reach]
                ok, rtt, src = False, None, cands[0] if cands else ''
                if src:
                    try:
                        r = vedge_ping(vm, src, target, 2)
                        ok, rtt = r.success, (r.avg_latency if r.success else None)
                    except Exception:
                        ok = False
                ts = round(time.time() - t0, 1)
                rows.append((ts, sid, ok, rtt, VEDGE_NAMES.get(src, '-')))
                w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ts, sid, VEDGE_NAMES.get(src, '-'),
                            int(ok), '' if rtt is None else round(rtt, 2)])
                parts.append('S{} {}'.format(sid, '{:.1f}ms'.format(rtt) if ok else 'DOWN'))
                if prev.get(sid, True) != ok:
                    changed = True
                    log('  [{}] {} {} tai t={:.0f}s\n'.format('UP' if ok else 'DOWN', SITE_LABEL[sid],
                                                           'phuc hoi' if ok else 'mat dich vu', ts),
                        'ok' if ok else 'err')
                prev[sid] = ok
            f.flush()
            if changed or cycle % 10 == 1:
                log('  #{:<4} {:%H:%M:%S}  {}\n'.format(cycle, datetime.now(), ' | '.join(parts)), 'data')
            up_now = sum(1 for sid in SITE_IDS if prev.get(sid))
            ctx._set_status('Availability {:.0f}/{:.0f} phut - {}/{} site UP'.format(
                (time.time() - t0) / 60, opts['duration_s'] / 60, up_now, len(SITE_IDS)), True)
            stop.wait(max(0, interval - (time.time() - t_start)))
    finally:
        f.close()
    if stop.is_set():
        log('  [i] Dung theo yeu cau - tinh tren du lieu da co.\n', 'info')
    total = time.time() - t0
    log('  ---- Ket qua ({:.1f} phut, {} chu ky) ----\n'.format(total / 60, cycle), 'hdr')
    log('  {:<22} {:>8} {:>13} {:>8} {:>9} {:>9}\n'.format('Site', 'Mau', 'Availability', 'Su co', 'MTTR (s)',
                                                         'Down (s)'), 'data')
    summ = {}
    for sid in SITE_IDS:
        s = [r for r in rows if r[1] == sid]
        up = sum(1 for r in s if r[2])
        incidents, run = [], None             # [(t_bat_dau, so_mau_down)]
        for r in s:
            if not r[2]:
                run = [run[0], run[1] + 1] if run else [r[0], 1]
            elif run:
                incidents.append(tuple(run)); run = None
        if run:
            incidents.append(tuple(run))
        avail = up / len(s) * 100 if s else None
        down_s = (len(s) - up) * interval
        mttr = _mean([n * interval for _, n in incidents])
        summ[sid] = {'n': len(s), 'up': up, 'avail': avail, 'inc': incidents, 'down_s': down_s, 'mttr': mttr,
                     'mtbf': (up * interval / len(incidents)) if incidents else None}
        log('  {:<22} {:>8} {:>12} {:>8} {:>9} {:>9}\n'.format(
            SITE_LABEL[sid], len(s), '{} %'.format(_fmt(avail, 3)) if avail is not None else '--', len(incidents),
            _fmt(mttr, 0), down_s), 'ok' if avail == 100 else 'info' if avail and avail >= 99 else 'err')
        for t_inc, n in incidents:
            log('      su co tai t={:.0f}s, ~{} s ({} mau)\n'.format(t_inc, n * interval, n), 'err')
    log('  (Availability = mau UP / tong mau. Down va MTTR uoc theo so mau x chu ky {} s.)\n'.format(interval), 'info')
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([])
        w.writerow(['site', 'ten', 'mau', 'mau_up', 'availability_pct', 'so_su_co', 'down_s', 'MTTR_s', 'MTBF_s'])
        for sid in SITE_IDS:
            s = summ[sid]
            w.writerow([sid, SITE_LABEL[sid], s['n'], s['up'], s['avail'] and round(s['avail'], 3), len(s['inc']),
                        s['down_s'], s['mttr'], s['mtbf'] and round(s['mtbf'])])
    log('  [OK] CSV: {}.csv\n'.format(name), 'ok')
    if HAS_MPL and rows:
        def draw(fig):
            ax1, ax2 = fig.add_subplot(1, 3, (1, 2)), fig.add_subplot(1, 3, 3)
            ChartEngine._dark(ax1, 'Trang thai dich vu {} theo thoi gian (xanh = UP, do = DOWN)'.format(target))
            for i, sid in enumerate(SITE_IDS):
                s = [r for r in rows if r[1] == sid]
                ax1.broken_barh([(r[0], interval) for r in s], (i - 0.35, 0.7),
                                facecolors=[GREEN if r[2] else RED for r in s])
            ax1.set_yticks(range(len(SITE_IDS)))
            ax1.set_yticklabels([SITE_LABEL[s] for s in SITE_IDS], color=ChartEngine.TXT, fontsize=8)
            ax1.set_xlabel('t (s)')
            ChartEngine._dark(ax2, 'Availability (%)')
            vals = [summ[s]['avail'] or 0 for s in SITE_IDS]
            bars = ax2.barh(range(len(SITE_IDS)), vals,
                            color=[GREEN if v >= 99.9 else YELLOW if v >= 99 else RED for v in vals])
            for b, v in zip(bars, vals):
                ax2.text(v, b.get_y() + b.get_height() / 2, ' {:.2f}'.format(v), va='center',
                         color=ChartEngine.TXT, fontsize=8)
            ax2.set_yticks(range(len(SITE_IDS)))
            ax2.set_yticklabels([SITE_LABEL[s] for s in SITE_IDS], color=ChartEngine.TXT, fontsize=8)
            ax2.set_xlim(min(vals + [90]) - 1, 101)
        _save_png(os.path.join(LOG_DIR, name + '.png'), draw, size=(15, 4.5))
        log('  [OK] PNG: {}.png\n'.format(name), 'ok')
    log('=' * 55 + '\n\n', 'sep')
