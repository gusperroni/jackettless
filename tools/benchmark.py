# SPDX-License-Identifier: GPL-2.0-or-later
"""Measure jackettless search speed with `all_public`, to choose good default settings.

Two phases:

1. sync: time the first download of every Jackett definition into an empty folder, per number of
   download workers (`--sync-workers`).
2. grid: run real searches with every combination of `--threads`, `--budgets` (indexer_timeout)
   and `--timeouts` (per request), for each query, and record time to the first result, total time,
   number of results and failures by reason.

    python tools/benchmark.py --doh https://1.1.1.1/dns-query --json bench.json
    python tools/benchmark.py --skip-sync --threads 20 --budgets 30 --queries ubuntu
"""

import argparse
import collections
import itertools
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import jackettless as jl  # noqa: E402


def ints(text):
    return [int(x) for x in text.split(',') if x.strip()]


def reason_of(outcome):
    """Bucket the summary strings run_search returns for failed indexers."""
    text = str(outcome)
    for key, bucket in (('Cloudflare', 'cloudflare'), ('DDoS-Guard', 'cloudflare'), ('getaddrinfo', 'dns'),
                        ('DNS lookup', 'dns'), ('timeout', 'timeout'), ('timed out', 'timeout'),
                        ('429', 'rate-limit'), ('HTTP', 'http'), ('NetworkError', 'network')):
        if key in text:
            return bucket
    return 'other'


def phase_sync(workers_list, ref):
    rows = []
    for workers in workers_list:
        folder = tempfile.mkdtemp(prefix='jl-bench-sync-')
        try:
            store = jl.DefinitionStore(folder, ref, refresh_days=1)
            t0 = time.time()
            listing = store.sync(everything=True, workers=workers)
            seconds = time.time() - t0
            public = sum(1 for i in store.available_ids() if store.quick_type(i) == 'public')
            rows.append({'workers': workers, 'seconds': round(seconds, 1), 'listed': len(listing or {}),
                         'downloaded': len(store.available_ids()), 'public': public})
            print('sync  workers=%-3d %6.1fs  %d definitions, %d public' % (
                workers, seconds, len(store.available_ids()), public), flush=True)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    return rows


def phase_grid(data_dir, queries, threads, budgets, timeouts, doh, pause, backoff=False):
    rows = []
    for t, b, r in itertools.product(threads, budgets, timeouts):
        if r > b:
            continue
        for q in queries:
            cfg = json.loads(json.dumps(jl.DEFAULT_CONFIG))
            cfg.update({'indexers': {}, 'all_public': True, 'thread_count': t, 'indexer_timeout': b, 'timeout': r,
                        'dns_over_https': doh, 'refresh_days': 365, 'report_errors': 'none', 'dedup': 'off',
                        # off by default: paused indexers would make later combinations look faster
                        'backoff': backoff})
            first = [None]
            count = [0]
            t0 = time.time()

            def printer(row, first=first, count=count, t0=t0):
                if first[0] is None:
                    first[0] = time.time() - t0
                count[0] += 1

            summary = jl.run_search(q, 'all', printer, cfg, data_dir)
            total = time.time() - t0
            failed = {i: o for i, o in summary.items() if isinstance(o, str)}
            reasons = collections.Counter(reason_of(o) for o in failed.values())
            row = {'threads': t, 'indexer_timeout': b, 'timeout': r, 'query': q, 'total_s': round(total, 1),
                   'first_s': round(first[0], 1) if first[0] is not None else None, 'results': count[0],
                   'indexers': len(summary), 'ok': sum(1 for o in summary.values() if isinstance(o, int) and o > 0),
                   'failed': len(failed), 'reasons': dict(reasons)}
            rows.append(row)
            print('grid  threads=%-2d budget=%-2d timeout=%-2d %-8s total=%6.1fs first=%5ss results=%-5d '
                  'ok=%-3d failed=%-3d %s' % (t, b, r, q, total, row['first_s'], count[0], row['ok'], len(failed),
                                              dict(reasons)), flush=True)
            time.sleep(pause)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--queries', default='ubuntu,dune')
    ap.add_argument('--threads', default='10,20,30')
    ap.add_argument('--budgets', default='20,30,45', help='indexer_timeout values (seconds)')
    ap.add_argument('--timeouts', default='10,15', help='per-request timeout values (seconds)')
    ap.add_argument('--sync-workers', default='8,16')
    ap.add_argument('--skip-sync', action='store_true')
    ap.add_argument('--ref', default='master')
    ap.add_argument('--doh', help='DNS-over-HTTPS fallback URL (record it: it changes the results)')
    ap.add_argument('--pause', type=float, default=5, help='seconds between searches, to be kind to the sites')
    ap.add_argument('--backoff', action='store_true',
                    help='keep indexer back-off on (to measure it with repeated searches; biases the grid)')
    ap.add_argument('--json', help='write all measurements to this file')
    args = ap.parse_args()

    jl.install_dns_fallback(args.doh)
    report = {'doh': args.doh, 'started': time.strftime('%Y-%m-%d %H:%M:%S')}
    if not args.skip_sync:
        report['sync'] = phase_sync(ints(args.sync_workers), args.ref)
    data_dir = tempfile.mkdtemp(prefix='jl-bench-grid-')
    try:
        jl.DefinitionStore(data_dir, args.ref, refresh_days=365).sync(everything=True, workers=16)
        report['grid'] = phase_grid(data_dir, [q.strip() for q in args.queries.split(',') if q.strip()],
                                    ints(args.threads), ints(args.budgets), ints(args.timeouts), args.doh, args.pause,
                                    args.backoff)
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=1)


if __name__ == '__main__':
    main()
