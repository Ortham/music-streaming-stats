#!/usr/bin/env python3

import argparse
import csv
import os

from helpers import read_json

def parse_input_csv(file_path):
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

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--mp3tag-lookup-export-path')
    parser.add_argument('--acoustid-matches-path')
    parser.add_argument('--acoustid-matches-base-path')
    args = parser.parse_args()

    rows = parse_input_csv(args.mp3tag_lookup_export_path)
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

    for lookup_entry in lookup_data.values():
        mbid = lookup_entry['MBID']
        rel_path = lookup_entry['relative_path']

        if mbid:
            if rel_path not in matched_relative_paths and rel_path not in unmatched_relative_paths:
                print(f'Cannot find {mbid} for {rel_path} in matched MBIDs or unmatched paths')
            elif rel_path not in matched_relative_paths and rel_path:
                print(f'Cannot find {mbid} for {rel_path} in matched MBIDs')

            if rel_path in matched_relative_paths:
                if mbid not in [m['recording_id'] for m in matched_relative_paths[rel_path]]:
                    print(f'The AcoustID matches for {rel_path} do not include {mbid}')

    print(f'Processed {len(lookup_data)} tracks')

if __name__ == "__main__":
    main()
