import os
import sys

DEFAULT_SUFFIXES = ('-hi.json', '-grafana12.json', '-perses.json')

def remove_target_files(suffixes, root_dir='.'):
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(suffixes):
                filepath = os.path.join(subdir, file)
                os.remove(filepath)
                print(f"Removed: {filepath}")

if __name__ == "__main__":
    remove_target_files(tuple(sys.argv[1:]) or DEFAULT_SUFFIXES)
