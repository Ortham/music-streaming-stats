#!/usr/bin/env python3

import argparse

import acoustid

from helpers import read_json, write_json

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--acoustid-fingerprints-path')
    parser.add_argument('--acoustid-api-key')
    parser.add_argument('--output-path')
    args = parser.parse_args()

    fingerprints = read_json(args.acoustid_fingerprints_path)
    fingerprints = fingerprints['results']
    print(f'Found {len(fingerprints)} AcoustID fingerprints')

    output = {
        'matches': [],
        'unmatched_paths': []
    }
    already_processed_paths = set()
    try:
        output = read_json(args.output_path)

        for match in output['matches']:
            already_processed_paths.add(match['file_path'])

        for path in output['unmatched_paths']:
            already_processed_paths.add(path)
    except Exception as e:
        print(f'Could not read file at {args.output_path}, will fetch AcoustID matches for all audio files.')
        pass

    for entry in fingerprints:
        file_path = entry['file_path']
        if file_path in already_processed_paths:
            continue

        print(f'Attempting to match "{file_path}"...')
        found_match = False
        try:
            fingerprint = bytes.fromhex(entry['fingerprint'])
            response = acoustid.lookup(args.acoustid_api_key, fingerprint, entry['duration'])
            results = acoustid.parse_lookup_result(response)

            for score, recording_id, title, artist in results:
                found_match = True
                output['matches'].append({
                    'file_path': file_path,
                    'score': score,
                    'recording_id': recording_id,
                    'title': title,
                    'artist': artist
                })
        except Exception as e:
            print('Failed to match by AcoustID fingerprint', e)

        if not found_match:
            print('No match found!')
            output['unmatched_paths'].append(file_path)

    write_json(args.output_path, output)

    matched_file_count = len(fingerprints) - len(output['unmatched_paths'])
    print(f'Found {len(output['matches'])} matches for {matched_file_count} files')

if __name__ == "__main__":
    main()
