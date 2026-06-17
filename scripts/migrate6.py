import os
import subprocess
import json
import sys

# Define the root directory to start traversal
root_dir = '.'  # Change as needed

# Function to process and run percli migrate command
def process_file(filepath):
    # Construct the output filename
    new_filename = filepath.replace('-ready.json', '-perses.json')
    
    # Construct the percli command
    command = [
        'percli', 'migrate',
        '-f', filepath,
        '--project', 'pp',
        '--online',
        '-o', 'json'
    ]
    
    try:
        # Run the command and capture output
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Parse the output as JSON
        output_data = json.loads(result.stdout)
        
        # Save the output to the new file
        with open(new_filename, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"Processed {filepath} and saved to {new_filename}")
    
    except subprocess.CalledProcessError as e:
        print(f"Error processing {filepath}: {e.stderr}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output for {filepath}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error processing {filepath}: {e}")
        sys.exit(1)

# Traverse directories and process JSON files
for subdir, _, files in os.walk(root_dir):
    for file in files:
        if file.endswith('-ready.json'):
            filepath = os.path.join(subdir, file)
            process_file(filepath)

print("Processing complete.")