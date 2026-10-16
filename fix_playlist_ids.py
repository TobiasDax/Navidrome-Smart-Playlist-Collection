"""Rewrite stale inPlaylist/notInPlaylist ids in .nsp files (and the README id tables)
to the current Navidrome playlist ids.

Usage: python3 -I fix_playlist_ids.py <nsp dir> <current navidrome.db> <older navidrome.db> [--apply]

Stale ids are resolved, in order, by:
  1. the `manual` dict below (id -> playlist name),
  2. looking the id up in the older DB and finding the playlist with the same name now,
  3. for "07 - Auswahl - X" / "999 - Auto - Auswahl - X": the genre's "Sort - 3" and "Sort - 4+" playlists,
  4. README rows: "Genre - X" -> "09 - Genre - X", "Auto - Sort - X" -> "999 - Auto - Sort - X".
The older DB should be a backup from before the playlists got new ids.
Without --apply it is a dry run that only prints the mapping. Stop Navidrome or
open the DBs from copies; they are only read."""
import re, sqlite3, sys
from pathlib import Path

nsp_dir, cur_db, old_db = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
APPLY = "--apply" in sys.argv
cur = sqlite3.connect(f"file:{cur_db}?mode=ro", uri=True)
old = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True)
cur_by_id = dict(cur.execute("select id, name from playlist"))
cur_by_name = {n: i for i, n in cur.execute("select id, name from playlist")}
old_by_id = dict(old.execute("select id, name from playlist"))
manual = {"JfBCqu9IpTEbJH3sgoM01W": "Spotisub - Vietnam"}
ID_RE = re.compile(r'"id"\s*:\s*"([^"]+)"')

problems = 0
replaced = {}
for f in sorted(nsp_dir.glob("*.nsp")):
    text = f.read_text()
    ids = ID_RE.findall(text)
    if not ids:
        continue
    # inferred targets for Auswahl files: their genre's Sort - 3 / Sort - 4+ playlists
    m = re.match(r"(999 - Auto - |0?7 - )Auswahl - (.+)\.nsp$", f.name)
    inferred = []
    if m:
        prefix = "999 - Auto - Sort - " if m.group(1).startswith("999") else "99 - Sort - "
        inferred = [cur_by_name.get(f"{prefix}{m.group(2)} - 3"), cur_by_name.get(f"{prefix}{m.group(2)} - 4+")]
        inferred = [i for i in inferred if i and i not in ids]
    new = text
    for pid in ids:
        if pid in cur_by_id:
            continue
        target = None
        if pid in manual:
            target = cur_by_name.get(manual[pid]); how = f"manual '{manual[pid]}'"
        elif pid in old_by_id and old_by_id[pid] in cur_by_name:
            target = cur_by_name[old_by_id[pid]]; how = f"by name '{old_by_id[pid]}'"
        elif inferred:
            target = inferred.pop(0); how = f"inferred '{cur_by_id[target]}'"
        if not target:
            print(f"!! {f.name}: {pid} unresolved"); problems += 1
            continue
        new = new.replace(f'"{pid}"', f'"{target}"')
        print(f"{f.name}: {pid} -> {target} ({how})")
    if new != text and APPLY:
        f.write_text(new)
        replaced[pid] = target

# README id tables: same mapping, plain-text ids
readme = nsp_dir / "README.md"
rtext = readme.read_text()
rnew = rtext
for pid, target in replaced.items():
    rnew = rnew.replace(f" {pid} ", f" {target} ")
# README rows with ids not referenced by any .nsp: resolve by row name
for row_name, pid in re.findall(r"^\| ([^|]+?) \| (\S+) \|$", rtext, re.M):
    if pid in cur_by_id or pid in replaced or row_name in ("Playlist", "---"):
        continue
    name = ("999 - " if row_name.startswith("Auto") else "09 - ") + row_name
    if name in cur_by_name:
        rnew = rnew.replace(f" {pid} ", f" {cur_by_name[name]} "); print(f"README: {row_name}: {pid} -> {cur_by_name[name]}")
    else:
        print(f"!! README: {row_name}: {pid} unresolved"); problems += 1
if APPLY and rnew != rtext:
    readme.write_text(rnew)
print("unresolved:", problems, "| APPLIED" if APPLY else "| DRY RUN")
