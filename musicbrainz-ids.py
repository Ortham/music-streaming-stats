#!/usr/bin/env python3

import argparse
import json

import psycopg
from datetime import datetime

def read_json(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def write_json(output_path, data):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent="\t")

def connect_to_postgres(postgres_host, postgres_port, postgres_sslmode, postgres_db, postgres_user, postgres_password):
    return psycopg.connect(f"host={postgres_host} port={postgres_port} sslmode={postgres_sslmode} dbname={postgres_db} user={postgres_user} password={postgres_password}")

def get_musicbrainz_recording_ids(postgres_connection, track):
    isrc = track['external_ids']['isrc'] if 'isrc' in track['external_ids'] else None
    spotify_track_name = track['name'].lower()

    for artist in track['artists']:
        spotify_artist_name = artist['name'].lower()

        with postgres_connection.cursor() as cur:
            cur.execute("""
                        select gid from recording r
                            left join isrc i on i.recording = r.id
                            join artist_credit_name acn on r.artist_credit = acn.artist_credit
                            where (isrc is not null and isrc = %s) or (lower(r.name) = %s and lower(acn.name) = %s)
                        """, (isrc, spotify_track_name, spotify_artist_name))
            rows = cur.fetchall()

            if rows:
                return [str(row[0]) for row in rows]

    return []

def match_track(recording, track):
    if recording[0]:
        isrc = track['external_ids']['isrc'] if 'isrc' in track['external_ids'] else None
        if isrc == recording[0]:
            return True

    if track['name'] != recording[2]:
        return False

    for artist in track['artists']:
        if artist['name'] == recording[3]:
            return True

    return False

def match_tracks(recordings, tracks):
    for recording in recordings:
        recording[2] = recording[2].lower()
        recording[3] = recording[3].lower()

    tracks = [t for t in tracks if t['name']]

    for track in tracks:
        track['name'] = track['name'].lower()

        for artist in track['artists']:
            artist['name'] = artist['name'].lower()

        track['artists'] = [a for a in track['artists'] if a['name']]

    start = datetime.now()

    matches = []
    for recording in recordings:
        for track in tracks:
            if match_track(recording, track):
                matches.append([track['uri'], recording[1]])

    print('Elapsed time', datetime.now() - start)
    print(f'Found {len(matches)} matches')

    return matches

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--spotify-tracks-metadata-path')
    parser.add_argument('--recordings-path')
    parser.add_argument('--output-path')
    parser.add_argument('--postgresql', action='store_const', const=True)
    parser.add_argument('--postgresql-host', default='localhost')
    parser.add_argument('--postgresql-port', default='6543')
    parser.add_argument('--postgresql-sslmode', default='disable')
    parser.add_argument('--postgresql-db', default='musicbrainz_db')
    parser.add_argument('--postgresql-user', default='musicbrainz')
    parser.add_argument('--postgresql-password', default='musicbrainz')
    args = parser.parse_args()

    tracks_metadata = read_json(args.spotify_tracks_metadata_path)
    print('Tracks', len(tracks_metadata))

    count = 0
    for track in tracks_metadata:
        if 'isrc' in track['external_ids']:
            count += 1
    print('Tracks with ISRCs', count)

    recording_ids_by_uri = {}
    unmapped_track_uris = []

    if args.recordings_path:
        print('Loading recordings...')
        recordings = read_json(args.recordings_path)

        matches = match_tracks(recordings, tracks_metadata)
        for [uri, id] in matches:
            if uri in recording_ids_by_uri:
                recording_ids_by_uri[uri].append(id)
            else:
                recording_ids_by_uri[uri] = [id]
    else:
        postgres_connection = connect_to_postgres(args.postgresql_host,
                                                    args.postgresql_port,
                                                    args.postgresql_sslmode,
                                                    args.postgresql_db,
                                                    args.postgresql_user,
                                                    args.postgresql_password)

        with postgres_connection:
            start = datetime.now()

            for track in tracks_metadata:
                uri = track['uri']
                recording_ids = get_musicbrainz_recording_ids(postgres_connection, track)

                if recording_ids:
                    recording_ids_by_uri[uri] = recording_ids
                else:
                    unmapped_track_uris.append(uri)

            print('Elapsed time', datetime.now() - start)

    print('Mapped tracks', len(recording_ids_by_uri))
    print('Unmapped tracks', len(unmapped_track_uris))

    if args.output_path:
        content = {
            'mbids_by_spotify_uri': recording_ids_by_uri,
            'unmapped_track_uris': list(unmapped_track_uris)
        }

        write_json(args.output_path, content)

if __name__ == "__main__":
    main()
