#!/usr/bin/env python3

import argparse

from helpers import read_json, write_json

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
