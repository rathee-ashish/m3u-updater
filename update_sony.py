#!/usr/bin/env python3
"""
update_sony_m3u.py

- Replaces blocks for channels listed in sonychannels.txt (Sony channels)
  with fresh blocks from SONY_SOURCE_URL
- Ensures group-title is set from respective channel file
- Extracts cookie + user-agent (from URL or existing #EXTHTTP/#EXTVLCOPT)
- Inserts #EXTVLCOPT and #EXTHTTP in the desired format
- Rewrites URL to: base?cookie_part&xxx=%7Ccookie=cookie_part
- Does NOT print license keys/cookies to logs
"""
import re
import requests

MY_PLAYLIST = "my_playlist.m3u"
SONY_CHANNELS_FILE = "sonychannels.txt"
SONY_SOURCE_URL = "https://solii.saqlainhaider8198.workers.dev/"


# ---- Same helper functions as above ---- #
# (parse_channels_file, fetch_source_lines, parse_m3u_blocks, set_group_title_in_extinf, transform_block)
# You can copy them exactly from the Star script above


# To avoid redundancy here, you’d simply copy-paste the same helpers from update_star_m3u.py
# and just change CHANNELS_FILE + SOURCE_URL + printed log labels.


def main():
    print("[LOG] Reading sonychannels.txt (Sony channels)")
    sony_groups = parse_channels_file(SONY_CHANNELS_FILE)
    sony_channel_to_group = {ch.lower(): grp for grp, chs in sony_groups.items() for ch in chs}

    print("[LOG] Fetching Sony source M3U…")
    sony_source_lines = fetch_source_lines(SONY_SOURCE_URL)
    _, sony_source_blocks_list = parse_m3u_blocks(sony_source_lines)
    sony_source_blocks = {name.lower(): block for name, block in sony_source_blocks_list}
    print(f"[LOG] Sony source contains {len(sony_source_blocks)} channels")

    try:
        with open(MY_PLAYLIST, "r", encoding="utf-8") as f:
            my_lines = f.read().splitlines()
    except FileNotFoundError:
        my_lines = ["#EXTM3U"]

    header, my_blocks = parse_m3u_blocks(my_lines)

    updated_blocks = []
    updated_channels = set()

    for name, block in my_blocks:
        lname = name.lower()
        if lname in sony_channel_to_group and lname in sony_source_blocks:
            new_block = transform_block(sony_source_blocks[lname])
            new_block[0] = set_group_title_in_extinf(new_block[0], sony_channel_to_group[lname])
            updated_blocks.append((name, new_block))
            updated_channels.add(lname)
            print(f"[LOG] Replaced Sony channel: {name}")
        else:
            updated_blocks.append((name, block))

    for ch_lower, group in sony_channel_to_group.items():
        if ch_lower not in updated_channels and ch_lower in sony_source_blocks:
            new_block = transform_block(sony_source_blocks[ch_lower])
            new_block[0] = set_group_title_in_extinf(new_block[0], group)
            name = new_block[0].rpartition(",")[2].strip()
            updated_blocks.append((name, new_block))
            print(f"[LOG] Added Sony channel: {name}")

    output_lines = header or ["#EXTM3U"]
    for _, block in updated_blocks:
        output_lines.extend(block)

    with open(MY_PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print(f"[LOG] ✅ Playlist updated with {len(updated_blocks)} channels")


if __name__ == "__main__":
    main()
