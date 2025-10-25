#!/usr/bin/env python3
"""
update_sony.py

- Replaces or adds channels listed in sonychannels.txt (Sony channels) with fresh blocks from SONY_SOURCE_URL
- Ensures group-title is set from sonychannels.txt
- Extracts cookie + user-agent (from URL or #EXTHTTP/#EXTVLCOPT)
- Inserts #EXTVLCOPT and #EXTHTTP in correct format
"""

import re
import requests

MY_PLAYLIST = "my_playlist.m3u"
SONY_CHANNELS_FILE = "sonychannels.txt"
SONY_SOURCE_URL = "https://solii.saqlainhaider8198.workers.dev/"


def parse_channels_file(path):
    groups = {}
    current_group = None
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = re.match(r'^([^:]+)\s*:\s*\{\s*$', line)
            if m:
                current_group = m.group(1).strip()
                groups[current_group] = []
                continue
            if line == "}" and current_group:
                current_group = None
                continue
            if current_group:
                ch = line.rstrip(",").strip()
                if ch:
                    groups[current_group].append(ch)
    return groups


def fetch_source_lines(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text.splitlines()


def parse_m3u_blocks(lines):
    header = []
    blocks = []
    current_block = []
    current_name = None
    in_block = False
    for line in lines:
        if line.startswith("#EXTINF"):
            if in_block and current_block and current_name is not None:
                blocks.append((current_name, current_block))
            current_block = [line]
            current_name = line.rpartition(",")[2].strip()
            in_block = True
        else:
            if in_block:
                current_block.append(line)
            else:
                header.append(line)
    if in_block and current_block and current_name is not None:
        blocks.append((current_name, current_block))
    return header, blocks


def set_group_title_in_extinf(extinf_line, group):
    prefix, sep, name = extinf_line.rpartition(",")
    if not sep:
        return extinf_line
    if 'group-title="' in prefix:
        prefix = re.sub(r'group-title="[^"]*"', f'group-title="{group}"', prefix)
    else:
        prefix = prefix + f' group-title="{group}"'
    return prefix + "," + name


def transform_block(src_block):
    if not src_block:
        return src_block

    # Find URL line (last non-# line)
    url_idx = None
    for i in range(len(src_block) - 1, -1, -1):
        ln = src_block[i].strip()
        if ln and not ln.startswith("#"):
            url_idx = i
            break

    cookie_from_exthttp = None
    ua_from_extvlc = None
    for ln in src_block:
        if ln.startswith("#EXTHTTP"):
            m = re.search(r'"cookie"\s*:\s*"([^"]+)"', ln)
            if m:
                cookie_from_exthttp = m.group(1)
        if ln.startswith("#EXTVLCOPT"):
            m = re.search(r'http-user-agent=(.*)', ln, flags=re.IGNORECASE)
            if m:
                ua_from_extvlc = m.group(1).strip()

    cookie_only = cookie_from_exthttp
    ua = ua_from_extvlc
    url_line = src_block[url_idx].strip() if url_idx is not None else None

    # If cookie not found in #EXTHTTP, check in URL
    if cookie_only is None and url_line:
        cookie_split = re.split(r'\|[Cc]ookie=', url_line, 1)
        if len(cookie_split) == 2:
            tail = cookie_split[1].strip()
            ua_split = re.split(r'&[Uu]ser-[Aa]gent=', tail, 1)
            cookie_only = ua_split[0].strip()
            if len(ua_split) > 1:
                ua = ua_split[1].strip()

    transformed_url = url_line
    if cookie_only and url_line:
        base = re.split(r'\|[Cc]ookie=|\?', url_line, 1)[0].strip()
        transformed_url = f"{base}?{cookie_only}&xxx=%7Ccookie={cookie_only}"

    new_block = []
    for idx, ln in enumerate(src_block):
        if ln.startswith("#EXTVLCOPT") or ln.startswith("#EXTHTTP"):
            continue
        if idx == url_idx:
            continue
        new_block.append(ln)

    if ua:
        new_block.append(f'#EXTVLCOPT:http-user-agent={ua.strip()}')
    if cookie_only:
        new_block.append(f'#EXTHTTP:{{"cookie":"{cookie_only.strip()}"}}')
    if transformed_url:
        new_block.append(transformed_url)

    return new_block


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
        print(f"[LOG] Loaded existing playlist with {len(my_lines)} lines")
    except FileNotFoundError:
        my_lines = ["#EXTM3U"]
        print("[LOG] No existing playlist, creating new")

    header, my_blocks = parse_m3u_blocks(my_lines)
    updated_blocks = []
    updated_channels = set()

    print("[LOG] Processing Sony channels...")
    for name, block in my_blocks:
        lname = name.lower()
        if lname in sony_channel_to_group and lname in sony_source_blocks:
            new_block = transform_block(list(sony_source_blocks[lname]))
            desired_group = sony_channel_to_group[lname]
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            updated_blocks.append((name, new_block))
            updated_channels.add(lname)
            print(f"[LOG] Replaced Sony channel: {name}")
        else:
            updated_blocks.append((name, block))

    # Add any missing Sony channels
    for ch_lower, desired_group in sony_channel_to_group.items():
        if ch_lower not in updated_channels and ch_lower in sony_source_blocks:
            new_block = transform_block(list(sony_source_blocks[ch_lower]))
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            display_name = new_block[0].rpartition(",")[2].strip()
            updated_blocks.append((display_name, new_block))
            updated_channels.add(ch_lower)
            print(f"[LOG] Added new Sony channel: {display_name}")

    output_lines = header or ["#EXTM3U"]
    for _, block in updated_blocks:
        output_lines.extend(block)

    with open(MY_PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print(f"[LOG] ✅ Playlist updated, total {len(updated_blocks)} channels (Sony only)")


if __name__ == "__main__":
    main()
