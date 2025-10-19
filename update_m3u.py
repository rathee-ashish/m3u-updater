#!/usr/bin/env python3
"""
update_m3u.py

- Replaces blocks for channels listed in channels.txt (Star channels) with fresh blocks from STAR_SOURCE_URL
- Replaces blocks for channels listed in sonychannels.txt (Sony channels) with fresh blocks from SONY_SOURCE_URL
- Ensures group-title is set from respective channel files
- Extracts cookie + user-agent (from URL or existing #EXTHTTP/#EXTVLCOPT)
- Inserts #EXTVLCOPT and #EXTHTTP in the desired format and rewrites URL to:
    base?cookie_part&xxx=%7Ccookie=cookie_part
- Does NOT print license keys/cookies to logs
- Processes both Star and Sony channels separately with their respective sources
"""
import re
import requests

MY_PLAYLIST = "my_playlist.m3u"
CHANNELS_FILE = "channels.txt"
SONY_CHANNELS_FILE = "sonychannels.txt"
STAR_SOURCE_URL = "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/jtv.m3u"
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
    # keep original line endings removed
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
            # display name after last comma
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
    """
    - Find URL line (last non-# non-empty line)
    - Extract cookie (from #EXTHTTP JSON or from URL |Cookie=... segment)
    - Extract UA (from #EXTVLCOPT line or from URL &User-Agent=... segment)
    - Remove existing #EXTVLCOPT and #EXTHTTP lines and the old URL
    - Insert new #EXTVLCOPT and #EXTHTTP (if found)
    - Append transformed URL (base?cookie_part&xxx=%7Ccookie=cookie_part) or original URL if nothing found
    Returns new_block (list of lines).
    """
    if not src_block:
        return src_block

    # find URL index (last non-# line)
    url_idx = None
    for i in range(len(src_block) - 1, -1, -1):
        ln = src_block[i].strip()
        if ln and not ln.startswith("#"):
            url_idx = i
            break

    # scan for existing cookie / UA lines
    cookie_from_exthttp = None
    ua_from_extvlc = None
    for ln in src_block:
        if ln.startswith("#EXTHTTP"):
            m = re.search(r'"cookie"\s*:\s*"([^"]+)"', ln)
            if m:
                cookie_from_exthttp = m.group(1)
        if ln.startswith("#EXTVLCOPT"):
            # look for http-user-agent=
            m = re.search(r'http-user-agent=(.*)', ln, flags=re.IGNORECASE)
            if m:
                ua_from_extvlc = m.group(1).strip()

    cookie_only = cookie_from_exthttp
    ua = ua_from_extvlc
    url_line = None
    if url_idx is not None:
        url_line = src_block[url_idx].strip()

    # If cookie not found from #EXTHTTP, try parse from URL '|Cookie=' pattern
    if cookie_only is None and url_line:
        # case-insensitive check for '|cookie='
        cookie_split = re.split(r'\|[Cc]ookie=', url_line, 1)
        if len(cookie_split) == 2:
            base = cookie_split[0].strip()
            tail = cookie_split[1].strip()
            # split off User-Agent if present
            ua_split = re.split(r'&[Uu]ser-[Aa]gent=', tail, 1)
            cookie_part = ua_split[0].strip()
            cookie_only = cookie_part
            if len(ua_split) > 1:
                ua = ua_split[1].strip()

    # If still no cookie found, but URL already has ?__hdnea__ and &xxx=%7Ccookie=, try to extract cookie part
    if cookie_only is None and url_line:
        if "?__hdnea__=" in url_line and "&xxx=%7Ccookie=" in url_line:
            m = re.search(r'&xxx=%7Ccookie=([^&\s]+)', url_line)
            if m:
                cookie_only = m.group(1)

    # Build transformed URL (only if we have base & cookie info)
    transformed_url = url_line
    if cookie_only and url_line:
        # compute base (the left part before any '|' or before '?')
        base_match = re.split(r'\|[Cc]ookie=|\?', url_line, 1)
        # Prefer left of '|' if present, else before '?', else whole
        # but better: if '|cookie=' was present earlier we already split into base variable
        # We'll reconstruct base robustly:
        if re.search(r'\|[Cc]ookie=', url_line):
            base = re.split(r'\|[Cc]ookie=', url_line, 1)[0].strip()
        else:
            # take up to first '?' as base
            base = url_line.split("?", 1)[0].strip()
        # Construct new URL in exact required format:
        # base?cookie_only&xxx=%7Ccookie=cookie_only
        transformed_url = f"{base}?{cookie_only}&xxx=%7Ccookie={cookie_only}"

    # Rebuild new block: preserve lines except old #EXTVLCOPT/#EXTHTTP and old URL
    new_block = []
    for idx, ln in enumerate(src_block):
        # skip old #EXTVLCOPT and #EXTHTTP lines
        if ln.startswith("#EXTVLCOPT") or ln.startswith("#EXTHTTP"):
            continue
        # skip the old URL line (we'll append transformed_url later)
        if idx == url_idx:
            continue
        # keep everything else (including #KODIPROP and #EXTINF)
        new_block.append(ln)

    # append #EXTVLCOPT if ua found
    if ua:
        ua_clean = ua.strip()
        new_block.append(f'#EXTVLCOPT:http-user-agent={ua_clean}')

    # append #EXTHTTP if cookie found
    if cookie_only:
        cookie_clean = cookie_only.strip()
        new_block.append(f'#EXTHTTP:{{"cookie":"{cookie_clean}"}}')

    # append transformed_url or fallback to original url
    if transformed_url:
        new_block.append(transformed_url)

    return new_block


