# SPDX-License-Identifier: GPL-2.0-or-later
"""Measure how much of Jackett's Cardigann definitions jackettless can handle.

Static analysis (default): parses every YAML definition and checks that every
feature it uses (filters, selectors, regexes, login method, response type) is
supported by jackettless.

Live mode (--live): runs a real search against every definition of the chosen
types (public by default) and classifies the outcome.

Examples:
    python tools/coverage.py                       # download definitions + static report
    python tools/coverage.py --defs path/to/Definitions
    python tools/coverage.py --live --query ""     # latest releases from every public indexer
    python tools/coverage.py --live --doh https://1.1.1.1/dns-query --json report.json
"""

import argparse
import collections
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import jackettless as jl  # noqa: E402

ROW_FILTERS = {'andmatch', 'strdump'}
LOGIN_METHODS = {'post', 'form', 'cookie', 'get', 'oneurl'}


def dummy_variables(idx):
    v = idx._query_variables('test', None)  # noqa: SLF001
    v['.Keywords'] = 'test'
    v['.Query.Keywords'] = 'test'
    v['.Categories'] = ['1']
    for k in list(v):
        if k.startswith('.Config.') and v[k] is None:
            v[k] = ''
    return v


def walk(node, path=()):
    """Yield (path, key, value) for every mapping entry in the definition."""
    if isinstance(node, dict):
        for k, val in (node.pairs if isinstance(node, jl.OMap) else node.items()):
            yield path, k, val
            yield from walk(val, path + (k,))
    elif isinstance(node, list):
        for i, val in enumerate(node):
            yield from walk(val, path + (i,))


