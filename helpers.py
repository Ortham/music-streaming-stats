import json
import os

import psycopg

def read_json(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def write_json(output_path, data):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent="\t")

def connect_to_postgres(postgres_host, postgres_port, postgres_sslmode, postgres_db, postgres_user, postgres_password):
    return psycopg.connect(f"host={postgres_host} port={postgres_port} sslmode={postgres_sslmode} dbname={postgres_db} user={postgres_user} password={postgres_password}")

def read_spotify_streaming_history(dir_path):
    streams = []
    for file in os.listdir(dir_path):
        filename = os.fsdecode(file)
        if filename.endswith('.json') and '_Audio_' in filename:
            file_path = os.path.join(dir_path, filename)
            streams.extend(read_json(file_path))

    return streams
