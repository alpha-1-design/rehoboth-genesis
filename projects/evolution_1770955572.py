import os
import glob
from datetime import datetime

# Define the projects folder path and the files to exclude
projects_folder = 'projects'
exclude_files = ['master_manifest.txt']
evolution_files = glob.glob(os.path.join(projects_folder, 'evolution_*.txt'))

# Sort the evolution files by modification time and get the 5 most recent ones
evolution_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
recent_evolution_files = evolution_files[:5]
recent_evolution_files = [os.path.basename(file) for file in recent_evolution_files]

# Get all files in the projects folder
all_files = os.listdir(projects_folder)

# Delete files except the most recent evolution files and the master manifest
for file in all_files:
    if file not in recent_evolution_files and file not in exclude_files:
        file_path = os.path.join(projects_folder, file)
        if os.path.isfile(file_path):
            os.remove(file_path)

# Clear the genesis.log file
genesis_log_path = os.path.join(projects_folder, 'genesis.log')
with open(genesis_log_path, 'w') as f:
    f.write('')