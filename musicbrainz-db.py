#!/usr/bin/env python3

import argparse
import json

import psycopg

max_recordings_per_request = 25
musicbrainz_rate_limit_rps = 1

def read_json(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def write_json(output_path, data):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent="\t")

def connect_to_postgres(postgres_host, postgres_port, postgres_sslmode, postgres_db, postgres_user, postgres_password):
    return psycopg.connect(f"host={postgres_host} port={postgres_port} sslmode={postgres_sslmode} dbname={postgres_db} user={postgres_user} password={postgres_password}")

def get_musicbrainz_recording_ids(postgres_connection, isrc):
    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select gid from recording r join isrc i on i.recording = r.id where isrc = %s
                    """, (isrc, ))
        rows = cur.fetchall()

        return [str(row[0]) for row in rows]

def get_all_musicbrainz_recording_ids(postgres_connection):
    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select isrc, gid from recording r join isrc i on i.recording = r.id
                    """)
        rows = cur.fetchall()

        return [(row[0], str(row[1])) for row in rows]

def get_recording_tags(postgres_connection, musicbrainz_recording_id):
    # Not all tags are genres that are recognised by MusicBrainz, this includes
    # the genre ID if there is one.
    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select tag.name, rt.count, genre.gid as genre_id
                        from recording r
                        join recording_tag rt on r.id = rt.recording
                        join tag on rt.tag = tag.id
                        left join genre on genre.name = tag.name
                        where r.gid = %s
                    """, (musicbrainz_recording_id, ))
        rows = cur.fetchall()

        return rows

def get_recording_genres(postgres_connection, musicbrainz_recording_id):
    # Not all tags are genres that are recognised by MusicBrainz, this only
    # returns tags that are genres
    with postgres_connection.cursor() as cur:
        cur.execute("""
                    select tag.name, rt.count, genre.gid as genre_id
                        from recording r
                        join recording_tag rt on r.id = rt.recording
                        join tag on rt.tag = tag.id
                        join genre on genre.name = tag.name
                        where r.gid = %s
                    """, (musicbrainz_recording_id, ))
        rows = cur.fetchall()

        return rows

def main():
    parser = argparse.ArgumentParser(description='Supply the path to a JSON file containing $[*].external_ids.isrc fields.')
    parser.add_argument('--isrcs-json-path')
    parser.add_argument('--output-path')
    parser.add_argument('--dump-all-recording-ids', action='store_const', const=True)
    parser.add_argument('--get-all-tags', action='store_const', const=True)
    parser.add_argument('--postgresql', action='store_const', const=True)
    parser.add_argument('--postgresql-host', default='localhost')
    parser.add_argument('--postgresql-port', default='6543')
    parser.add_argument('--postgresql-sslmode', default='disable')
    parser.add_argument('--postgresql-db', default='musicbrainz_db')
    parser.add_argument('--postgresql-user', default='musicbrainz')
    parser.add_argument('--postgresql-password', default='musicbrainz')
    args = parser.parse_args()

    tracks_metadata = read_json(args.isrcs_json_path)

    isrcs = set(t['external_ids']['isrc'] for t in tracks_metadata if 'isrc' in t['external_ids'])
    count = 0
    for track in tracks_metadata:
        if 'isrc' in track['external_ids']:
            count += 1

    print('Tracks', len(tracks_metadata))
    print('Tracks with ISRCs', count)
    print('ISRCs', len(isrcs))

    postgres_connection = connect_to_postgres(args.postgresql_host,
                                                args.postgresql_port,
                                                args.postgresql_sslmode,
                                                args.postgresql_db,
                                                args.postgresql_user,
                                                args.postgresql_password)

    if args.dump_all_recording_ids and args.output_path:
        data = get_all_musicbrainz_recording_ids(postgres_connection)
        write_json(args.output_path, data)
        exit(0)

    recording_ids_by_isrc = {}
    recording_id_count = 0
    recording_id_set = set()
    recording_genres = {}
    with postgres_connection:
        for isrc in isrcs:
            recording_ids = get_musicbrainz_recording_ids(postgres_connection, isrc)
            if len(recording_ids) > 0:
                recording_id_count += len(recording_ids)
                recording_ids_by_isrc[isrc] = recording_ids
                for id in recording_ids:
                    recording_id_set.add(id)

        print('Recording IDs from ISRCs', recording_id_count)
        print('Unique recording IDs from ISRCs', len(recording_id_set))
        print('Mapped ISRCs', len(recording_ids_by_isrc))

        for recording_id in recording_id_set:
            if args.get_all_tags:
                genres = get_recording_genres(postgres_connection, recording_id)
            else:
                genres = get_recording_tags(postgres_connection, recording_id)
            genres = [{'name': genre[0], 'tag_count': genre[1], 'genre_id': str(genre[2])} for genre in genres]

            if genres:
                recording_genres[recording_id] = genres

    if args.output_path:
        content = {
            'mbids_by_isrc': recording_ids_by_isrc,
            'genres_by_mbid': recording_genres
        }

        write_json(args.output_path, content)

if __name__ == "__main__":
    main()
