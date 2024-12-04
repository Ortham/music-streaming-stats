#!/usr/bin/env python3

import argparse
import csv
import os
import pprint

def parse_input_csv(dir_path):
    tracks = []
    for file in os.listdir(dir_path):
        filename = os.fsdecode(file)
        if filename.endswith('.csv'):
            file_path = os.path.join(dir_path, filename)
            with open(file_path, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tracks.append(row)

    return tracks

def collect_stats(tracks):
    return {
        'tracks_count': len(tracks),
        'plays_count': sum(int(t['Play Count']) for t in tracks),
        'plays_time_ms': sum(int(t['Duration (ms)']) for t in tracks)
    }


def write_csv(output_path, tracks):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['Title','Album', 'Artist', 'Duration (ms)', 'Rating', 'Play Count', 'Removed']
        writer = csv.DictWriter(csv_file, fieldnames=field_names)

        writer.writeheader()
        for track in tracks:
            writer.writerow(track)

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a directory of CSV files containing your Google Play Music tracks.')
    parser.add_argument('input_path')
    parser.add_argument('csv_output_path')
    args = parser.parse_args()

    tracks = parse_input_csv(args.input_path)

    stats = collect_stats(tracks)

    pprint.pp(stats)

    write_csv(args.csv_output_path, tracks, None)

if __name__ == "__main__":
    main()
