# <img src="icon-128.png" alt="" width="40" align="top"> jackettless

**Search every public site supported by Jackett, straight from qBittorrent, without running a Jackett server.**

[![Tests](https://github.com/gusperroni/jackettless/actions/workflows/tests.yml/badge.svg)](https://github.com/gusperroni/jackettless/actions/workflows/tests.yml)
[![Latest release](https://img.shields.io/github/v/release/gusperroni/jackettless)](https://github.com/gusperroni/jackettless/releases/latest)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: GPL-2.0-or-later](https://img.shields.io/badge/license-GPL--2.0--or--later-green)

> [!IMPORTANT]
> **Disclaimer.** jackettless is a research and educational project about search interoperability. It does not
> host, index, store or distribute any content. It only sends your searches to third-party websites and shows their
> results. The author does not encourage or condone piracy or any copyright infringement. You are solely responsible
> for how you use this software, for following the laws of your country, and for respecting the terms of service of
> the websites you search. The software is provided "as is", without warranty of any kind. Use it at your own risk.

## Contents

- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Settings](#settings)
  - [Turning indexers on and off](#turning-indexers-on-and-off)
  - [All settings](#all-settings)
- [Private trackers](#private-trackers)
- [Failed and paused indexers](#failed-and-paused-indexers)
- [Merging duplicates](#merging-duplicates)
- [Sites protected by Cloudflare](#sites-protected-by-cloudflare)
- [Sites blocked by your provider's DNS](#sites-blocked-by-your-providers-dns)
- [Updating](#updating)
- [Indexer definitions](#indexer-definitions)
- [Files and privacy](#files-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Command line and development](#command-line-and-development)
- [Credits](#credits)
- [License](#license)

## Quick start

You need qBittorrent with its search engine turned on, and Python 3.9 or newer.

1. In qBittorrent, open **Search → Search plugins… → Install a new one → Web link**.
2. Paste this link and confirm:

   ```
   https://raw.githubusercontent.com/gusperroni/jackettless/main/jackettless.py
   ```

3. Search for something, choosing **Jackettless** (or "All plugins") as the search engine.

That's it. The first search takes a bit longer, because jackettless downloads the indexer definitions from Jackett.
After that, every search runs on all public indexers at the same time.

## How it works

[Jackett](https://github.com/Jackett/Jackett) supports hundreds of torrent sites through **indexer definitions**:
small files that describe how to search each site. Normally, you run the Jackett server all the time, and
qBittorrent's Jackett plugin talks to it.

jackettless reads the same definitions and runs them **inside the qBittorrent plugin itself**:

```
With Jackett:      qBittorrent → plugin → Jackett server (always running) → sites
With jackettless:  qBittorrent → jackettless → sites
```

There is no server, no API key and nothing running in the background. The plugin only runs while you search.

Out of the box, jackettless:

- searches **every public indexer** from Jackett, about 80 sites;
- shows **one row listing the indexers that failed**, and why;
- **merges duplicates**: the same torrent found on several sites becomes one row;
- **pauses indexers that keep failing**, so searches stay fast.

## Settings

Settings live in `jackettless.json`, next to the plugin. jackettless creates the file on the first search:

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\qBittorrent\nova3\engines\` |
| Linux | `~/.local/share/qBittorrent/nova3/engines/` |
| macOS | `~/Library/Application Support/qBittorrent/nova3/engines/` |

Changes apply on the next search; there is no need to restart qBittorrent. Settings you leave out use their
default value. If the file has a mistake, such as a missing comma, jackettless uses the defaults and shows a row
like `[jackettless] (search: ubuntu) jackettless.json is invalid (...), default settings in use`.

### Turning indexers on and off

After the first search, the `indexers` section lists every public indexer:

```json
"indexers": {
    "1337x": { "enabled": true },
    "nyaasi": { "enabled": true },
    "thepiratebay": { "enabled": true },
    "yts": { "enabled": true }
}
```

- **To stop using a site**, change its `true` to `false`.
- **New public sites** that Jackett adds later appear in the list by themselves.
- **To search only a few sites**, set `"all_public": false` and keep only those sites in the list (or set the others
  to `false`).
- **Sites that Jackett removes** are skipped; you can delete their lines.
- **To add a private tracker**, add it with your account. See [Private trackers](#private-trackers).

Every indexer also accepts these settings:

| setting | what it does |
|---|---|
| `enabled` | `false` turns the indexer off and keeps its other settings. |
| `username`, `password` | Your account, for private trackers. |
| `cookie` | Cookies copied from your browser. See [Private trackers](#private-trackers) and [Cloudflare](#sites-protected-by-cloudflare). |
| `user_agent` | The User-Agent sent to this site. |
| `sitelink` | A specific address (mirror) for the site. |

An indexer also accepts the options of its definition, the same ones Jackett shows on its settings screen, such as
`sort` or `freeleech`.

### All settings

| setting | default | what it does |
|---|---|---|
| `all_public` | `true` | Keep the `indexers` list filled with every public Jackett indexer, including new ones. With `false`, no new sites are added; the ones already listed still run until you set them to `false`. |
| `report_errors` | `"summary"` | Show failed indexers as a result row: `"summary"` (one row), `"all"` (one row per indexer) or `"none"`. |
| `dedup` | `"merge"` | Merge duplicate results into one row. `"off"` shows every copy. |
| `dedup_wait` | `8` | Seconds to wait before showing merged results. |
| `backoff` | `true` | Pause indexers that keep failing. See [Failed and paused indexers](#failed-and-paused-indexers). |
| `thread_count` | `20` | How many indexers are searched at the same time. |
| `indexer_timeout` | `30` | Maximum seconds one indexer can take in a search. |
| `timeout` | `10` | Maximum seconds for each web request. |
| `tracker_first` | `true` | Start each result name with its site, e.g. `[The Pirate Bay] Ubuntu 24.04`. |
| `dns_over_https` | `null` | See [Sites blocked by your provider's DNS](#sites-blocked-by-your-providers-dns). |
| `refresh_days` | `1` | How often, in days, to check Jackett for updated definitions. |
| `definitions_ref` | `"master"` | Jackett branch, tag or commit to take definitions from. |
| `verbose` | `false` | Write a detailed log. Useful from the [command line](#command-line-and-development). |

A full example is in [`jackettless.example.json`](jackettless.example.json).

## Private trackers

Private trackers are never added automatically, because they need your account. Add one with its id and your login:

```json
"torrentleech": { "username": "me", "password": "secret" }
```

jackettless logs in, keeps the session, and logs in again when it expires.

If the site shows a **captcha** on its login page, use a cookie instead:

1. Log in with your browser. If there is a "remember me" option, tick it.
2. Press **F12**, open the **Network** tab and reload the page.
3. Click the first request. Under **Request Headers**, copy the whole `cookie:` value.
4. Paste it as the indexer's `cookie`.

> [!WARNING]
> Passwords and cookies are saved as plain text in `jackettless.json` and in the `jackettless_data` folder, like the
> official Jackett plugin does. Keep that folder private, and never share these files.

## Failed and paused indexers

Some sites are down, slow or blocked at any given time. After each search, jackettless adds one row that says which
indexers failed, and why:

```
[jackettless] (search: ubuntu) 3 of 60 indexers failed: 1337x (Cloudflare), example (timeout), other (DNS blocked/failed); 12 paused after repeated failures
```

- **Paused indexers.** When an indexer fails twice in a row, jackettless skips it for 1 hour. If it keeps failing,
  the pause grows to 6 hours and then 24 hours. One successful search brings it back to normal, and failures more
  than two days apart don't count as "in a row".
- **What each reason means**, and what you can do, is in [Troubleshooting](#troubleshooting).
- The row is a message, not a torrent. It contains your search words, so qBittorrent's name filter doesn't hide it.

To change this, use `"report_errors": "all"` (one row per failure), `"none"` (no rows) or `"backoff": false` (never
pause).

## Merging duplicates

The same torrent often appears on several sites. jackettless shows it once, with every site in the name:

```
[The Pirate Bay, YTS] Big Buck Bunny (2008) [1080p]
```

- The magnet link includes the trackers of every copy.
- Seeds and leechers show the highest value among the copies.
- Results are held for up to 8 seconds (`dedup_wait`) so they can be merged.
- Private trackers and sites that don't show the torrent's hash in their listings are never merged.

To see every copy separately, set `"dedup": "off"`.

## Sites protected by Cloudflare

Some sites make every visitor pass a browser check. jackettless can't do that, so these indexers fail with the
reason `Cloudflare`. Jackett needs an extra service, FlareSolverr, for the same sites.

On some of them, you can reuse the check your own browser already passed:

1. Open the site in your browser and wait until it loads.
2. Press **F12**, open the **Network** tab, reload, and click the first request.
3. Under **Request Headers**, copy the `cf_clearance=...` part of `cookie:`, and the whole `user-agent:` value.
4. Add both to the indexer:

   ```json
   "1337x": {
       "enabled": true,
       "cookie": "cf_clearance=PASTE_HERE",
       "user_agent": "PASTE THE EXACT USER-AGENT HERE"
   }
   ```

This only works from the same internet connection and with the exact same User-Agent, and it expires after hours
or days. Some sites, such as EZTV, check more than that, and it doesn't work there at all.

## Sites blocked by your provider's DNS

Some internet providers block torrent sites by DNS. Those indexers fail with `DNS blocked/failed`. If you don't use
a DNS service that avoids this (for example dnscrypt-proxy, or secure DNS set up on your system), add:

```json
"dns_over_https": "https://1.1.1.1/dns-query"
```

jackettless then looks up the site address through that service, **only when the normal lookup fails**. Connections
are still checked against the real site name.

## Updating

qBittorrent's **Check for updates** button only updates the **official** plugins. jackettless is unofficial, so:

- **To update**, install it again by **Web link** (see [Quick start](#quick-start)). Your settings are kept.
- **To know when there is a new version**, click **Watch → Custom → Releases** at the top of this page.
- **Indexer definitions** update by themselves, once a day.

To **uninstall**, remove it in qBittorrent's **Search plugins…** window, then delete `jackettless.json` and the
`jackettless_data` folder.

## Indexer definitions

jackettless doesn't include any site. It downloads [Jackett's definitions](https://github.com/Jackett/Jackett/tree/master/src/Jackett.Common/Definitions)
and keeps them up to date.

- **Find a site's id.** Every `.yml` file in that folder is a site jackettless can use. The id is the file name
  without `.yml`. For example, `kickasstorrents-ws.yml` is `"kickasstorrents-ws"`. The `type:` line at the top says
  whether it is `public`, `semi-private` or `private`.
- **Use your own definition.** Put a `.yml` file in `jackettless_data/custom/` and add its id to `indexers`. A file
  there replaces Jackett's definition with the same id.
- **Report a broken site to the right place.** If a site's results or login are wrong in Jackett too, the definition
  is what needs fixing: report it to Jackett. If it works in Jackett but not in jackettless, please open an issue
  here.

## Files and privacy

Everything is kept next to the plugin, in qBittorrent's `engines` folder:

| path | contents |
|---|---|
| `jackettless.json` | Your settings, including any passwords or cookies. |
| `jackettless_data/definitions/` | The downloaded definitions. |
| `jackettless_data/custom/` | Your own definitions. |
| `jackettless_data/cookies/` | Login sessions of private trackers. |
| `jackettless_data/state.json` | Working mirrors and paused indexers. |

Besides the sites you search, jackettless only connects to:

- **GitHub**, to download definitions, at most once a day;
- **your DNS-over-HTTPS server**, only if you set one, and only when a normal lookup fails.

Nothing else is collected or sent. Definitions are data, not code: they can't run programs on your computer. Your
cookies are only sent to the site they belong to.

## Troubleshooting

| you see | what to do |
|---|---|
| `Cloudflare` | The site requires a browser check. See [Sites protected by Cloudflare](#sites-protected-by-cloudflare), or turn the indexer off. |
| `DNS blocked/failed` | See [Sites blocked by your provider's DNS](#sites-blocked-by-your-providers-dns). |
| `timeout` | The site is slow or down. It is paused automatically if it keeps failing. |
| `network error` | The site could not be reached. Try again later. |
| a login message | Check `username` / `password`, or use a `cookie`. |
| `definition "x" not available` | The id is wrong, or Jackett removed that site. See [Indexer definitions](#indexer-definitions). |
| `jackettless.json is invalid` | The file has a mistake. The row shows the line and column. |
| `no indexers enabled` | Every site is set to `false`, or the list is empty with `"all_public": false`. |
| `Error occurred in search engine` in qBittorrent's log | qBittorrent logs every plugin message there, even when the search worked. jackettless only writes one line when indexers fail. |
| The first search is slow | jackettless is downloading the definitions. Later searches are faster. |

For a detailed log of one site, run this in the `engines` folder:

```bash
python jackettless.py -v search "ubuntu" --indexer thepiratebay
```

## Limitations

- **Only YAML definitions.** About 60 of Jackett's sites are written in C# instead, and jackettless can't run them.
  Some of them, such as AudioBookBay and TorrentsCSV, have their own qBittorrent plugins.
- **Cloudflare.** Sites with a browser check only work with the cookie workaround, and not all of them.
- **Keywords only.** qBittorrent sends words and a category. Searches by IMDb id, season or episode aren't
  available.
- **3-minute limit.** qBittorrent stops a search after 3 minutes and keeps the results shown so far. jackettless
  gives each site at most `indexer_timeout` seconds, so searches end well before that.
- **No settings screen.** qBittorrent plugins have no settings window, so settings live in `jackettless.json`.
- **A port of Jackett's engine.** A few definitions may behave differently than in Jackett. Please report them.

## Command line and development

The plugin also runs from a terminal, from the `engines` folder:

| command | what it does |
|---|---|
| `python jackettless.py search "ubuntu"` | Search, like qBittorrent does. Add `--indexer ID` to search only one site (even a paused one), `--json` for JSON output and `-v` for a detailed log. |
| `python jackettless.py list --type public` | List the downloaded definitions. |
| `python jackettless.py sync --all` | Download or update every definition. |
| `python jackettless.py login ID` | Test a private tracker login and save the session. |

The tests use only the standard library and a fake local tracker, so they run without internet access:

```bash
python -m unittest discover -s tests
```

Two tools help with development:

- `tools/coverage.py` checks which Jackett definitions jackettless supports. With `--live`, it also searches every
  public site.
- `tools/benchmark.py` measures search speed with different `thread_count` and timeout values.

Bug reports and pull requests are welcome. For a broken site, please include its id and the output of the `-v`
command above.

## Credits

jackettless exists thanks to these projects and their communities:

- **[Jackett](https://github.com/Jackett/Jackett)** and its contributors. jackettless is a port of Jackett's
  Cardigann engine, and every search it runs uses the indexer definitions that the Jackett community writes and
  keeps working as sites change. If jackettless is useful to you, please consider supporting Jackett.
- **[Cardigann](https://github.com/cardigann/cardigann)** and its contributors, who created the definition format
  that Jackett adopted.
- **[qBittorrent](https://github.com/qbittorrent/qBittorrent)** and
  **[qbittorrent/search-plugins](https://github.com/qbittorrent/search-plugins)**, for the search engine, the plugin
  API and the official Jackett plugin that inspired this one.
- **[jackettdedup](https://github.com/arihan-1560795/jackettdedup)**, whose idea of merging results by infohash
  inspired the `dedup` option.

jackettless is not affiliated with or endorsed by any of these projects.

## License

jackettless is free software under the [GNU General Public License v2.0 or later](LICENSE). As a port of Jackett's
Cardigann engine, it keeps a license compatible with Jackett's (GPL-2.0). The indexer definitions are not part of
this repository: they are downloaded from Jackett, under Jackett's license.
