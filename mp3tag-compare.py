#!/usr/bin/env python3

import argparse
import csv
import os

from helpers import read_json

def parse_input_tsv(file_path):
    tracks = []
    with open(file_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            tracks.append(row)

    return tracks

def process_rows(rows, file_path):
    root_path = os.path.dirname(file_path)
    data_by_relative_path = {}

    for row in rows:
        if not row['Path']:
            continue

        row['relative_path'] = os.path.relpath(row['Path'], start=root_path)
        data_by_relative_path[row['relative_path']] = row

    return data_by_relative_path

def get_lookup_only_tags(mbid, matches, musicbrainz_tags):
    if mbid in musicbrainz_tags:
        lookup_tags = set(g['name'] for g in musicbrainz_tags[mbid])
    else:
        lookup_tags = set()

    acoustid_tags = set(g['name'] for m in matches if m['recording_id'] in musicbrainz_tags for g in musicbrainz_tags[m['recording_id']])

    return lookup_tags - acoustid_tags

def matches_have_acoustic_metadata(matches, acousticbrainz_metadata):
    for match in matches:
        if match['recording_id'] in acousticbrainz_metadata:
            return True

    return False

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--mp3tag-lookup-export-path')
    parser.add_argument('--acoustid-matches-path')
    parser.add_argument('--acoustid-matches-base-path')
    parser.add_argument('--musicbrainz-tags-path')
    parser.add_argument('--acousticbrainz-path')
    args = parser.parse_args()

    rows = parse_input_tsv(args.mp3tag_lookup_export_path)
    lookup_data = process_rows(rows, args.mp3tag_lookup_export_path)

    match_data = read_json(args.acoustid_matches_path)
    matched_relative_paths = {}
    for match in match_data['matches']:
        rel_path = os.path.relpath(match['file_path'], start=args.acoustid_matches_base_path)
        if rel_path in matched_relative_paths:
            matched_relative_paths[rel_path].append(match)
        else:
            matched_relative_paths[rel_path] = [match]

    unmatched_relative_paths = set(os.path.relpath(p, start=args.acoustid_matches_base_path) for p in match_data['unmatched_paths'])

    musicbrainz_tags = read_json(args.musicbrainz_tags_path)
    acousticbrainz = read_json(args.acousticbrainz_path)

    for lookup_entry in lookup_data.values():
        mbid = lookup_entry['MBID']
        rel_path = lookup_entry['relative_path']

        if mbid:
            if rel_path in matched_relative_paths:
                matches = matched_relative_paths[rel_path]
                if mbid not in [m['recording_id'] for m in matches]:
                    print(f'The AcoustID matches for {rel_path} do not include {mbid}')

                    lookup_only_tags = get_lookup_only_tags(mbid, matches, musicbrainz_tags)
                    if lookup_only_tags:
                        print('The missing MBID leads to the following missing tags', lookup_only_tags)

                    if mbid in acousticbrainz and not matches_have_acoustic_metadata(matches, acousticbrainz):
                        print('The missing MBID leads to missing acoustic metadata')

            elif rel_path in unmatched_relative_paths:
                print(f'Cannot find {mbid} for {rel_path} in matched MBIDs')
            else:
                print(f'Cannot find {mbid} for {rel_path} in matched MBIDs or unmatched paths')

    print(f'Processed {len(lookup_data)} tracks')

if __name__ == "__main__":
    main()
