# ALM map parser

This is a map parser, written in (poor) Python.

## Features

1. Read a map from an `.alm` file;
2. Display most relevant information in a human-readable text format;
3. Optionally save the map in machine-readable JSON format with `--output_format=json`;
4. Load a saved JSON file and re-save it in `.alm` --- `--save`.

Note that you need a compliant game client installed. Some data (monster types,
spell names, ...) for human-readable format is gathered by parsing files from
the game directory. The parser assumes that the unpacked game files are present
in `{allods_install_directory}/data/`.

## Using as an editor

You can use the parser as an editor:

```
$ alm_parser -d {allods_data_directory} map.alm --output_format=json > map.json

... edit JSON file however you like ...

$ alm_parser -d {allods_data_directory} map.json --save edited-map.alm
```
