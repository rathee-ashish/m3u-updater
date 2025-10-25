#!/usr/bin/env python3
"""
update_star_m3u.py

- Replaces blocks for channels listed in starchannel.txt (Star channels)
  with fresh blocks from STAR_SOURCE_URL
- Ensures group-title is set from respective channel file
- Extracts cookie + user-agent (from URL or existing #EXTHTTP/#EXTVLCOPT)
- Inserts #EXTVLCOPT and #EXTHTTP in the desired format
- Rewrites URL to: base?cookie_part&xxx=%7Ccookie=cookie_part
- Does NOT print license keys/cookies to logs
"""
import re
import requests

MY_PLAYLIST = "my_playlist.m3u"
CHANNELS_FILE = "starchannel.txt"
STAR_SOURCE_URL = "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/jtv.m3u"


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
        prefix += f' group-title="{group}"'
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

    cookie = None
    ua = None
    for ln in src_block:
        if ln.startswith("#EXTHTTP"):
            m = re.search(r'"cookie"\s*:\s*"([^"]+)"', ln)
            if m:
                cookie = m.group(1)
        if ln.startswith("#EXTVLCOPT"):
            m = re.search(r'http-user-agent=(.*)', ln, flags=re.IGNORECASE)
            if m:
                ua = m.group(1).strip()

    url_line = src_block[url_idx].strip() if url_idx is not None else None

    if cookie is None and url_line:
        cookie_split = re.split(r'\|[Cc]ookie=', url_line, 1)
        if len(cookie_split) == 2:
            base = cookie_split[0].strip()
            tail = cookie_split[1].strip()
            ua_split = re.split(r'&[Uu]ser-[Aa]gent=', tail, 1)
            cookie = ua_split[0].strip()
            if len(ua_split) > 1:
                ua = ua_split[1].strip()

    transformed_url = url_line
    if cookie and url_line:
        base = re.split(r'\|[Cc]ookie=|\?', url_line, 1)[0].strip()
        transformed_url = f"{base}?{cookie}&xxx=%7Ccookie={cookie}"

    new_block = [
        ln for i, ln in enumerate(src_block)
        if not ln.startswith("#EXTVLCOPT") and not ln.startswith("#EXTHTTP") and i != url_idx
    ]

    if ua:
        new_block.append(f"#EXTVLCOPT:http-user-agent={ua}")
    if cookie:
        new_block.append(f'#EXTHTTP:{{"cookie":"{cookie}"}}')
    if transformed_url:
        new_block.append(transformed_url)

    return new_block


def main():
    print("[LOG] Reading starchannel.txt (Star channels)")
    star_groups = parse_channels_file(CHANNELS_FILE)
    star_channel_to_group = {ch.lower(): grp for grp, chs in star_groups.items() for ch in chs}

    print("[LOG] Fetching Star source M3U…")
    star_source_lines = fetch_source_lines(STAR_SOURCE_URL)
    _, star_source_blocks_list = parse_m3u_blocks(star_source_lines)
    star_source_blocks = {name.lower(): block for name, block in star_source_blocks_list}
    print(f"[LOG] Star source contains {len(star_source_blocks)} channels")

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
        if lname in star_channel_to_group and lname in star_source_blocks:
            new_block = transform_block(star_source_blocks[lname])
            new_block[0] = set_group_title_in_extinf(new_block[0], star_channel_to_group[lname])
            updated_blocks.append((name, new_block))
            updated_channels.add(lname)
            print(f"[LOG] Replaced Star channel: {name}")
        else:
            updated_blocks.append((name, block))

    for ch_lower, group in star_channel_to_group.items():
        if ch_lower not in updated_channels and ch_lower in star_source_blocks:
            new_block = transform_block(star_source_blocks[ch_lower])
            new_block[0] = set_group_title_in_extinf(new_block[0], group)
            name = new_block[0].rpartition(",")[2].strip()
            updated_blocks.append((name, new_block))
            print(f"[LOG] Added Star channel: {name}")

    output_lines = header or ["#EXTM3U"]
    for _, block in updated_blocks:
        output_lines.extend(block)

    with open(MY_PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print(f"[LOG] ✅ Playlist updated with {len(updated_blocks)} channels")


if __name__ == "__main__":
    main()
