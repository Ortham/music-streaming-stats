#!/usr/bin/env python3

import argparse
import os

import acoustid

from helpers import read_json, write_json

audio_file_extensions = ['.mp3', '.flac', '.wav', '.m4a']
other_file_extensions = ['.jpg', '.png', '.txt', '.pdf', '.log', '.rtf', '.exe', '.url', '.DS_Store']

def ends_with_one_of(string, candidates):
    for candidate in candidates:
        if string.endswith(candidate):
            return True

    return False

def extended_length_path(dos_path):
    abs_path = os.path.abspath(dos_path)
    if abs_path.startswith(u"\\\\"):
        return u"\\\\?\\UNC\\" + abs_path[2:]

    return u"\\\\?\\" + abs_path

def find_audio_files(root_path):
    audio_file_paths = []
    for root, dirs, files in os.walk(root_path):
        for file in files:
            if ends_with_one_of(file, audio_file_extensions):
                audio_file_paths.append(os.path.join(root, file))
            elif not ends_with_one_of(file, other_file_extensions):
                print('Unexpected file extension:', os.path.join(root, file))

    return audio_file_paths

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--music-library-path')
    parser.add_argument('--acoustid-api-key')
    parser.add_argument('--output-path')
    args = parser.parse_args()

    file_paths = find_audio_files(args.music_library_path)
    print(f'Found {len(file_paths)} audio files')

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

    for file_path in file_paths:
        if file_path in already_processed_paths:
            continue

        print(f'Attempting to match "{file_path}"...')
        found_match = False
        try:
            results = acoustid.match(args.acoustid_api_key, file_path)

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

    matched_file_count = len(file_paths) - len(output['unmatched_paths'])
    print(f'Found {len(output['matches'])} matches for {matched_file_count} files')

if __name__ == "__main__":
    main()
