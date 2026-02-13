import os

def clean_genesis_log(file_path='genesis.log'):
    """Wipe the 'genesis.log' file completely."""
    try:
        with open(file_path, 'w') as file:
            file.write('')
        print(f"Successfully wiped {file_path}")
    except Exception as e:
        print(f"Error wiping {file_path}: {e}")

def clean_project_folder(folder_path='projects/'):
    """Delete all files in 'projects/' that don't have 'manifest' or 'guardian' in their name."""
    try:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path) and 'manifest' not in filename and 'guardian' not in filename:
                os.remove(file_path)
                print(f"Deleted {filename} from {folder_path}")
    except Exception as e:
        print(f"Error cleaning {folder_path}: {e}")

def set_write_permissions(folder_path='projects/'):
    """Use 'os.chmod' to ensure the dashboard has write permissions to the project folder."""
    try:
        os.chmod(folder_path, 0o777)
        print(f"Set write permissions for {folder_path}")
    except Exception as e:
        print(f"Error setting write permissions for {folder_path}: {e}")

if __name__ == "__main__":
    clean_genesis_log()
    clean_project_folder()
    set_write_permissions()