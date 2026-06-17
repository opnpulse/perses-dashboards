import os

def remove_target_files(root_dir='.'):
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith('-hi.json') or file.endswith('-grafana12.json') or file.endswith('-perses.json'): # or file.endswith('-ready.json'):
                filepath = os.path.join(subdir, file)
                os.remove(filepath)
                print(f"Removed: {filepath}")

if __name__ == "__main__":
    remove_target_files()
