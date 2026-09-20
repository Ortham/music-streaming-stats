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

def process_rows(tracks, file_path):
    root_path = os.path.dirname(file_path)
    data_by_relative_path = {}

    for track in tracks:
        track['relative_path'] = os.path.relpath(track['file_path'], start=root_path)
        data_by_relative_path[track['relative_path']] = track

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
    parser.add_argument('--extracted-metadata-path')
    parser.add_argument('--acoustid-matches-path')
    parser.add_argument('--acoustid-matches-base-path')
    parser.add_argument('--musicbrainz-ids-path')
    parser.add_argument('--musicbrainz-tags-path')
    parser.add_argument('--acousticbrainz-path')
    args = parser.parse_args()

    tracks = read_json(args.extracted_metadata_path)
    lookup_data = process_rows(tracks, args.extracted_metadata_path)

    match_data = read_json(args.acoustid_matches_path)
    matched_relative_paths = {}
    for match in match_data['matches']:
        rel_path = os.path.relpath(match['file_path'], start=args.acoustid_matches_base_path)
        if rel_path in matched_relative_paths:
            matched_relative_paths[rel_path].append(match)
        else:
            matched_relative_paths[rel_path] = [match]

    unmatched_relative_paths = set(os.path.relpath(p, start=args.acoustid_matches_base_path) for p in match_data['unmatched_paths'])

    musicbrainz_ids = read_json(args.musicbrainz_ids_path)
    musicbrainz_tags = read_json(args.musicbrainz_tags_path)
    acousticbrainz = read_json(args.acousticbrainz_path)

    musicbrainz_ids = set(m for u in musicbrainz_ids['mbids_by_spotify_uri'] for m in u)

    mbids_with_missing_matches = set()
    mbids_with_missing_tags = set()
    mbids_with_missing_acoustic_metadata = set()
    mbids_for_unmatched_files = set()
    mbids_for_unprocessed_files = set()

    for lookup_entry in lookup_data.values():
        tags = {k.upper(): v for k, v in lookup_entry['tags'].items()}
        mbid = tags.get('MUSICBRAINZ_TRACKID')
        rel_path = lookup_entry['relative_path']

        if mbid:
            if rel_path in matched_relative_paths:
                matches = matched_relative_paths[rel_path]
                if mbid not in [m['recording_id'] for m in matches]:
                    print(f'The AcoustID matches for {rel_path} do not include {mbid}')
                    mbids_with_missing_matches.add(mbid)

                    lookup_only_tags = get_lookup_only_tags(mbid, matches, musicbrainz_tags)
                    if lookup_only_tags:
                        print('The missing MBID leads to the following missing tags', lookup_only_tags)
                        mbids_with_missing_tags.add(mbid)

                    if mbid in acousticbrainz and not matches_have_acoustic_metadata(matches, acousticbrainz):
                        print('The missing MBID leads to missing acoustic metadata')
                        mbids_with_missing_acoustic_metadata.add(mbid)

            elif rel_path in unmatched_relative_paths:
                print(f'Cannot find {mbid} for {rel_path} because AcoustID could not match the path')
                mbids_for_unmatched_files.add(mbid)
            elif mbid in musicbrainz_ids:
                print(f'Cannot find {mbid} for {rel_path} because the path was not processed')
                mbids_for_unprocessed_files.add(mbid)

    print(f'Processed {len(lookup_data)} tracks')
    print(f"{len(mbids_with_missing_matches)} files had an MBID found by lookup that wasn't found by AcoustID scan. {len(mbids_with_missing_matches & musicbrainz_ids)} match to Spotify tracks")
    print(f'{len(mbids_with_missing_tags)} files missed out on tags due to a missing MBID. {len(mbids_with_missing_tags & musicbrainz_ids)} match to Spotify tracks')
    print(f'{len(mbids_with_missing_acoustic_metadata)} files missed out on acoustic metadata due to a missing MBID. {len(mbids_with_missing_acoustic_metadata & musicbrainz_ids)} match to Spotify tracks')
    print(f"{len(mbids_for_unmatched_files)} files had an MBID found by lookup but weren't recognised by AcoustID. {len(mbids_for_unmatched_files & musicbrainz_ids)} match to Spotify tracks")
    print(f'{len(mbids_for_unprocessed_files)} files have not been processed by acoustid-match.py. {len(mbids_for_unprocessed_files & musicbrainz_ids)} match to Spotify tracks')

if __name__ == "__main__":
    main()
