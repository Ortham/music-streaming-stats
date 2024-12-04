#!/usr/bin/env python3

import argparse
import csv
import json
import os
import pprint

def parse_input_json(dir_path):
    streams = []
    for file in os.listdir(dir_path):
        filename = os.fsdecode(file)
        if filename.endswith('.json') and '_Audio_' in filename:
            file_path = os.path.join(dir_path, filename)
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
                streams.extend(data)

    return streams

def get_tracks(streams):
    tracks_by_id = {}
    for stream in streams:
        track_id = stream['spotify_track_uri']
        if track_id is None:
            # It's probably a podcast episode
            continue

        if track_id not in tracks_by_id:
            tracks_by_id[track_id] = {
                'track_id': track_id,
                'track_name': stream['master_metadata_track_name'],
                'artist_name': stream['master_metadata_album_artist_name'],
                'album_name': stream['master_metadata_album_album_name'],
                'duration_ms': 0,
                'play_time_ms': 0,
                'play_count': 0,
                'complete_play_count': 0,
            }

        tracks_by_id[track_id]['play_count'] += 1
        tracks_by_id[track_id]['play_time_ms'] += stream['ms_played']

        if stream['reason_end'] == 'trackdone':
            tracks_by_id[track_id]['complete_play_count'] += 1

            if tracks_by_id[track_id]['duration_ms'] == 0:
                tracks_by_id[track_id]['duration_ms'] = stream['ms_played']

    tracks = list(tracks_by_id.values())
    tracks.sort(key=lambda t: t['play_count'], reverse=True)

    return tracks_by_id

def get_albums(tracks_by_id):
    albums_by_name = {}
    for track in tracks_by_id.values():
        album_name = track['album_name']
        if album_name not in albums_by_name:
            albums_by_name[album_name] = {
                'album_name': album_name,
                'artist_name': track['artist_name'],
                'tracks_play_count': 0,
                'complete_play_count': 0,
                'track_ids': set()
            }

        albums_by_name[album_name]['tracks_play_count'] += track['complete_play_count']
        albums_by_name[album_name]['track_ids'].add(track['track_id'])

    # The complete play count is a bit misleading, as it assumes that I've listened to all the tracks in the album at least once.
    for album in albums_by_name.values():
        track_play_counts = [tracks_by_id[t]['complete_play_count'] for t in album['track_ids']]
        album['complete_play_count'] = min(track_play_counts)

    # This is a heuristic intended to filter out singles and EPs, and albums that haven't had a single complete play of any tracks
    albums = [album for album in albums_by_name.values() if len(album['track_ids']) > 3 and album['tracks_play_count'] > 0]

    albums.sort(key=lambda a: a['tracks_play_count'], reverse=True)

    return albums

def increment_count(counters, key):
    if key not in counters:
        counters[key] = 0
    counters[key] += 1

def collect_stats(streams, tracks_count):
    start_reason_counts = {}
    end_reason_counts = {}
    platform_counts = {}
    country_counts = {}
    ip_addr_counts = {}
    skipped_count = 0
    complete_play_count = 0
    play_time_ms = 0

    for stream in streams:
        increment_count(start_reason_counts, stream['reason_start'])
        increment_count(end_reason_counts, stream['reason_end'])
        increment_count(platform_counts, stream['platform'])
        increment_count(country_counts, stream['conn_country'])
        increment_count(ip_addr_counts, stream['ip_addr'])

        if stream['skipped']:
            skipped_count += 1
        if stream['reason_end'] == 'trackdone':
            complete_play_count += 1

        play_time_ms += stream["ms_played"]

    return {
        'tracks_count': tracks_count,
        'plays_count': len(streams),
        'plays_time_ms': play_time_ms,
        'skipped_count': skipped_count,
        'complete_play_count': complete_play_count,
        'start_reason_counts': start_reason_counts,
        'end_reason_counts': end_reason_counts,
        'platform_counts': platform_counts,
        'country_counts': country_counts,
        'ip_addr_counts': ip_addr_counts
    }

def get_ip_addrs(stats):
    ip_addrs = [{'ip_addr': k, 'play_count': v} for (k, v) in stats['ip_addr_counts'].items()]
    ip_addrs.sort(key=lambda i: i['play_count'], reverse=True)

    return ip_addrs

def get_platforms(stats):
    platforms = [{'platform': k, 'play_count': v} for (k, v) in stats['platform_counts'].items()]
    platforms.sort(key=lambda p: p['play_count'], reverse=True)

    return platforms

def write_stats_json(output_path, stats):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent="\t")

def write_csv(output_path, rows):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(next(iter(rows)).keys()))

        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def write_albums_csv(output_path, albums):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['album_name','artist_name', 'tracks_play_count', 'complete_play_count']
        writer = csv.DictWriter(csv_file, fieldnames=field_names, extrasaction='ignore')

        writer.writeheader()
        for album in albums:
            writer.writerow(album)

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a directory of JSON files containing your Spotify extended streaming history.')
    parser.add_argument('input_dir_path')
    parser.add_argument('output_dir_path')
    args = parser.parse_args()

    streams = parse_input_json(args.input_dir_path)

    tracks_by_id = get_tracks(streams)

    albums = get_albums(tracks_by_id)

    stats = collect_stats(streams, len(tracks_by_id))
    ip_addrs = get_ip_addrs(stats)
    platforms = get_platforms(stats)

    write_stats_json(os.path.join(args.output_dir_path, 'spotify_stats.json'), stats)

    write_csv(os.path.join(args.output_dir_path, 'spotify_ip_addrs.csv'), ip_addrs)

    write_csv(os.path.join(args.output_dir_path, 'spotify_platforms.csv'), platforms)

    write_csv(os.path.join(args.output_dir_path, 'spotify_tracks.csv'), tracks_by_id.values())

    write_albums_csv(os.path.join(args.output_dir_path, 'spotify_albums.csv'), albums)

if __name__ == "__main__":
    main()
