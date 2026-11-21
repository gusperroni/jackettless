# SPDX-License-Identifier: GPL-2.0-or-later
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jackettless as jl  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


class YamlTests(unittest.TestCase):
    def test_basic_structures(self):
        d = jl.yaml_load(
            '---\n'
            'id: test # comment\n'
            'links:\n'
            '  - https://a.example/\n'
            '  - "https://b.example/"\n'
            'caps:\n'
            '  categorymappings:\n'
            '    - {id: 1, cat: Movies, desc: "Films: HD"}\n'
            '    - {id: 2, cat: TV, desc: Ai Generated"}\n'
            '  modes:\n'
            '    search: [q, season]\n'
            'text: "tab\\there \\u00e9"\n'
            "single: 'it''s'\n"
            'empty:\n'
            'plain: a long\n'
            '  continued line\n'
            'seq:\n'
            '- one\n'
            '- key: v\n'
            '  other: w\n')
        self.assertEqual(d['id'], 'test')
        self.assertEqual(d['links'], ['https://a.example/', 'https://b.example/'])
        cm = d['caps']['categorymappings']
        self.assertEqual(cm[0]['desc'], 'Films: HD')
        self.assertEqual(cm[1]['desc'], 'Ai Generated"')
        self.assertEqual(d['caps']['modes']['search'], ['q', 'season'])
        self.assertEqual(d['text'], 'tab\there \u00e9')
        self.assertEqual(d['single'], "it's")
        self.assertIsNone(d['empty'])
        self.assertEqual(d['plain'], 'a long continued line')
        self.assertEqual(d['seq'], ['one', {'key': 'v', 'other': 'w'}])

    def test_duplicate_keys_are_kept(self):
        d = jl.yaml_load('fields:\n  title:\n    selector: a\n  title:\n    text: b\n')
        self.assertEqual([k for k, _ in d['fields'].pairs], ['title', 'title'])
        self.assertEqual(d['fields']['title'], {'text': 'b'})


class TemplateTests(unittest.TestCase):
    V = {'.Keywords': 'ubuntu linux', '.Config.sort': 'time', '.Config.flag': None, '.False': None,
         '.True': 'True', '.Categories': ['1', '2'], '.Config.x': '1'}

    def t(self, s, mod=None):
        return jl.apply_template(s, dict(self.V), mod)

    def test_if_else_and_logic(self):
        self.assertEqual(self.t('{{ if .Keywords }}k{{ else }}none{{ end }}'), 'k')
        self.assertEqual(self.t('{{ if .Config.flag }}y{{ else }}n{{ end }}'), 'n')
        self.assertEqual(self.t('{{ if and (.Keywords) (eq .Config.flag .False) }}a{{ else }}b{{ end }}'), 'a')
        self.assertEqual(self.t('{{ if or .Config.flag .Keywords }}a{{ else }}b{{ end }}'), 'a')
        self.assertEqual(self.t('{{ if eq .Config.x "1" }}one{{ else }}other{{ end }}'), 'one')
        self.assertEqual(self.t('{{ if ne .Config.x "1" }}one{{ else }}other{{ end }}'), 'other')

    def test_range_join_re_replace(self):
        self.assertEqual(self.t('{{ range .Categories }}&c[]={{.}}{{end}}'), '&c[]=1&c[]=2')
        self.assertEqual(self.t('{{ join .Categories "," }}'), '1,2')
        self.assertEqual(self.t('{{ re_replace .Keywords "\\s+" "%" }}'), 'ubuntu%linux')

    def test_variables_and_modifier(self):
        self.assertEqual(self.t('search/{{ .Keywords }}/{{ .Config.sort }}', jl.net_url_encode),
                         'search/ubuntu+linux/time')
        self.assertEqual(self.t('{{ .Missing }}x'), 'x')


class RegexTests(unittest.TestCase):
    def test_net_compat(self):
        self.assertEqual(jl.net_sub(r'(?<y>\d{4})-(?<m>\d\d)', '${m}/${y}', '2024-05'), '05/2024')
        self.assertEqual(jl.net_sub(r'foo(?i)BAR', '$0!', 'fooBAR'), 'fooBAR!')
        self.assertEqual(jl.net_sub(r'[\p{IsCyrillic}]+', '', 'abcпривет'), 'abc')
        self.assertEqual(jl.net_sub(r'(a)(b)', '$2$1$$', 'ab'), 'ba$')
        self.assertEqual(jl.net_sub(r'T[\s-_]?(\d)', 'S$1', 'T_2'), 'S2')