def main():
    print("[LOG] Reading channels.txt (Star channels)")
    star_groups = parse_channels_file(CHANNELS_FILE)
    # mapping channel name (lower) -> group for Star channels
    star_channel_to_group = {ch.lower(): grp for grp, chs in star_groups.items() for ch in chs}

    print("[LOG] Reading sonychannels.txt (Sony channels)")
    sony_groups = parse_channels_file(SONY_CHANNELS_FILE)
    # mapping channel name (lower) -> group for Sony channels
    sony_channel_to_group = {ch.lower(): grp for grp, chs in sony_groups.items() for ch in chs}

    print("[LOG] Fetching Star source M3U…")
    star_source_lines = fetch_source_lines(STAR_SOURCE_URL)
    _, star_source_blocks_list = parse_m3u_blocks(star_source_lines)
    star_source_blocks = {name.lower(): block for name, block in star_source_blocks_list}
    print(f"[LOG] Star source contains {len(star_source_blocks)} channels")

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

    # Process Star channels
    print("[LOG] Processing Star channels...")
    for name, block in my_blocks:
        lname = name.lower()
        if lname in star_channel_to_group and lname in star_source_blocks:
            src_block = list(star_source_blocks[lname])
            new_block = transform_block(src_block)
            # set desired group-title
            desired_group = star_channel_to_group[lname]
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            updated_blocks.append((name, new_block))
            updated_channels.add(lname)
            print(f"[LOG] Replaced Star channel with fresh block: {name}")
        else:
            # keep untouched (will be processed for Sony channels later)
            updated_blocks.append((name, block))

    # Add missing Star channels from channel list (if not already updated)
    for ch_lower, desired_group in star_channel_to_group.items():
        if ch_lower not in updated_channels and ch_lower in star_source_blocks:
            src_block = list(star_source_blocks[ch_lower])
            new_block = transform_block(src_block)
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            display_name = new_block[0].rpartition(",")[2].strip()
            updated_blocks.append((display_name, new_block))
            updated_channels.add(ch_lower)
            print(f"[LOG] Added new Star channel: {display_name}")

    # Process Sony channels
    print("[LOG] Processing Sony channels...")
    # First, replace existing Sony channels
    for i, (name, block) in enumerate(updated_blocks):
        lname = name.lower()
        if lname in sony_channel_to_group and lname in sony_source_blocks:
            src_block = list(sony_source_blocks[lname])
            new_block = transform_block(src_block)
            # set desired group-title
            desired_group = sony_channel_to_group[lname]
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            updated_blocks[i] = (name, new_block)
            updated_channels.add(lname)
            print(f"[LOG] Replaced Sony channel with fresh block: {name}")

    # Add missing Sony channels from channel list (if not already updated)
    for ch_lower, desired_group in sony_channel_to_group.items():
        if ch_lower not in updated_channels and ch_lower in sony_source_blocks:
            src_block = list(sony_source_blocks[ch_lower])
            new_block = transform_block(src_block)
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            display_name = new_block[0].rpartition(",")[2].strip()
            updated_blocks.append((display_name, new_block))
            updated_channels.add(ch_lower)
            print(f"[LOG] Added new Sony channel: {display_name}")

    # Reconstruct playlist
    output_lines = header or ["#EXTM3U"]
    for _, block in updated_blocks:
        output_lines.extend(block)

    with open(MY_PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print(f"[LOG] ✅ Playlist updated, total {len(updated_blocks)} channels")
    print(f"[LOG] Star channels processed: {len([ch for ch in updated_channels if ch in star_channel_to_group])}")
    print(f"[LOG] Sony channels processed: {len([ch for ch in updated_channels if ch in sony_channel_to_group])}")


if __name__ == "__main__":
    main()
