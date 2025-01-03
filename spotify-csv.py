#!/usr/bin/env python3

import argparse
import csv
from datetime import datetime, timedelta, timezone
import os

from helpers import write_json, read_spotify_streaming_history

bucket_duration_secs = 3600

def get_tracks(streams):
    tracks_by_uri = {}
    for stream in streams:
        track_uri = stream['spotify_track_uri']
        if track_uri is None:
            # It's probably a podcast episode
            continue

        if track_uri not in tracks_by_uri:
            tracks_by_uri[track_uri] = {
                'track_uri': track_uri,
                'track_name': stream['master_metadata_track_name'],
                'artist_name': stream['master_metadata_album_artist_name'],
                'album_name': stream['master_metadata_album_album_name'],
                'duration_ms': None,
                'play_time_ms': 0,
                'play_count': 0,
                'complete_play_count': 0,
            }

        tracks_by_uri[track_uri]['play_count'] += 1
        tracks_by_uri[track_uri]['play_time_ms'] += stream['ms_played']

        if stream['reason_end'] == 'trackdone':
            tracks_by_uri[track_uri]['complete_play_count'] += 1

            if 'duration_ms' not in tracks_by_uri[track_uri]:
                tracks_by_uri[track_uri]['duration_ms'] = stream['ms_played']

    tracks = list(tracks_by_uri.values())
    tracks.sort(key=lambda t: t['play_count'], reverse=True)

    return tracks_by_uri

def get_albums(tracks_by_uri):
    albums_by_name = {}
    for track in tracks_by_uri.values():
        album_name = track['album_name']
        if album_name not in albums_by_name:
            albums_by_name[album_name] = {
                'album_name': album_name,
                'artist_name': track['artist_name'],
                'tracks_play_count': 0,
                'complete_play_count': 0,
                'play_time_ms': 0,
                'track_uris': set()
            }

        albums_by_name[album_name]['tracks_play_count'] += track['complete_play_count']
        albums_by_name[album_name]['play_time_ms'] += track['play_time_ms']
        albums_by_name[album_name]['track_uris'].add(track['track_uri'])

    # The complete play count is a bit misleading, as it assumes that I've listened to all the tracks in the album at least once.
    for album in albums_by_name.values():
        track_play_counts = [tracks_by_uri[t]['complete_play_count'] for t in album['track_uris']]
        album['complete_play_count'] = min(track_play_counts)

    # This is a heuristic intended to filter out singles and EPs, and albums that haven't had a single complete play of any tracks
    albums = [album for album in albums_by_name.values() if len(album['track_uris']) > 3 and album['tracks_play_count'] > 0]

    albums.sort(key=lambda a: a['tracks_play_count'], reverse=True)

    return albums

def get_artists(tracks_by_uri):
    artists_by_name = {}
    for track in tracks_by_uri.values():
        artist_name = track['artist_name']
        if artist_name not in artists_by_name:
            artists_by_name[artist_name] = {
                'artist_name': artist_name,
                'play_count': 0,
                'complete_play_count': 0,
                'play_time_ms': 0,
                'track_uris': set()
            }

        artists_by_name[artist_name]['play_count'] += track['play_count']
        artists_by_name[artist_name]['complete_play_count'] += track['complete_play_count']
        artists_by_name[artist_name]['play_time_ms'] += track['play_time_ms']
        artists_by_name[artist_name]['track_uris'].add(track['track_uri'])

    artists = list(artists_by_name.values())
    artists.sort(key=lambda a: a['play_count'], reverse=True)

    return artists

def get_day_of_week(timestamp: datetime):
    week_days = {
        1: 'Mon',
        2: 'Tue',
        3: 'Wed',
        4: 'Thu',
        5: 'Fri',
        6: 'Sat',
        7: 'Sun'
    }
    return week_days[timestamp.isoweekday()]