def check_selector(sel, variables, problems, where, json_mode=False):
    if sel is None:
        return
    try:
        text = jl.apply_template(str(sel), variables)
    except Exception as e:  # noqa: BLE001
        problems.append('template:%s' % type(e).__name__)
        return
    if json_mode:
        return
    try:
        doc = jl.parse_html('<div></div>')
        jl.select_all(doc, text)
    except jl.SelectorError as e:
        msg = str(e)
        m = re.search(r'unsupported pseudo-class (:[\w-]+)', msg)
        problems.append('selector:%s' % (m.group(1) if m else 'syntax'))
        if os.environ.get('COVERAGE_DEBUG'):
            print(where, repr(text), msg, file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        problems.append('selector:%s' % type(e).__name__)


def check_regex(pattern, problems):
    try:
        jl.net_regex(str(pattern))
    except Exception as e:  # noqa: BLE001
        problems.append('regex')
        if os.environ.get('COVERAGE_DEBUG'):
            print('regex', repr(pattern), e, file=sys.stderr)


def check_filters(filters, problems, row=False):
    for f in jl.as_list(filters):
        if not isinstance(f, dict):
            continue
        name = f.get('name')
        allowed = ROW_FILTERS if row else jl.SUPPORTED_FILTERS
        if name not in allowed:
            problems.append('filter:%s' % name)
        args = jl.as_list(f.get('args'))
        if name in ('regexp', 're_replace') and args:
            check_regex(args[0], problems)


def analyse(ident, d):
    """Return (info, problems, warnings) for one parsed definition."""
    problems = []
    warnings = []
    info = {'id': ident, 'type': str(d.get('type', '?')).lower(), 'name': d.get('name')}
    try:
        idx = jl.CardigannIndexer(d, {}, tempfile.gettempdir())
    except Exception as e:  # noqa: BLE001
        return info, ['init:%s' % e], warnings
    variables = dummy_variables(idx)
    settings_types = {str(s.get('type')) for s in jl.as_list(d.get('settings')) if isinstance(s, dict)}
    if 'info_flaresolverr' in settings_types:
        warnings.append('cloudflare-likely')
    login = d.get('login')
    if isinstance(login, dict):
        method = str(login.get('method') or 'form').lower()
        info['login'] = method
        if method not in LOGIN_METHODS:
            problems.append('login:%s' % method)
        if isinstance(login.get('captcha'), dict):
            warnings.append('captcha')
    search = d.get('search') or {}
    rtypes = {str(jl._get(jl._get(p, 'response') or {}, 'type', 'html')).lower()  # noqa: SLF001
              for p in idx.paths}
    info['response'] = sorted(rtypes)
    json_mode = rtypes == {'json'}
    for t in rtypes:
        if t not in ('html', 'json', 'xml'):
            problems.append('response:%s' % t)
    rows = jl._get(search, 'rows') or {}  # noqa: SLF001
    if not json_mode:
        check_selector(jl._get(rows, 'selector'), variables, problems, 'rows')  # noqa: SLF001
    check_filters(jl._get(rows, 'filters'), problems, row=True)  # noqa: SLF001
    check_filters(jl._get(search, 'keywordsfilters'), problems)  # noqa: SLF001
    check_filters(jl._get(search, 'preprocessingfilters'), problems)  # noqa: SLF001
    for key, block in jl._pairs(jl._get(search, 'fields')):  # noqa: SLF001
        if not isinstance(block, dict):
            continue
        check_selector(block.get('selector'), variables, problems, key, json_mode)
        if block.get('remove') and not json_mode:
            check_selector(block.get('remove'), variables, problems, key)
        for ck, _ in jl._pairs(block.get('case')):  # noqa: SLF001
            if not json_mode and ck != '*':
                check_selector(ck, variables, problems, key)
        check_filters(block.get('filters'), problems)
    dl = d.get('download')
    if isinstance(dl, dict):
        for sel in jl.as_list(dl.get('selectors')):
            if isinstance(sel, dict):
                check_selector(sel.get('selector'), variables, problems, 'download')
                check_filters(sel.get('filters'), problems)
    if isinstance(login, dict):
        for key, block in jl._pairs(login.get('selectorinputs')):  # noqa: SLF001
            if isinstance(block, dict):
                check_selector(block.get('selector'), variables, problems, 'login')
        test = login.get('test')
        if isinstance(test, dict):
            check_selector(test.get('selector'), variables, problems, 'login.test')
    for _, key, val in walk(d):
        if isinstance(val, str) and '{{' in val:
            try:
                jl.apply_template(val, variables)
            except Exception as e:  # noqa: BLE001
                problems.append('template:%s' % type(e).__name__)
    return info, sorted(set(problems)), warnings


def load_defs(defs_dir):
    out = {}
    for name in sorted(os.listdir(defs_dir)):
        if name.endswith('.yml'):
            with open(os.path.join(defs_dir, name), encoding='utf-8-sig') as f:
                out[name[:-4]] = f.read()
    return out


def static_report(texts):
    results = []
    for ident, text in texts.items():
        try:
            d = jl.yaml_load(text)
        except Exception as e:  # noqa: BLE001
            results.append(({'id': ident, 'type': '?'}, ['yaml:%s' % e], []))
            continue
        results.append(analyse(ident, d))
    by_type = collections.defaultdict(lambda: [0, 0])
    reasons = collections.Counter()
    warn = collections.Counter()
    for info, problems, warnings in results:
        by_type[info['type']][0] += 1
        if not problems:
            by_type[info['type']][1] += 1
        for p in problems:
            reasons[p] += 1
        for w in warnings:
            warn[(info['type'], w)] += 1
    total = sum(v[0] for v in by_type.values())
    ok = sum(v[1] for v in by_type.values())
    print('\n== Static analysis: %d definitions ==' % total)
    print('fully supported features: %d (%.1f%%)' % (ok, 100.0 * ok / max(total, 1)))
    for t, (n, k) in sorted(by_type.items()):
        print('  %-13s %3d / %3d  (%.1f%%)' % (t, k, n, 100.0 * k / max(n, 1)))
    if reasons:
        print('unsupported features (definitions affected):')
        for r, n in reasons.most_common():
            print('  %-40s %d' % (r, n))
    if warn:
        print('warnings (not errors, may block at runtime):')
        for (t, w), n in sorted(warn.items()):
            print('  %-13s %-20s %d' % (t, w, n))
    return results


def classify(exc):
    """Group jackettless.describe_error() reasons into report buckets."""
    if isinstance(exc, jl.LoginError):
        return 'login'
    reason = jl.describe_error(exc)
    buckets = {'Cloudflare': 'cloudflare', 'timeout': 'timeout', 'DNS blocked/failed': 'dns',
               'network error': 'network'}
    if reason in buckets:
        return buckets[reason]
    if 'HTTP' in reason or 'redirected' in reason:
        return 'http'
    return 'parse/other'


def live_report(texts, types, query, workers, budget, cfg_overrides):
    data_dir = tempfile.mkdtemp(prefix='jackettless-cov-')
    targets = []
    for ident, text in texts.items():
        m = re.search(r'^type:\s*([\w-]+)', text, re.M)
        if m and m.group(1).lower() in types:
            targets.append(ident)
    print('\n== Live test: %d definitions (%s), query=%r ==' % (len(targets), ','.join(sorted(types)), query))

    def one(ident):
        t0 = time.time()
        try:
            d = jl.yaml_load(texts[ident])
            idx = jl.CardigannIndexer(d, cfg_overrides.get(ident, {}), data_dir, timeout=20)
            rels = idx.search(query, 'all', None, deadline=time.time() + budget)
            outcome = 'ok' if rels else 'zero'
            detail = len(rels)
        except Exception as e:  # noqa: BLE001
            outcome = classify(e)
            detail = '%s: %s' % (type(e).__name__, str(e)[:160])
        return ident, outcome, detail, round(time.time() - t0, 1)

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, i) for i in targets]
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            print('  %-28s %-12s %s (%.1fs)' % row, flush=True)
    counts = collections.Counter(r[1] for r in rows)
    print('\nlive summary:')
    for k, v in counts.most_common():
        print('  %-12s %d' % (k, v))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--defs', help='folder with Jackett *.yml definitions (default: download them)')
    ap.add_argument('--ref', default='master', help='Jackett git ref used when downloading')
    ap.add_argument('--live', action='store_true', help='also run real searches')
    ap.add_argument('--types', default='public', help='comma list of types for --live')
    ap.add_argument('--query', default='', help='search query for --live (default: empty = latest)')
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--budget', type=float, default=60, help='seconds per indexer for --live')
    ap.add_argument('--doh', help='DNS-over-HTTPS fallback URL for --live')
    ap.add_argument('--json', help='write the full report as JSON to this file')
    args = ap.parse_args()

    if args.defs:
        texts = load_defs(args.defs)
    else:
        data_dir = os.path.join(tempfile.gettempdir(), 'jackettless-coverage')
        store = jl.DefinitionStore(data_dir, args.ref, refresh_days=1)
        store.sync(everything=True)
        texts = load_defs(store.dir)
    static = static_report(texts)
    report = {'static': [{'info': i, 'problems': p, 'warnings': w} for i, p, w in static]}
    if args.live:
        jl.install_dns_fallback(args.doh)
        rows = live_report(texts, {t.strip() for t in args.types.split(',')}, args.query, args.workers,
                           args.budget, {})
        report['live'] = [{'id': r[0], 'outcome': r[1], 'detail': r[2], 'seconds': r[3]} for r in rows]
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=1, default=str)


if __name__ == '__main__':
    main()
