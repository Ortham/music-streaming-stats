#!/usr/bin/env python3

import argparse
import csv
import os

from pprint import pp

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
    parser.add_argument('--mp3tag-scan-export-path')
    args = parser.parse_args()

    rows = parse_input_csv(args.mp3tag_lookup_export_path)
    lookup_data = process_rows(rows, args.mp3tag_lookup_export_path)

    rows = parse_input_csv(args.mp3tag_scan_export_path)
    scan_data = process_rows(rows, args.mp3tag_scan_export_path)

    mismatched_isrc_keys = []
    mismatched_mbid_keys = []

    for key in lookup_data:
        lookup_entry = lookup_data[key]
        scan_entry = scan_data[key]

        if lookup_entry['MBID'] != scan_entry['MBID']:
            mismatched_mbid_keys.append(key)

        if lookup_entry['ISRC'] != scan_entry['ISRC']:
            mismatched_isrc_keys.append(key)


    print(f'Processed {len(lookup_data)} tracks')
    print('The following keys had different lookup and scan ISRCs:')
    pp(mismatched_isrc_keys)
    print('The following keys had different lookup and scan MBIDs:')
    pp(mismatched_mbid_keys)

if __name__ == "__main__":
    main()