class SelectorTests(unittest.TestCase):
    HTML = ('<html><body><table id="t"><tr class="head"><th>Name</th></tr>'
            '<tr class="r"><td class="coll-1 name"><a href="/torrent/1/">Ubuntu 24.04</a></td><td>10</td>'
            '<td><img src="x.png"><a href="magnet:?xt=urn:btih:abc">m</a></td></tr>'
            '<tr class="r"><td class="coll-1"><a href="/sub/2/">Other</a></td><td>5</td></tr>'
            '</table><p>one<div>block</div></body></html>')

    def setUp(self):
        self.doc = jl.parse_html(self.HTML)

    def test_tbody_inserted_and_combinators(self):
        rows = jl.select_all(self.doc, 'table#t > tbody > tr.r')
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(jl.select_all(self.doc, 'tr.head + tr')), 1)
        self.assertEqual(len(jl.select_all(self.doc, 'tr.head ~ tr')), 2)

    def test_pseudo_classes(self):
        sel = jl.select_all(self.doc, 'tr:has(a[href^="/torrent/"])')
        self.assertEqual(len(sel), 1)
        self.assertEqual(len(jl.select_all(self.doc, 'tr:has(> td > a[href*="sub"])')), 1)
        self.assertEqual(jl.select_one(self.doc, 'td:contains("Other")').text_content(), 'Other')
        self.assertEqual(len(jl.select_all(self.doc, 'tr.r:not(:has(a[href^="magnet:"]))')), 1)
        self.assertEqual(jl.select_one(self.doc, 'tr.r td:nth-child(2)').text_content(), '10')
        self.assertEqual(jl.select_one(self.doc, 'tr.r td:nth-last-child(1) a').get('href'),
                         'magnet:?xt=urn:btih:abc')
        self.assertEqual(len(jl.select_all(self.doc, 'tr:nth-child(odd)')), 2)
        self.assertEqual(jl.select_one(self.doc, 'td[class~="name"] a').text_content(), 'Ubuntu 24.04')
        self.assertTrue(jl.matches(jl.select_one(self.doc, 'tr.r'), 'tr:first-of-type + tr'))

    def test_root_and_scope(self):
        row = jl.select_one(self.doc, 'tr.r')
        self.assertIsNotNone(jl.select_one(row, ':root table#t'))
        self.assertEqual(jl.select_one(row, '> td').text_content(), 'Ubuntu 24.04')

    def test_paragraph_closed_by_block(self):
        p = jl.select_one(self.doc, 'p')
        self.assertEqual(p.text_content(), 'one')

    def test_xml_namespaced_tags_match_local_name(self):
        doc = jl.parse_xml('<?xml version="1.0"?><rss xmlns:tv="x"><channel><item><title>A</title>'
                           '<tv:raw_title>A raw</tv:raw_title><enclosure url="u"/></item></channel></rss>')
        item = jl.select_one(doc, 'rss > channel > item')
        self.assertEqual(jl.select_one(item, 'raw_title').text_content(), 'A raw')
        self.assertEqual(jl.select_one(item, 'enclosure').get('url'), 'u')


class DateTests(unittest.TestCase):
    NOW = datetime(2026, 11, 12, 15, 0, 0)

    def test_go_and_net_layouts(self):
        self.assertEqual(jl.parse_date_golang('2023-01-15 10:30:00', '2006-01-02 15:04:05'),
                         datetime(2023, 1, 15, 10, 30))
        self.assertEqual(jl.parse_date_golang('15.01.2023', '02.01.2006'), datetime(2023, 1, 15))
        self.assertEqual(jl.parse_date_golang('Apr. 18 11', 'MMM. d yy'), datetime(2011, 4, 18))
        self.assertEqual(jl.parse_date_golang('7am Sep. 14', 'htt MMM. d', self.NOW), datetime(2026, 9, 14, 7))
        # Go layout without a year: a date in the future goes back one year
        self.assertEqual(jl.parse_date_golang('Dec 24', 'Jan 02', self.NOW), datetime(2025, 12, 24))

    def test_relative_and_fuzzy(self):
        self.assertEqual(jl.from_unknown('2 hours ago', self.NOW), self.NOW - timedelta(hours=2))
        self.assertEqual(jl.from_unknown('Yesterday 10:30', self.NOW), datetime(2026, 11, 11, 10, 30))
        self.assertEqual(jl.from_unknown('Jan 5, 2023 3:04 PM', self.NOW), datetime(2023, 1, 5, 15, 4))
        self.assertEqual(jl.from_unknown('05/01/2023', self.NOW), datetime(2023, 5, 1))
        rfc = jl.fmt_rfc(datetime(2024, 5, 6, 7, 8, 9))
        self.assertEqual(jl.from_unknown(rfc), datetime(2024, 5, 6, 7, 8, 9))


class FilterTests(unittest.TestCase):
    def f(self, data, *filters):
        return jl.apply_filters(data, list(filters), {'.Config.x': 'X'})

    def test_filters(self):
        self.assertEqual(self.f('/a?id=5&x=1', {'name': 'querystring', 'args': 'id'}), '5')
        self.assertEqual(self.f('a-b-c', {'name': 'split', 'args': ['-', '-1']}), 'c')
        self.assertEqual(self.f('abc', {'name': 'replace', 'args': ['b', '{{ .Config.x }}']}), 'aXc')
        self.assertEqual(self.f('Size: 1.5 GB', {'name': 'regexp', 'args': r'Size: (.+)'}), '1.5 GB')
        self.assertEqual(self.f('  x  ', {'name': 'trim'}), 'x')
        self.assertEqual(self.f('a+b%20c', {'name': 'urldecode'}), 'a b c')
        self.assertEqual(self.f('Ação', {'name': 'diacritics', 'args': 'replace'}), 'Acao')
        self.assertEqual(self.f('1080p, x264, HDR', {'name': 'validate', 'args': '720p, 1080p, hdr'}),
                         '1080p,hdr')
        self.assertEqual(self.f('{"a": {"b": [1, 2]}}', {'name': 'jsonjoinarray', 'args': ['a.b', ', ']}),
                         '1, 2')

    def test_numbers(self):
        self.assertEqual(jl.get_bytes('1.5 GB'), 1610612736)
        self.assertEqual(jl.get_bytes('296,98 MB'), 311406100)
        self.assertEqual(jl.get_bytes('1.018,29 MB'), 1067754455)
        self.assertEqual(jl.coerce_long('1,234'), 1234)
        self.assertEqual(jl.coerce_long('-'), 0)