def get_bucket_start_timestamp(timestamp: datetime):
    return datetime.fromtimestamp((timestamp.timestamp() // bucket_duration_secs) * bucket_duration_secs, tz=timezone.utc)

def get_hour_bucket_key(timestamp: datetime):
    return get_bucket_start_timestamp(timestamp).isoformat()

def get_hour_of_week_bucket_key(timestamp: datetime):
    day_of_week = get_day_of_week(timestamp)

    return f'{timestamp.isoweekday()} {day_of_week} {timestamp.hour:02}:00'

def get_buckets(streams, get_bucket_key):
    streams.sort(key=lambda s: s['ts'])

    buckets_by_key = {}
    for stream in streams:
        if stream['spotify_track_uri'] is None:
            # It's probably a podcast episode
            continue

        # The timestamp is when the track stopped playing, but it may have been playing across multiple buckets, and should be partially recorded against each relevant bucket to avoid over-representing playtime in any one bucket.
        end_timestamp = datetime.fromisoformat(stream['ts'])
        start_timestamp = end_timestamp - timedelta(milliseconds=stream['ms_played'])

        keys = {}
        current_ts = start_timestamp
        key = get_bucket_key(current_ts)
        end_key = get_bucket_key(end_timestamp)
        while key != end_key:
            bucket_time_remaining = timedelta(seconds=bucket_duration_secs) - (current_ts - get_bucket_start_timestamp(current_ts))

            keys[key] = bucket_time_remaining / timedelta(milliseconds=1)

            current_ts += bucket_time_remaining
            key = get_bucket_key(current_ts)

        keys[key] = (end_timestamp - current_ts) / timedelta(milliseconds=1)

        for (key, bucket_play_time_ms) in keys.items():
            if key not in buckets_by_key:
                buckets_by_key[key] = {
                    'bucket_start': key,
                    'play_time_ms': 0,
                    'streams': []
                }

            buckets_by_key[key]['play_time_ms'] += bucket_play_time_ms

            buckets_by_key[key]['streams'].append(stream)
            buckets_by_key[key]['streams'][-1]['start_ts'] = start_timestamp.isoformat()

    buckets = list(buckets_by_key.values())
    buckets.sort(key=lambda b: b['play_time_ms'], reverse=True)

    if get_bucket_key == get_hour_bucket_key:
        # Some buckets may overflow due to bad timestamps and/or playtimes. There can be many tracks with the same end timestamp (and which were played for at least one second), and even when they're not the same, the end time of one stream may be after the (end time - play duration) of the next.
        # Identical timestamps seem to often (always?) be offline = true, but the offline_timestamp field is not reliable (some streams have it set to times in 1970).
        # This block checks that all the overflowed time is accounted for by overlaps between consecutive streams.
        bucket_duration_ms = bucket_duration_secs * 1000
        for bucket in buckets:
            if bucket['play_time_ms'] <= bucket_duration_ms:
                continue

            overlap = timedelta(milliseconds=0)
            for i in reversed(range(1, len(bucket['streams']))):
                start_ts = datetime.fromisoformat(bucket['streams'][i]['start_ts'])
                previous_end_ts = datetime.fromisoformat(bucket['streams'][i - 1]['ts'])


                if previous_end_ts > start_ts:
                    overlap += previous_end_ts - start_ts

            overflow_due_to_overlap = bucket_duration_ms + (overlap / timedelta(milliseconds=1))
            unexplained_overflow = bucket['play_time_ms'] - overflow_due_to_overlap
            if unexplained_overflow > 0:
                print(f'The bucket {bucket['bucket_start']} overflows by more than the overlap between streams, leaving {unexplained_overflow} ms unexplained')

    return buckets

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

def write_csv(output_path, rows):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(next(iter(rows)).keys()))

        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def write_albums_csv(output_path, albums):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['album_name','artist_name', 'tracks_play_count', 'complete_play_count', 'play_time_ms']
        writer = csv.DictWriter(csv_file, fieldnames=field_names, extrasaction='ignore')

        writer.writeheader()
        for album in albums:
            writer.writerow(album)

def write_artists_csv(output_path, artists):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['artist_name', 'play_count', 'complete_play_count', 'play_time_ms']
        writer = csv.DictWriter(csv_file, fieldnames=field_names, extrasaction='ignore')

        writer.writeheader()
        for artist in artists:
            writer.writerow(artist)

def write_buckets_csv(output_path, buckets):
    with open(output_path, 'w', newline='', encoding='utf-8') as csv_file:
        field_names = ['bucket_start', 'play_time_ms']
        writer = csv.DictWriter(csv_file, fieldnames=field_names, extrasaction='ignore')

        writer.writeheader()
        for bucket in buckets:
            writer.writerow(bucket)

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a directory of JSON files containing your Spotify extended streaming history.')
    parser.add_argument('--output-path')
    parser.add_argument('-b', '--bucket-type', choices=['hour', 'hour-of-week'], default='hour')
    parser.add_argument('input_dir_path')
    args = parser.parse_args()

    streams = read_spotify_streaming_history(args.input_dir_path)

    tracks_by_uri = get_tracks(streams)

    albums = get_albums(tracks_by_uri)
    artists = get_artists(tracks_by_uri)

    get_bucket_key = get_hour_of_week_bucket_key if args.bucket_type == 'hour-of-week' else get_hour_bucket_key
    buckets = get_buckets(streams, get_bucket_key)

    stats = collect_stats(streams, len(tracks_by_uri))
    ip_addrs = get_ip_addrs(stats)
    platforms = get_platforms(stats)

    write_json(os.path.join(args.output_path, 'spotify_streams.json'), streams)

    write_json(os.path.join(args.output_path, 'spotify_stats.json'), stats)

    write_csv(os.path.join(args.output_path, 'spotify_ip_addrs.csv'), ip_addrs)

    write_csv(os.path.join(args.output_path, 'spotify_platforms.csv'), platforms)

    write_csv(os.path.join(args.output_path, 'spotify_tracks.csv'), tracks_by_uri.values())

    write_albums_csv(os.path.join(args.output_path, 'spotify_albums.csv'), albums)

    write_artists_csv(os.path.join(args.output_path, 'spotify_artists.csv'), artists)

    write_buckets_csv(os.path.join(args.output_path, 'spotify_times.csv'), buckets)

if __name__ == "__main__":
    main()
