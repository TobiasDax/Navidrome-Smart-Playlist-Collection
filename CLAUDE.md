# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of Navidrome smart playlists (`.nsp` files) in JSON format, plus a Python utility script. There is no build system, linter, or test suite — the "development" workflow is editing `.nsp` files and importing them into Navidrome.

## Playlist architecture

Playlists are numbered to establish a dependency order — lower numbers depend on higher numbers:

| Prefix | Role |
|--------|------|
| `09 - Genre - *` | Base genre playlists. Built from `contains artist/album` rules. These are the foundation everything else references via `inPlaylist` IDs. |
| `99 - Weight - *` | Star-rating buckets (1–5 stars) with play limits and skip-ban windows (`notInTheLast`). |
| `99 - Sort - GENRE - 3` / `4+` | Intersection of a Genre playlist and a rating filter. 50 tracks (3★) or 250 tracks (4+★), random sort. |
| `07 - Auswahl - *` | Combines the two Sort playlists for a genre into a single enjoyable genre mix. |
| `999 - Auto - Sort - *` | Like `99 - Sort` but tuned for car listening (larger limits). |
| `999 - Auto - Auswahl - *` | Combines the two Auto Sort playlists per genre. 400 tracks total. |
| `00 - Dax - *` | Top-level personal playlists built from Weight buckets. Synced offline to phone. |
| `08 - Unsorted - *` | Catch-all for tracks not yet assigned to any Genre playlist or rated. |
| `01` | Discovery/surfacing playlists — recently added, recently played, never played, rarely played, etc. |
| `02–06` | Reserved for manually curated playlists. |

## Key constraints when editing

- **IDs are instance-specific.** Every `inPlaylist` / `notInPlaylist` reference uses a Navidrome-internal UUID or short ID. The mapping between playlist name and ID is in `README.md`. When creating a new playlist that others will reference, its ID must be added to `README.md` and then manually updated in every dependent playlist.
- **Genre playlists use `contains artist`**, not `inPlaylist`, so adding an artist to a genre means appending a `{"contains": {"artist": "..."}}` entry to the relevant `09 - Genre - *.nsp` file.
- **`08 - Unsorted - Genre`** is built by negating *all* genre playlist IDs — when a new `09 - Genre` playlist is added, its ID must also be added as a `notInPlaylist` rule here.
- **Sort playlists** reference Genre playlist IDs directly and apply a `gt`/`is` rating filter — no artist lists needed.
- **`99 - Weight - 4 Stars`** and lower use `notInTheLast` to avoid recently-skipped tracks. The value is in days.