# ---------------------------------------------------------------------------
# end to end: a fake private tracker served on localhost
# ---------------------------------------------------------------------------

TORRENT = b'd8:announce9:http://x/4:infod4:name4:testee'

DEFINITION = '''---
id: faketracker
name: Fake Tracker
type: private
encoding: UTF-8
links:
  - http://127.0.0.1:{port}/
caps:
  categorymappings:
    - {{id: 1, cat: Movies, desc: "Movies"}}
    - {{id: 2, cat: TV, desc: "TV"}}
settings:
  - name: username
    type: text
  - name: password
    type: password
login:
  path: login.php
  method: form
  form: form#login
  inputs:
    username: "{{{{ .Config.username }}}}"
    password: "{{{{ .Config.password }}}}"
  error:
    - selector: div.error
  test:
    path: index.php
    selector: a[href="logout.php"]
search:
  paths:
    - path: browse.php
  inputs:
    search: "{{{{ .Keywords }}}}"
    $raw: "{{{{ range .Categories }}}}c{{{{.}}}}=1&{{{{end}}}}"
  rows:
    selector: table.torrents > tbody > tr:has(a.dl)
  fields:
    category:
      selector: td.cat a
      attribute: href
      filters:
        - name: querystring
          args: cat
    title:
      selector: td.name a
    details:
      selector: td.name a
      attribute: href
    download:
      selector: a.dl
      attribute: href
    size:
      selector: td.size
    seeders:
      selector: td.seed
    leechers:
      selector: td.leech
    date:
      selector: td.date
      filters:
        - name: dateparse
          args: "2006-01-02 15:04"
'''

PAGE_ROWS = '''<html><body><a href="logout.php">logout</a><table class="torrents">
<tr><th>head</th></tr>
<tr><td class="cat"><a href="browse.php?cat=1">Movies</a></td><td class="name"><a href="details.php?id=1">Ubuntu Movie 2024</a></td>
<td class="size">1.5 GB</td><td class="seed">12</td><td class="leech">3</td><td class="date">2024-03-01 10:00</td>
<td><a class="dl" href="download.php?id=1">dl</a></td></tr>
<tr><td class="cat"><a href="browse.php?cat=2">TV</a></td><td class="name"><a href="details.php?id=2">Ubuntu Show S01</a></td>
<td class="size">700 MB</td><td class="seed">1,200</td><td class="leech">0</td><td class="date">2024-03-02 11:00</td>
<td><a class="dl" href="download.php?id=2">dl</a></td></tr>
</table></body></html>'''


