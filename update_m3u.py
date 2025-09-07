#!/usr/bin/env python3
import re
import requests

MY_PLAYLIST = "my_playlist.m3u"
CHANNELS_FILE = "channels.txt"
SOURCE_URL = "https://raw.githubusercontent.com/alex4528/m3u/main/jstar.m3u"

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

def main():
    groups = parse_channels_file(CHANNELS_FILE)
    channel_to_group = {ch.lower(): grp for grp, chs in groups.items() for ch in chs}

    source_lines = fetch_source_lines(SOURCE_URL)
    _, source_blocks_list = parse_m3u_blocks(source_lines)
    source_blocks = {name.lower(): block for name, block in source_blocks_list}

    try:
        with open(MY_PLAYLIST, "r", encoding="utf-8") as f:
            my_lines = f.read().splitlines()
    except FileNotFoundError:
        my_lines = ["#EXTM3U"]

    header, my_blocks = parse_m3u_blocks(my_lines)

    updated_blocks = []
    updated_channels = set()

    # ✅ Update in place
    for name, block in my_blocks:
        lname = name.lower()
        if lname in channel_to_group and lname in source_blocks:
            new_block = list(source_blocks[lname])
            desired_group = channel_to_group[lname]
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            updated_blocks.append((name, new_block))
            updated_channels.add(lname)
            print(f"Updated: {name}")
        else:
            updated_blocks.append((name, block))

    # ✅ Append only missing ones
    for ch_lower, desired_group in channel_to_group.items():
        if ch_lower not in updated_channels and ch_lower in source_blocks:
            new_block = list(source_blocks[ch_lower])
            new_block[0] = set_group_title_in_extinf(new_block[0], desired_group)
            display_name = new_block[0].rpartition(",")[2].strip()
            updated_blocks.append((display_name, new_block))
            print(f"Added missing channel: {display_name}")

    output_lines = header or ["#EXTM3U"]
    for _, block in updated_blocks:
        output_lines.extend(block)

    with open(MY_PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print("✅ Done")

if __name__ == "__main__":
    main()
