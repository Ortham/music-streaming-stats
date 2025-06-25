import csv
import json
import os

def read_json(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def write_json(output_path, data):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent="\t")

def read_spotify_streaming_history(dir_path):
    streams = []
    for file in os.listdir(dir_path):
        filename = os.fsdecode(file)
        if filename.endswith('.json') and '_Audio_' in filename:
            file_path = os.path.join(dir_path, filename)
            streams.extend(read_json(file_path))

    return streams

def read_csv(file_path):
    rows = []
    with open(file_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    return rows