class FakeTracker(http.server.BaseHTTPRequestHandler):
    logins = 0
    last_query = None
    last_headers = {}

    def log_message(self, *args):
        pass

    def _logged(self):
        return 'session=ok' in (self.headers.get('Cookie') or '')

    def _send(self, code, body=b'', ctype='text/html; charset=utf-8', headers=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        u = urllib.parse.urlsplit(self.path)
        FakeTracker.last_headers = dict(self.headers)
        if u.path == '/public.php':
            self._send(200, PAGE_ROWS.encode('utf-8'))
            return
        if u.path == '/magnets.php':
            one = 'site=pubone' in u.query
            page = MAGNET_ROWS.format(seeds=5 if one else 50, a=HASH_A, b=('c' if one else 'd') * 40,
                                      tr='one' if one else 'two')
            self._send(200, page.encode('utf-8'))
            return
        if u.path == '/login.php':
            self._send(200, b'<form id="login" action="takelogin.php" method="post">'
                            b'<input type="hidden" name="token" value="t0k">'
                            b'<input name="username"><input name="password" type="password">'
                            b'<input type="checkbox" name="remember"></form>',
                       headers={'Set-Cookie': 'pre=1; Path=/'})
        elif u.path == '/index.php':
            self._send(200, b'<a href="logout.php">logout</a>' if self._logged() else b'<a href="login.php">in</a>')
        elif u.path == '/browse.php':
            if not self._logged():
                self._send(302, headers={'Location': '/login.php'})
                return
            FakeTracker.last_query = u.query
            self._send(200, PAGE_ROWS.encode('utf-8'))
        elif u.path == '/download.php':
            if not self._logged():
                self._send(302, headers={'Location': '/login.php'})
                return
            self._send(200, TORRENT, 'application/x-bittorrent')
        else:
            self._send(404, b'not found')

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get('Content-Length') or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        if self.path == '/takelogin.php':
            ok = (form.get('username') == ['user'] and form.get('password') == ['pa ss&']
                  and form.get('token') == ['t0k'] and 'pre=1' in (self.headers.get('Cookie') or ''))
            if ok:
                FakeTracker.logins += 1
                self._send(302, headers={'Location': '/index.php', 'Set-Cookie': 'session=ok; Path=/'})
            else:
                self._send(200, b'<div class="error">Bad password</div>')
        else:
            self._send(404)


class FakeTrackerCase(unittest.TestCase):
    """Starts the fake tracker and prepares a temporary data folder with its definition."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeTracker)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, 'custom'))
        with open(os.path.join(self.tmp, 'custom', 'faketracker.yml'), 'w', encoding='utf-8') as f:
            f.write(DEFINITION.format(port=self.port))
        # mark the cache as fresh so the store does not call GitHub
        with open(os.path.join(self.tmp, 'definitions_index.json'), 'w') as f:
            json.dump({'ref': 'master', 'updated': time.time(), 'files': {}}, f)
        FakeTracker.logins = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cfg(self, password='pa ss&'):
        return {'indexers': {'faketracker': {'username': 'user', 'password': password}}, 'thread_count': 2,
                'timeout': 5, 'indexer_timeout': 20, 'tracker_first': True, 'definitions_ref': 'master',
                'refresh_days': 7, 'all_public': False, 'backoff': False}


class EndToEndTests(FakeTrackerCase):
    def test_login_search_and_download(self):
        results = []
        summary = jl.run_search('ubuntu', 'all', results.append, self.cfg(), self.tmp)
        self.assertEqual(summary, {'faketracker': 2})
        self.assertEqual(FakeTracker.logins, 1)
        first = results[0]
        self.assertEqual(first['name'], '[Fake Tracker] Ubuntu Movie 2024')
        self.assertEqual(first['size'], 1610612736)
        self.assertEqual(first['seeds'], 12)
        self.assertEqual(first['leech'], 3)
        self.assertEqual(results[1]['seeds'], 1200)
        self.assertTrue(first['link'].endswith('/download.php?id=1#jackettless=faketracker'))
        self.assertEqual(first['desc_link'], 'http://127.0.0.1:%d/details.php?id=1' % self.port)
        self.assertEqual(datetime.fromtimestamp(first['pub_date']), datetime(2024, 3, 1, 10, 0))
        self.assertIn('search=ubuntu', FakeTracker.last_query)

        # cookies were saved: a second search does not log in again
        results2 = []
        jl.run_search('ubuntu', 'movies', results2.append, self.cfg(), self.tmp)
        self.assertEqual(FakeTracker.logins, 1)
        self.assertEqual([r['name'] for r in results2], ['[Fake Tracker] Ubuntu Movie 2024'])
        self.assertIn('c1=1', FakeTracker.last_query)

        line = jl.run_download(first['link'], self.cfg(), self.tmp)
        path, url = line.split(' ', 1)
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), TORRENT)
        os.remove(path)
        self.assertEqual(url, first['link'])

    def test_bad_password_reports_site_error(self):
        summary = jl.run_search('ubuntu', 'all', lambda r: None, self.cfg('wrong'), self.tmp)
        self.assertIn('Bad password', summary['faketracker'])

    def test_expired_cookie_triggers_relogin(self):
        os.makedirs(os.path.join(self.tmp, 'cookies'))
        with open(os.path.join(self.tmp, 'cookies', 'faketracker.json'), 'w') as f:
            json.dump({'site': 'http://127.0.0.1:%d/' % self.port, 'cookies': {'session': 'expired'}}, f)
        results = []
        summary = jl.run_search('ubuntu', 'all', results.append, self.cfg(), self.tmp)
        self.assertEqual(summary, {'faketracker': 2})
        self.assertEqual(FakeTracker.logins, 1)


PUBLIC_DEFINITION = '''---
id: fakepublic
name: Fake Public
type: public
links:
  - http://127.0.0.1:{port}/
caps:
  categorymappings:
    - {{id: 1, cat: Movies}}
search:
  paths:
    - path: public.php
  rows:
    selector: table.torrents > tbody > tr:has(a.dl)
  fields:
    title:
      selector: td.name a
    download:
      selector: a.dl
      attribute: href
'''


HASH_A = 'a' * 40
HASH_B = 'B' * 40
MAGNET_ROWS = '''<html><body><table class="torrents">
<tr><td class="name"><a href="details.php?id=1">Same Release</a></td><td class="seed">{seeds}</td>
<td><a class="dl" href="magnet:?xt=urn:btih:{a}&amp;dn=x&amp;tr=udp%3A%2F%2F{tr}%3A1337">m</a></td></tr>
<tr><td class="name"><a href="details.php?id=2">Only Here</a></td><td class="seed">1</td>
<td><a class="dl" href="magnet:?xt=urn:btih:{b}&amp;dn=y">m</a></td></tr>
</table></body></html>'''

MAGNET_DEFINITION = '''---
id: {ident}
name: {name}
type: public
links:
  - http://127.0.0.1:{port}/
search:
  paths:
    - path: magnets.php?site={ident}
  rows:
    selector: table.torrents > tbody > tr
  fields:
    title:
      selector: td.name a
    download:
      selector: a.dl
      attribute: href
    seeders:
      selector: td.seed
'''


class _Idx:
    def __init__(self, ident, name, typ='public'):
        self.id, self.name, self.type = ident, name, typ


def _rel(title, seeds, magnet=None, link=None, infohash=None):
    r = jl.Release()
    r.title, r.seeders, r.magnet, r.link, r.infohash = title, seeds, magnet, link, infohash
    return r


class InfohashTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(jl.normalize_infohash('urn:btih:' + 'AB' * 20), 'ab' * 20)
        b32 = __import__('base64').b32encode(bytes.fromhex('ab' * 20)).decode()
        self.assertEqual(jl.normalize_infohash(b32), 'ab' * 20)
        self.assertEqual(jl.normalize_infohash('urn:btmh:1220' + 'CD' * 32), 'v2:' + 'cd' * 32)
        self.assertIsNone(jl.normalize_infohash('abc'))

    def test_sources(self):
        self.assertEqual(jl.release_infohash(_rel('t', 1, infohash='AB' * 20)), 'ab' * 20)
        self.assertEqual(jl.release_infohash(_rel('t', 1, magnet='magnet:?xt=urn:btih:%s&dn=t' % ('CD' * 20))),
                         'cd' * 20)
        self.assertEqual(jl.release_infohash(_rel('t', 1, link='https://h/%s/name' % ('EF' * 20))), 'ef' * 20)
        self.assertIsNone(jl.release_infohash(_rel('t', 1, link='https://h/%s/name' % ('EF' * 21))))
        self.assertIsNone(jl.release_infohash(_rel('t', 1, link='https://h/torrent/123/name')))


class MergerTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.m = jl.ResultMerger(self.rows.append)
        self.mag = lambda h, tr: 'magnet:?xt=urn:btih:%s&dn=x&tr=udp%%3A%%2F%%2F%s%%3A1' % (h, tr)

    def test_same_hash_from_public_sites_is_merged(self):
        self.m.add(_Idx('a', 'Site A'), _rel('Low', 5, self.mag(HASH_A, 'ta')))
        self.m.add(_Idx('b', 'Site B'), _rel('High', 50, self.mag(HASH_A.upper(), 'tb')))
        self.m.add(_Idx('c', 'Site C'), _rel('Other', 1, self.mag(HASH_A, 'tc')))
        self.assertEqual(self.rows, [])
        self.m.go_live()
        self.assertEqual(len(self.rows), 1)
        row = self.rows[0]
        self.assertEqual(row['name'], '[Site B, Site A +1] High')
        self.assertEqual(row['seeds'], 50)
        for tr in ('tb', 'ta', 'tc'):
            self.assertIn('udp%%3A%%2F%%2F%s%%3A1' % tr, row['link'])
        self.assertTrue(row['link'].startswith('magnet:?xt=urn:btih:' + HASH_A.upper()))

    def test_private_and_hashless_pass_through(self):
        self.m.add(_Idx('p', 'Private', 'private'), _rel('Priv', 3, self.mag(HASH_A, 'tp'), 'http://p/dl'))
        self.m.add(_Idx('a', 'Site A'), _rel('No hash', 1, link='http://a/torrent/1'))
        self.assertEqual(len(self.rows), 2)
        self.m.add(_Idx('a', 'Site A'), _rel('Pub', 3, self.mag(HASH_A, 'ta')))
        self.m.go_live()
        self.assertEqual(len(self.rows), 3)

    def test_live_mode(self):
        self.m.add(_Idx('a', 'Site A'), _rel('First', 3, self.mag(HASH_A, 'ta')))
        self.m.go_live()
        self.m.add(_Idx('b', 'Site B'), _rel('Late copy', 9, self.mag(HASH_A, 'tb')))
        self.m.add(_Idx('b', 'Site B'), _rel('New hash', 9, self.mag(HASH_B, 'tb')))
        self.assertEqual([r['name'] for r in self.rows], ['[Site A] First', '[Site B] New hash'])
        self.assertEqual(self.m.dropped, 1)


class AllPublicTests(FakeTrackerCase):
    """all_public by default: the indexer list fills itself, old defaults migrate, failing indexers pause."""

    def setUp(self):
        super().setUp()
        for ident, name in (('pubone', 'Pub One'), ('pubtwo', 'Pub Two')):
            with open(os.path.join(self.tmp, 'custom', ident + '.yml'), 'w', encoding='utf-8') as f:
                f.write(MAGNET_DEFINITION.format(ident=ident, name=name, port=self.port))
        # a non-empty, fresh index: the store must not go to GitHub during tests
        with open(os.path.join(self.tmp, 'definitions_index.json'), 'w') as f:
            json.dump({'ref': 'master', 'updated': time.time(), 'files': {'pubone': '-'}}, f)
        self.path = os.path.join(self.tmp, 'jackettless.json')

    def write(self, data):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def read(self):
        with open(self.path, encoding='utf-8') as f:
            return json.load(f)

    def test_public_indexers_are_added_and_user_choices_kept(self):
        self.write({'indexers': {'pubone': {'enabled': False}}, 'all_public': True, 'timeout': 5,
                    'backoff': False, 'dedup': 'off'})
        cfg = jl.load_config(self.path)
        rows = []
        summary = jl.run_search('x', 'all', rows.append, cfg, self.tmp)
        written = self.read()
        self.assertEqual(written['indexers'], {'pubone': {'enabled': False}, 'pubtwo': {'enabled': True}})
        self.assertNotIn('faketracker', written['indexers'])  # private: never added automatically
        # the rest of the file is untouched: same keys, same values, no defaults merged in
        self.assertEqual(set(written), {'indexers', 'all_public', 'timeout', 'backoff', 'dedup'})
        self.assertEqual(written['timeout'], 5)
        self.assertEqual(list(summary), ['pubtwo'])  # the disabled one is not searched

    def test_invalid_file_is_never_rewritten(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('{"all_public": true,,}')
        cfg = jl.load_config(self.path)
        cfg['backoff'] = False
        jl.run_search('x', 'all', lambda r: None, cfg, self.tmp)
        with open(self.path, encoding='utf-8') as f:
            self.assertEqual(f.read(), '{"all_public": true,,}')

    def test_untouched_old_default_is_migrated(self):
        self.write(jl._OLD_DEFAULTS[0])  # noqa: SLF001
        cfg = jl.load_config(self.path)
        self.assertIs(cfg['all_public'], True)
        self.assertEqual(self.read(), jl.DEFAULT_CONFIG)

    def test_edited_old_config_is_kept(self):
        edited = json.loads(json.dumps(jl._OLD_DEFAULTS[0]))  # noqa: SLF001
        edited['dns_over_https'] = 'https://1.1.1.1/dns-query'
        self.write(edited)
        cfg = jl.load_config(self.path)
        self.assertIs(cfg['all_public'], False)
        self.assertEqual(self.read(), edited)

    def test_backoff_grows_and_resets(self):
        now = 1000000.0
        self.assertEqual(jl.record_health(self.tmp, {'a': 'timeout'}, now), [])
        self.assertEqual(jl.paused_indexers(self.tmp, ['a'], now), [])
        self.assertEqual(jl.record_health(self.tmp, {'a': 'timeout'}, now), ['a'])
        self.assertEqual(jl.paused_indexers(self.tmp, ['a', 'b'], now + 3599), ['a'])
        self.assertEqual(jl.paused_indexers(self.tmp, ['a'], now + 3601), [])
        jl.record_health(self.tmp, {'a': 'Cloudflare'}, now)
        self.assertEqual(jl.paused_indexers(self.tmp, ['a'], now + 6 * 3600 - 1), ['a'])
        for _ in range(5):
            jl.record_health(self.tmp, {'a': 'Cloudflare'}, now)
        self.assertEqual(jl.paused_indexers(self.tmp, ['a'], now + 24 * 3600 + 1), [])  # never more than 24 h
        jl.record_health(self.tmp, {'a': None}, now)
        self.assertEqual(jl.paused_indexers(self.tmp, ['a'], now), [])

    def test_failures_far_apart_do_not_pause(self):
        now = 1000000.0
        jl.record_health(self.tmp, {'a': 'timeout'}, now)
        self.assertEqual(jl.record_health(self.tmp, {'a': 'timeout'}, now + 3 * 24 * 3600), [])

    def test_damaged_health_entry_is_ignored(self):
        with open(os.path.join(self.tmp, 'state.json'), 'w') as f:
            json.dump({'health': {'a': {'until': 'soon'}, 'b': {'until': 9e12}}}, f)
        self.assertEqual(jl.paused_indexers(self.tmp, ['a', 'b']), ['b'])

    def test_no_enabled_indexer_shows_a_row(self):
        self.write({'indexers': {'pubone': {'enabled': False}}, 'all_public': False})
        rows = []
        jl.run_search('x', 'all', rows.append, jl.load_config(self.path), self.tmp)
        self.assertEqual([r['name'] for r in rows], ['[jackettless] (search: x) no indexers enabled: check '
                                                     '"indexers" and "all_public" in jackettless.json'])

    def test_indexers_removed_from_jackett_are_skipped(self):
        self.write({'indexers': {'gone': {'enabled': True}, 'pubtwo': {'enabled': True}}, 'all_public': False,
                    'backoff': False, 'dedup': 'off'})
        summary = jl.run_search('x', 'all', lambda r: None, jl.load_config(self.path), self.tmp)
        self.assertEqual(list(summary), ['pubtwo'])  # 'gone' is not upstream and has no custom file

    def test_paused_indexer_is_skipped_but_explicit_search_still_runs(self):
        cfg = self.cfg('wrong')
        cfg['backoff'] = True
        cfg['report_errors'] = 'summary'
        for _ in range(2):
            jl.run_search('ubuntu', 'all', lambda r: None, cfg, self.tmp)
        rows = []
        summary = jl.run_search('ubuntu', 'all', rows.append, cfg, self.tmp)
        self.assertEqual(summary, {})
        self.assertEqual([r['name'] for r in rows],
                         ['[jackettless] (search: ubuntu) 1 paused after repeated failures'])
        explicit = jl.run_search('ubuntu', 'all', lambda r: None, cfg, self.tmp, only=['faketracker'])
        self.assertIn('Bad password', explicit['faketracker'])


class OptionTests(FakeTrackerCase):
    def test_new_install_config_defaults(self):
        path = os.path.join(self.tmp, 'new.json')
        jl.load_config(path)
        with open(path, encoding='utf-8') as f:
            written = json.load(f)
        self.assertEqual(written['indexers'], {})
        self.assertIs(written['all_public'], True)
        self.assertEqual(written['report_errors'], 'summary')
        self.assertEqual(written['dedup'], 'merge')
        self.assertIs(written['backoff'], True)

    def test_invalid_config_shows_warning_row(self):
        path = os.path.join(self.tmp, 'broken.json')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{"dedup": "merge"\n "report_errors": "none"}')
        cfg = jl.load_config(path)
        self.assertIn("Expecting ','", cfg['_error'])
        self.assertNotIn('char', cfg['_error'])
        cfg['indexers'] = {}
        cfg['all_public'] = False  # no real searches in tests
        rows = []
        jl.run_search('x', 'all', rows.append, cfg, self.tmp, only=None)
        self.assertEqual(len(rows), 2)  # invalid file, then "no indexers enabled" (the list is empty here)
        self.assertIn('no indexers enabled', rows[1]['name'])
        self.assertTrue(rows[0]['name'].startswith('[jackettless] (search: x) jackettless.json is invalid (Expecting'))
        self.assertEqual(rows[0]['desc_link'], jl.HELP_URL)
        self.assertTrue(rows[0]['link'].endswith(jl.ERROR_MARK))

    def test_mirror_fallback_is_remembered(self):
        import socket
        with socket.socket() as s:  # a port with nothing listening
            s.bind(('127.0.0.1', 0))
            dead = s.getsockname()[1]
        text = PUBLIC_DEFINITION.format(port=self.port).replace(
            '  - http://127.0.0.1:%d/\n' % self.port,
            '  - http://127.0.0.1:%d\n  - http://127.0.0.1:%d\n' % (dead, self.port))  # no trailing slashes
        idx = jl.CardigannIndexer(jl.yaml_load(text), {}, self.tmp, 5)
        self.assertEqual(len(idx.search('ubuntu')), 2)
        again = jl.CardigannIndexer(jl.yaml_load(text), {}, self.tmp, 5)
        self.assertEqual(again.site_link, 'http://127.0.0.1:%d/' % self.port)

    def test_cookies_only_go_to_the_indexer_hosts(self):
        url = 'http://127.0.0.1:%d/public.php' % self.port
        other = jl.HttpSession(cookies={'session': 'secret'}, cookie_domains={'tracker.example'})
        other.request(url)
        self.assertNotIn('Cookie', FakeTracker.last_headers)
        same = jl.HttpSession(cookies={'session': 'secret'}, cookie_domains={'127.0.0.1'})
        same.request(url)
        self.assertEqual(FakeTracker.last_headers.get('Cookie'), 'session=secret')

    def test_only_http_urls_are_opened(self):
        with self.assertRaises(jl.IndexerError):
            jl.HttpSession().request('file:///etc/passwd')

    def test_result_links_cannot_inject_rows(self):
        idx = _Idx('x', 'X', 'private')
        rel = _rel('t', 1, link='http://h/dl\n#evil|row', )
        rel.details = 'http://h/d\r\nmagnet:?xt=urn:btih:%s' % HASH_A
        res = jl.release_to_result(idx, rel)
        for value in (res['link'], res['desc_link']):
            self.assertNotRegex(value, r'[\r\n|\x00-\x1f ]')

    def capture_stderr(self, fn):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            fn()
        return [line for line in buf.getvalue().splitlines() if line.strip()]

    def test_successful_search_and_first_run_are_silent(self):
        # qBittorrent logs every stderr line as "Error occurred in search engine"
        lines = self.capture_stderr(lambda: (
            jl.load_config(os.path.join(self.tmp, 'fresh.json')),
            jl.run_search('ubuntu', 'all', lambda r: None, self.cfg(), self.tmp)))
        self.assertEqual(lines, [])

    def test_failures_are_one_stderr_line(self):
        lines = self.capture_stderr(lambda: jl.run_search('ubuntu', 'all', lambda r: None, self.cfg('wrong'), self.tmp))
        self.assertEqual(lines, ['[jackettless] 1 of 1 indexers failed: faketracker (Error: Bad password)'])

    def test_invalid_indexer_id_is_rejected(self):
        for bad in ('../evil', '..\\evil', 'a/b', '', '.hidden'):
            with self.assertRaises(jl.IndexerError):
                jl.check_indexer_id(bad)
        cfg = self.cfg()
        cfg['indexers'] = {'../../outside': {}}
        summary = jl.run_search('x', 'all', lambda r: None, cfg, self.tmp)
        self.assertIn('invalid indexer id', summary['../../outside'])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, '..', 'outside.yml')))

    def test_dedup_merge_in_run_search(self):
        for ident, name, tr in (('pubone', 'Pub One', 'one'), ('pubtwo', 'Pub Two', 'two')):
            with open(os.path.join(self.tmp, 'custom', ident + '.yml'), 'w', encoding='utf-8') as f:
                f.write(MAGNET_DEFINITION.format(ident=ident, name=name, port=self.port))
        cfg = self.cfg()
        cfg['indexers'] = {'pubone': {}, 'pubtwo': {}}
        for mode, expected in (('off', 4), ('merge', 3)):
            cfg['dedup'] = mode
            rows = []
            jl.run_search('x', 'all', rows.append, cfg, self.tmp)
            self.assertEqual(len(rows), expected, mode)
        merged = [r for r in rows if r['name'].startswith('[Pub')]
        self.assertTrue(any(', ' in r['name'].split(']')[0] for r in merged))


class ErrorReportAndOptionTests(FakeTrackerCase):
    """report_errors, manual cookie/user_agent and the definitions refresh backoff."""

    def run_with(self, mode, password='wrong'):
        cfg = self.cfg(password)
        cfg['report_errors'] = mode
        rows = []
        jl.run_search('ubuntu', 'all', rows.append, cfg, self.tmp)
        return [r for r in rows if r['name'].startswith('[jackettless]')]

    def test_report_errors_modes(self):
        self.assertEqual(self.run_with('none'), [])
        summary = self.run_with('summary')
        self.assertEqual(len(summary), 1)
        self.assertIn('1 of 1 indexers failed: faketracker (Error: Bad password)', summary[0]['name'])
        self.assertTrue(summary[0]['link'].endswith(jl.ERROR_MARK))
        self.assertEqual(self.run_with('all')[0]['name'],
                         '[jackettless] (search: ubuntu) faketracker failed: Error: Bad password')
        self.assertEqual(self.run_with('summary', password='pa ss&'), [])  # no failure, no row
        with self.assertRaises(jl.IndexerError):
            jl.run_download(summary[0]['link'], self.cfg(), self.tmp)

    def test_describe_error(self):
        self.assertEqual(jl.describe_error(jl.CloudflareError('x')), 'Cloudflare')
        self.assertEqual(jl.describe_error(jl.NetworkError('h: [Errno 11001] getaddrinfo failed')),
                         'DNS blocked/failed')
        self.assertEqual(jl.describe_error(jl.DeadlineExceeded('x')), 'timeout')

    def test_manual_cookie_and_user_agent(self):
        d = jl.yaml_load(PUBLIC_DEFINITION.format(port=self.port))
        idx = jl.CardigannIndexer(d, {'cookie': 'cf_clearance=abc; other=1', 'user_agent': 'UA/1'}, self.tmp, 5)
        rels = idx.search('ubuntu')
        self.assertEqual(len(rels), 2)
        self.assertIn('cf_clearance=abc', FakeTracker.last_headers.get('Cookie', ''))
        self.assertEqual(FakeTracker.last_headers.get('User-Agent'), 'UA/1')

    def test_manual_cookie_survives_relogin(self):
        d = jl.yaml_load(DEFINITION.format(port=self.port))
        idx = jl.CardigannIndexer(d, {'username': 'user', 'password': 'pa ss&', 'cookie': 'cf_clearance=abc'},
                                  self.tmp, 5)
        idx.relogin()
        self.assertEqual(FakeTracker.logins, 1)
        self.assertEqual(len(idx.search('ubuntu')), 2)
        cookie = FakeTracker.last_headers.get('Cookie', '')
        self.assertIn('cf_clearance=abc', cookie)
        self.assertIn('session=ok', cookie)

    def test_refresh_backoff_after_failure(self):
        store = jl.DefinitionStore(os.path.join(self.tmp, 'fresh'), 'master', refresh_days=1)
        calls = []

        def failing():
            calls.append(1)
            raise OSError('rate limited')

        store.remote_listing = failing
        store._download = lambda ident: None  # noqa: SLF001
        store.ensure(['x'])
        store.ensure(['x'])
        self.assertEqual(len(calls), 1)
        self.assertFalse(store.is_stale())


class PluginInterfaceTests(unittest.TestCase):
    def test_class_attributes(self):
        engine = jl.jackettless()
        self.assertTrue(engine.url.startswith('https://'))
        self.assertIn('all', engine.supported_categories)
        self.assertTrue(callable(engine.search) and callable(engine.download_torrent))

    def test_link_preference(self):
        rel = jl.Release()
        rel.title, rel.link, rel.magnet = 't', 'http://h/dl/1', 'magnet:?xt=urn:btih:abc'
        public = type('I', (), {'id': 'p', 'name': 'P', 'type': 'public'})()
        private = type('I', (), {'id': 'q', 'name': 'Q', 'type': 'private'})()
        self.assertEqual(jl.release_to_result(public, rel)['link'], 'magnet:?xt=urn:btih:abc')
        self.assertEqual(jl.release_to_result(private, rel)['link'], 'http://h/dl/1#jackettless=q')

    def test_result_never_contains_pipe(self):
        idx = type('I', (), {'id': 'x', 'name': 'X', 'type': 'private'})()
        rel = jl.Release()
        rel.title, rel.link, rel.details = 'a | b', 'http://h/d?a|b', 'http://h/x|y'
        res = jl.release_to_result(idx, rel)
        self.assertNotIn('|', res['link'] + res['desc_link'])


if __name__ == '__main__':
    unittest.main()
