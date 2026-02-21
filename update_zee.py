#!/usr/bin/env python3
"""
update_zee.py

- Replaces or adds Zee channels listed in zeechannels.txt
  with fresh blocks from ZEE_SOURCE_URL
- Preserves cookie/user-agent handling
- Preserves EXTHTTP headers (Origin/Referer)
- Sets group-title from zeechannels.txt
- Writes back to my_playlist.m3u
"""

import re
import requests

MY_PLAYLIST = "my_playlist.m3u"
ZEE_CHANNELS_FILE = "zeechannels.txt"
ZEE_SOURCE_URL = "https://join-vaathala1-for-more.vodep39240327.workers.dev/zee5.m3u"


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

    url_idx = None
    for i in range(len(src_block) - 1, -1, -1):
        ln = src_block[i].strip()
        if ln and not ln.startswith("#"):
            url_idx = i
            break

    original_exthttp = None
    ua_from_extvlc = None
    cookie_only = None

    # READ EXISTING HEADERS
    for ln in src_block:
        if ln.startswith("#EXTHTTP"):
            original_exthttp = ln
            m = re.search(r'"cookie"\s*:\s*"([^"]+)"', ln, re.IGNORECASE)
            if m:
                cookie_only = m.group(1)

        if ln.startswith("#EXTVLCOPT"):
            m = re.search(r'http-user-agent=(.*)', ln, flags=re.IGNORECASE)
            if m:
                ua_from_extvlc = m.group(1).strip()

    url_line = src_block[url_idx].strip() if url_idx is not None else None

    # COOKIE FROM URL
    if cookie_only is None and url_line:
        cookie_split = re.split(r'\|[Cc]ookie=', url_line, 1)
        if len(cookie_split) == 2:
            tail = cookie_split[1].strip()
            ua_split = re.split(r'&[Uu]ser-[Aa]gent=', tail, 1)
            cookie_only = ua_split[0].strip()
            if len(ua_split) > 1:
                ua_from_extvlc = ua_split[1].strip()

    # TRANSFORM URL
    transformed_url = url_line
    if cookie_only and url_line:
        base = url_line.split('?', 1)[0].strip()
        transformed_url = f"{base}?{cookie_only}&xxx=%7Ccookie={cookie_only}"

    # BUILD NEW BLOCK
    new_block = []

    for idx, ln in enumerate(src_block):
        if idx == url_idx:
            continue
        if ln.startswith("#EXTHTTP") or ln.startswith("#EXTVLCOPT"):
            continue
        new_block.append(ln)

    # User-Agent
    if ua_from_extvlc:
        new_block.append(f'#EXTVLCOPT:http-user-agent={ua_from_extvlc}')

    # PRESERVE OR MERGE EXTHTTP
    if original_exthttp:
        if cookie_only and "cookie" not in original_exthttp.lower():
            json_part = original_exthttp.split(":", 1)[1].strip()
            json_part = json_part.rstrip("}")
            json_part += f',"cookie":"{cookie_only}"' + "}"
            new_block.append(f"#EXTHTTP:{json_part}")
        else:
            new_block.append(original_exthttp)
    elif cookie_only:
        new_block.append(f'#EXTHTTP:{{"cookie":"{cookie_only}"}}')

    if transformed_url:
        new_block.append(transformed_url)

    return new_block


def main():
    print("[LOG] Reading zeechannels.txt")
    zee_groups = parse_channels_file(ZEE_CHANNELS_FILE)
    zee_channel_to_group = {ch.lower(): grp for grp, chs in zee_groups.items() for ch in chs}

    print("[LOG] Fetching Zee source M3U…")
    zee_source_lines = fetch_source_lines(ZEE_SOURCE_URL)
    _, zee_source_blocks_list = parse_m3u_blocks(zee_source_lines)
    zee_source_blocks = {name.lower(): block for name, block in zee_source_blocks_list}

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
        if lname in zee_channel_to_group and lname in zee_source_blocks:
            src_block = list(zee_source_blocks[lname])
            new_block = transform_block(src_block)
            desired_group = zee_channel_to_group[lname]
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            updated_blocks.append((name, new_block))
            updated_channels.add(lname)
        else:
            updated_blocks.append((name, block))

    for ch_lower, desired_group in zee_channel_to_group.items():
        if ch_lower not in updated_channels and ch_lower in zee_source_blocks:
            src_block = list(zee_source_blocks[ch_lower])
            new_block = transform_block(src_block)
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            display_name = new_block[0].rpartition(",")[2].strip()
            updated_blocks.append((display_name, new_block))

    output_lines = header or ["#EXTM3U"]
    for _, block in updated_blocks:
        output_lines.extend(block)

    with open(MY_PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print("[LOG] Playlist updated successfully")


if __name__ == "__main__":
    main()
