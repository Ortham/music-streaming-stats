#!/usr/bin/env python3

import argparse
import json

def read_json(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def write_json(output_path, data):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent="\t")


def main():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--input-1-path')
    parser.add_argument('--input-2-path')
    parser.add_argument('--output-path')
    args = parser.parse_args()

    input_1 = read_json(args.input_1_path)
    input_2 = read_json(args.input_2_path)

    output = input_1 | input_2

    write_json(args.output_path, output)

if __name__ == "__main__":
    main()
