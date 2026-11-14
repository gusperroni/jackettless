# <img src="icon-128.png" alt="" width="40" align="top"> jackettless

**Search hundreds of torrent sites from qBittorrent, using Jackett's indexer definitions, without running a Jackett
server.**

[![Tests](https://github.com/gusperroni/jackettless/actions/workflows/tests.yml/badge.svg)](https://github.com/gusperroni/jackettless/actions/workflows/tests.yml)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: GPL-2.0-or-later](https://img.shields.io/badge/license-GPL--2.0--or--later-green)

> [!IMPORTANT]
> **Disclaimer.** jackettless is a research and educational project about search interoperability. It does not
> host, index, store or distribute any content: it only runs queries on third-party websites chosen by you, and shows
> you their results. The author does not encourage or condone piracy or any copyright infringement. You are solely
> responsible for how you use this software, for complying with the laws of your country, and for respecting the
> terms of service of the websites you query. The software is provided "as is", without warranty of any kind. Use it
> at your own risk.

## What it is

[qBittorrent](https://www.qbittorrent.org/) has a built-in search engine that uses small Python plugins, one per
website. [Jackett](https://github.com/Jackett/Jackett) supports hundreds of websites through a shared library of
**indexer definitions**: YAML files that describe how to search each site. To use Jackett from qBittorrent, you
normally keep the Jackett server running in the background and install the official Jackett plugin, which talks to
that server.

**jackettless reads those same YAML definitions and runs them directly inside the qBittorrent plugin.** There is no
server and no API key. Python runs only while a search is happening.

```
Jackett + official plugin:   qBittorrent → plugin → Jackett server (always running) → websites
jackettless:                 qBittorrent → jackettless plugin → websites
```

## Features

- **One file, no dependencies.** It uses only the Python standard library, as qBittorrent requires.
- **Jackett's indexer library.** Definitions are downloaded from the Jackett repository on demand, cached, and kept
  up to date automatically. You get the fixes that the Jackett community makes to them.
- **Public and private trackers.** Login by form, POST, GET or cookie. The plugin keeps the session and logs in again
  when it expires.
- **Fast, parallel searches.** All your indexers are searched at the same time, and results appear as they arrive.
- **Optional duplicate merging.** The same torrent found on several sites becomes one row, with the trackers of every
  copy in its magnet link.
- **Works around common blocks.** It can fall back to DNS-over-HTTPS when your provider blocks a site by DNS. You can
  also reuse your browser's Cloudflare clearance cookie on some sites.
- **Clear errors.** It can optionally show which indexers failed, and why, as rows in the results list.

## Requirements

- qBittorrent with its search engine enabled. qBittorrent 5.x was tested.
- Python 3.9 or newer, the same Python that qBittorrent's search engine uses.

## Installation

1. Download [`jackettless.py`](https://raw.githubusercontent.com/gusperroni/jackettless/main/jackettless.py).
2. In qBittorrent, open the **Search** tab → **Search plugins…** → **Install a new one** → **Local file**, and select
   `jackettless.py`.
3. Run any search. On the first search, jackettless creates its settings file, `jackettless.json`, next to the plugin.
   The file starts with a few public indexers enabled:

   | System | Folder |
   |---|---|
   | Windows | `%LOCALAPPDATA%\qBittorrent\nova3\engines\` |
   | Linux | `~/.local/share/qBittorrent/nova3/engines/` |
   | macOS | `~/Library/Application Support/qBittorrent/nova3/engines/` |

4. Edit `jackettless.json` to choose your indexers and options, then search again. There is no need to restart
   qBittorrent after editing the settings file.

## Configuration

All settings live in `jackettless.json`. A complete example is in
[`jackettless.example.json`](jackettless.example.json).

```json
{
    "indexers": {
        "thepiratebay": {},
        "nyaasi": {},
        "torrentleech": { "username": "me", "password": "secret" }
    },
    "dedup": "merge",
    "report_errors": "summary"
}
```

Any setting missing from the file uses its default, so you only need to write what you want to change. If the file is
not valid JSON, for example because a comma is missing, jackettless uses the default settings. It then shows a row
like `[jackettless] (search: ubuntu) jackettless.json is invalid (Expecting ',' delimiter: line 26 column 5), default
settings in use`
at the top of the results.

### Choosing indexers

Each key in `indexers` is the **id** of a Jackett indexer. The id is the file name of its definition, without `.yml`,
in [Jackett's Definitions folder](https://github.com/Jackett/Jackett/tree/master/src/Jackett.Common/Definitions).
For example, `thepiratebay.yml` has the id `thepiratebay`.

Each value holds that indexer's settings, and `{}` means the defaults. These settings work for every indexer:

| setting | what it does |
|---|---|
| `enabled` | `false` turns the indexer off without removing its settings. |
| `username`, `password` | Your account on a private tracker. |
| `cookie` | Cookies copied from your browser. Used for trackers that log in with a cookie or that show a captcha, and for Cloudflare clearance. |
| `user_agent` | Replaces the User-Agent sent to this indexer. |
| `sitelink` | Forces a specific domain or mirror of the site. |

An indexer also accepts the options from its definition's `settings` section, the same options Jackett shows on
its configuration screen. Examples are `sort`, `type` and `freeleech`.

### General settings

| setting | default | what it does |
|---|---|---|
| `all_public` | `false` | Also searches **every** public Jackett indexer. The first search then downloads all definitions, which takes a while. |
| `thread_count` | `10` | How many indexers are searched at the same time. |
| `timeout` | `20` | Timeout of each web request, in seconds. |
| `indexer_timeout` | `60` | Maximum time for one indexer during a search, in seconds. |
| `tracker_first` | `true` | Starts each result name with the site, e.g. `[The Pirate Bay] Ubuntu 24.04`. |
| `dedup` | `"off"` | `"merge"` combines duplicate results. See [Merging duplicates](#merging-duplicates). |
| `dedup_wait` | `8` | With `"merge"`: seconds to wait before showing merged results. |
| `report_errors` | `"none"` | Shows failed indexers as result rows: `"none"`, `"summary"` (one row) or `"all"` (one row per failure). |
| `dns_over_https` | `null` | e.g. `"https://1.1.1.1/dns-query"`. See [Blocked by your provider's DNS](#blocked-by-your-providers-dns). |
| `refresh_days` | `1` | How often to check for updated definitions, in days. |
| `definitions_ref` | `"master"` | Jackett branch, tag or commit to download definitions from. |
| `verbose` | `false` | Detailed log output, useful when running from the command line. |

## Private trackers

Add the tracker's id with your credentials:

```json
"torrentleech": { "username": "me", "password": "secret" }
```

jackettless logs in the first time you search and saves the session cookies, and it logs in again when they expire.
Downloads of `.torrent` files from private trackers go through the plugin, so your session is used.

Some trackers show a **captcha** on their login page, or only support logging in with a cookie. For those:

1. Log in with your browser. If the site offers "remember me", tick it.
2. Press F12, open the **Network** tab, and reload the page.
3. Click the first request. In **Request Headers**, copy the whole value of `cookie:`.
4. Paste it as the indexer's `cookie` setting.

> [!WARNING]
> Passwords and cookies are stored in plain text in `jackettless.json` and in the `jackettless_data` folder, just like
> the official Jackett plugin stores its settings. Keep that folder private, and never share these files.

## Merging duplicates

The same torrent often appears on several sites. With `"dedup": "merge"`, results that share the same **infohash**
(the torrent's unique id) become one row:

```
[The Pirate Bay, YTS] Big Buck Bunny (2008) [1080p]
```

- The row's magnet link includes the trackers of every copy.
- Seeds and leechers show the highest value among the copies. They are counts of the same swarm, so they are not
  added up.

qBittorrent cannot change a row after it is shown. So when merging is on, results are held for up to `dedup_wait`
seconds (default 8) and then shown already merged. A copy that arrives later than that is dropped if its torrent is
already on screen.

Some results are never merged:

- Results from private trackers, because their links contain your personal key.
- Results from sites that don't publish the infohash in their listings, such as 1337x and LimeTorrents.

## Sites protected by Cloudflare

Some sites ask every visitor to pass a browser check from Cloudflare first. jackettless cannot solve that check, so
the indexer fails with the reason `Cloudflare`. Jackett handles these sites with FlareSolverr, which is an extra
service.

On some sites, you can reuse the clearance your own browser already obtained:

1. Open the site in your browser and wait until the page loads normally.
2. Press F12, open the **Network** tab, reload the page and click the first request.
3. In **Request Headers**, copy the `cf_clearance=...` part of `cookie:`, and the whole `user-agent:` value.
4. Add both to the indexer:

   ```json
   "1337x": {
       "cookie": "cf_clearance=PASTE_HERE",
       "user_agent": "Mozilla/5.0 ... PASTE THE EXACT VALUE"
   }
   ```

The clearance only works:

- from the same internet connection (IP address), and with exactly the same User-Agent;
- until it expires, after hours or days. When the indexer fails again with `Cloudflare`, repeat the steps.

Some sites also check details of the connection itself that a browser has and Python can't imitate. On those sites
this workaround does not work at all. EZTV is one example at the time of writing.

## Blocked by your provider's DNS

Some internet providers block torrent sites by making their names fail to resolve. The indexer then fails with
`DNS blocked/failed`. Set:

```json
"dns_over_https": "https://1.1.1.1/dns-query"
```

jackettless then asks that DNS-over-HTTPS server for the address, but **only when the normal lookup fails**. The
connection to the site itself is unchanged: HTTPS certificates are still verified against the real site name. Any
DNS-over-HTTPS server with a JSON API works, for example `https://dns.google/resolve`.

## Seeing which indexers failed

By default, a failed indexer is skipped silently. To see failures inside qBittorrent, set `"report_errors"`:

- `"summary"`: one row, e.g. `[jackettless] (search: ubuntu) 2 of 8 indexers failed: 1337x (Cloudflare), eztv (DNS
  blocked/failed)`.
- `"all"`: one row per failed indexer.

These rows are messages, not torrents: opening them does nothing, and **Open description page** leads to
[Troubleshooting](#troubleshooting). They include your search words, because qBittorrent hides rows whose name
doesn't contain them when its "Torrent names only" filter is on (the default).

## Files, network access and privacy

**Files.** jackettless keeps everything next to the plugin, in qBittorrent's `engines` folder:

| path | contents |
|---|---|
| `jackettless.json` | Your settings, including any credentials. |
| `jackettless_data/definitions/` | The cached indexer definitions. |
| `jackettless_data/custom/` | Your own `.yml` definitions, if you write any. A definition here takes priority over Jackett's definition with the same id. |
| `jackettless_data/cookies/` | Login sessions of private trackers. |
| `jackettless_data/state.json` | Which mirror of each site worked last. |

**Network.** Apart from the sites you search, jackettless only contacts:

- **GitHub**, to download and update definitions: at most once a day, and only the files that changed.
- **The DNS-over-HTTPS server you configured**, only if you set one, and only when a normal DNS lookup fails.

Nothing is collected or sent anywhere else.

**Trust.** Definitions are data, not code: a definition can't make jackettless run programs on your computer.
Your cookies are only sent to the indexer's own site, never to other domains. Self-signed certificates are only
accepted when their fingerprint is listed in the indexer's definition, as Jackett does.

## Updating and uninstalling

- **Update the plugin:** install the new `jackettless.py` the same way, and qBittorrent replaces the old one. Your
  `jackettless.json` and `jackettless_data` are kept.
- **Indexer definitions** update by themselves.
- **Uninstall:** remove the plugin in qBittorrent's **Search plugins…** window. Then delete `jackettless.json` and
  `jackettless_data` from the `engines` folder.

## Troubleshooting

| symptom | what to do |
|---|---|
| No results at all | Set `"report_errors": "summary"` and search again to see which indexers fail and why. |
| `Cloudflare` | The site requires a browser check. See [Sites protected by Cloudflare](#sites-protected-by-cloudflare). |
| `DNS blocked/failed` | See [Blocked by your provider's DNS](#blocked-by-your-providers-dns). |
| `timeout` | The site is slow or down. Increase `indexer_timeout`, or try again later. |
| Login errors | Check `username`/`password`. If the site uses a captcha, use `cookie` instead. |
| `definition "x" not available` | The id is wrong, or the indexer was removed from Jackett. Check it against [Jackett's Definitions folder](https://github.com/Jackett/Jackett/tree/master/src/Jackett.Common/Definitions). |
| `jackettless.json is invalid` | The file has a JSON syntax error. The row shows the line and column. |

You can also run a search from a terminal, which prints a detailed log of every request. Run it from the
`nova3/engines` folder:

```bash
python jackettless.py -v search "ubuntu" --indexer thepiratebay
```

## Limitations

- **Only YAML indexers.** About 60 of Jackett's indexers are written in C# instead of YAML, and jackettless can't run
  them. Some of them, such as AudioBookBay and TorrentsCSV, have their own qBittorrent plugins.
- **Cloudflare.** Sites that require a browser check only work with the manual workaround above, and not all of them.
- **Keyword search only.** qBittorrent sends keywords and a category. Searches by IMDb id, season or episode are not
  available.
- **3-minute limit.** qBittorrent stops any search after 3 minutes and keeps the results shown so far. jackettless
  limits each indexer to `indexer_timeout`, 60 seconds by default, so it stays well within that limit.
- **No settings screen.** qBittorrent plugins have no settings UI, so everything is configured in
  `jackettless.json`.
- **A re-implementation.** Jackett's definition engine was ported to Python. Rare definitions may behave differently
  than in Jackett. Please report them.

## Command line

The plugin also works from a terminal, which is useful for testing:

```bash
python jackettless.py search "ubuntu" --cat software --indexer thepiratebay --json
```

```bash
python jackettless.py list --type public
```

```bash
python jackettless.py sync --all
```

```bash
python jackettless.py login torrentleech
```

The commands:

- `search` runs a search.
- `list` shows the cached definitions.
- `sync` downloads or updates definitions.
- `login` tests a private tracker login and saves the session.

Add `--config` and `--data` to use another settings file and data folder.

You can also test the plugin through qBittorrent's own search runner, from the `nova3` folder:

```bash
python nova2.py jackettless all ubuntu
```

## Development

The tests use only the standard library and a local fake tracker, so they don't need internet access:

```bash
python -m unittest discover -s tests
```

`tools/coverage.py` downloads all of Jackett's definitions and checks which features they use that jackettless does
not support. With `--live`, it also runs real searches on every public indexer:

```bash
python tools/coverage.py --live
```

Bug reports and pull requests are welcome. If a definition doesn't work, please include the indexer id and the
output of the command-line search with `-v`.

## Credits

jackettless only exists because of the work of these projects and their communities:

- **[Jackett](https://github.com/Jackett/Jackett)** and its contributors. The Cardigann engine that jackettless
  ports to Python comes from Jackett, and so does the library of indexer definitions. Keeping hundreds of
  definitions working as websites change is a huge, ongoing community effort, and every search jackettless runs is
  built on it. If jackettless is useful to you, please consider supporting Jackett.
- **[Cardigann](https://github.com/cardigann/cardigann)** and its contributors, who created the YAML definition
  format that Jackett adopted.
- **[qBittorrent](https://github.com/qbittorrent/qBittorrent)** and
  **[qbittorrent/search-plugins](https://github.com/qbittorrent/search-plugins)**, for the search engine, the plugin
  API and the official Jackett plugin that inspired this one.
- **[jackettdedup](https://github.com/arihan-1560795/jackettdedup)**, whose idea of merging results by infohash
  inspired the `dedup` option.

jackettless is not affiliated with or endorsed by any of these projects.

## License

jackettless is free software, licensed under the
[GNU General Public License v2.0 or later](LICENSE) (GPL-2.0-or-later).

Because it is a port of Jackett's Cardigann engine, it keeps a license compatible with Jackett's (GPL-2.0). The
indexer definitions are not part of this repository: they are downloaded at runtime from Jackett, under Jackett's
license.
