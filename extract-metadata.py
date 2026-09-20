#!/usr/bin/env python3
# /// script
# requires-python = ">=3.7"
# dependencies = [
#   "mutagen",
# ]
# ///
#
# This script reads the metadata tags from .flac, .mp3 and .m4a files found in a
# given directory tree and writes a JSON array of objects containing those tags
# along with the relevant file's path, size and audio length to a given file
# path.
#
# FLAC and MP4 tag names are written without any normalisation. If a tag has
# multiple values, the tag's value in the JSON output is an array of those
# values.
#
# The following tags are skipped:
#
# - Cover art
# - Non-UTF-8 freeform MP4 tags
# - Tags that get extracted to null values.
#
# Some other ID3 tags may also get skipped.

import argparse
import json
import os

from mutagen.flac import FLAC
from mutagen.mp3 import EasyMP3
from mutagen.id3 import COMM, WOAS, WXXX
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

def is_instance_or_list_of(value, type_to_check):
    return isinstance(value, type_to_check) or (isinstance(value, list) and len(value) > 0 and isinstance(value[0], type_to_check))

def add_to_dict(tags_dict, key, value):
    if key in tags_dict:
        if isinstance(tags_dict[key], list):
            tags_dict[key].append(value)
        else:
            tags_dict[key] = [tags_dict[key], value]
    else:
        tags_dict[key] = value

def convert_flac_tags(tags):
    tags_dict = {}
    for key, value in tags:
        add_to_dict(tags_dict, key, value)

    return tags_dict

def convert_mp3_tags(tags):
    tags_dict = {}
    for key in tags:
        value = tags[key]
        if isinstance(value, list) and len(value) == 1:
            value = value[0]

        if is_instance_or_list_of(value, COMM):
            if isinstance(value, list):
                value = [c.text if c.text else None for c in value]
            else:
                value = value.text if value.text else None
        elif isinstance(value, WXXX | WOAS):
            value = value.url

        if value == None:
            continue

        add_to_dict(tags_dict, key, value)

    return tags_dict

def convert_mp4_tags(tags):
    tags_dict = {}
    for key in tags:
        value = tags[key]
        if isinstance(value, list) and len(value) == 1:
            value = value[0]

        if is_instance_or_list_of(value, MP4FreeForm):
            if is_instance_or_list_of(value, bytes):
                try:
                    if isinstance(value, list):
                        value = [v.decode('utf8') for v in value]
                    else:
                        value = value.decode('utf8')
                except UnicodeError:
                    print(f'Tag {key} is freeform and not valid UTF-8, skipping: {value}')
                    continue
            else:
                print(f'Tag {key} is freeform and not a byte string, skipping: {value}')
                continue
        elif isinstance(value, MP4Cover):
            print(f'Tag {key} is cover artwork, skipping')
            continue

        add_to_dict(tags_dict, key, value)

    return tags_dict

def process_flac_file(file_path):
    audio = FLAC(file_path)

    return {
        'file_path': file_path,
        'file_size': os.path.getsize(file_path),
        'length': audio.info.length,
        'tags': convert_flac_tags(audio.tags)
    }

def process_mp3_file(file_path):
    audio = EasyMP3(file_path)

    return {
        'file_path': file_path,
        'file_size': os.path.getsize(file_path),
        'length': audio.info.length,
        'tags': convert_mp3_tags(audio.tags)
    }

def process_m4a_file(file_path):
    audio = MP4(file_path)

    return {
        'file_path': file_path,
        'file_size': os.path.getsize(file_path),
        'length': audio.info.length,
        'tags': convert_mp4_tags(audio.tags)
    }


def write_json(output_path, data):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent="\t")

def get_id3_comment(id3, key):
    frames = id3.getall('COMM')
    return frames if frames else None

def get_id3_website(id3, key):
    frames = id3.getall('WXXX')
    return frames if frames else None

def get_id3_wwwaudiosource(id3, key):
    frames = id3.getall('WOAS')
    return frames if frames else None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_directory')
    parser.add_argument('output_path')
    args = parser.parse_args()

    EasyID3.RegisterKey('comment', get_id3_comment)
    EasyID3.RegisterKey('website', get_id3_website)
    EasyID3.RegisterKey('wwwaudiosource', get_id3_wwwaudiosource)
    EasyID3.RegisterTXXXKey('source', 'SOURCE')
    EasyID3.RegisterTXXXKey('source', 'BARCODE')
    EasyID3.RegisterTextKey('publisher', 'TPUB')
    EasyID3.RegisterTextKey('movementname', 'MVNM')
    EasyID3.RegisterTextKey('movement', 'MVIN')

    all_metadata = []
    for root, _, files in os.walk(args.input_directory):
        for f in files:
            if f.lower().endswith('.flac'):
                full_path = os.path.join(root, f)
                print(f"Processing: {full_path}")

                metadata = process_flac_file(full_path)
                all_metadata.append(metadata)

            elif f.lower().endswith('.mp3'):
                full_path = os.path.join(root, f)
                print(f"Processing: {full_path}")

                metadata = process_mp3_file(full_path)
                all_metadata.append(metadata)

            elif f.lower().endswith('.m4a'):
                full_path = os.path.join(root, f)
                print(f"Processing: {full_path}")

                metadata = process_m4a_file(full_path)
                all_metadata.append(metadata)


    write_json(args.output_path, all_metadata)

if __name__ == "__main__":
    main()
