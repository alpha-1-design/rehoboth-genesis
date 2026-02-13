import os
from git import Repo
from dotenv import load_dotenv

# Load keys
env_path = os.path.join(os.path.dirname(__file__), '../.env')
load_dotenv(env_path)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def push_to_github(filename):
    """Securely pushes a specific file using the authenticated origin."""
    try:
        repo = Repo(REPO_PATH)
        
        # 1. Stage the file
        file_path = f"projects/{filename}"
        if not os.path.exists(os.path.join(REPO_PATH, file_path)):
            print(f"File not found: {file_path}")
            return False
            
        repo.index.add([file_path])
        
        # 2. Commit
        repo.index.commit(f"GENESIS_EVOLUTION: {filename}")
        
        # 3. Push using the token explicitly in the push command
        origin = repo.remote(name='origin')
        
        # We set the URL to the clean version you just verified manually
        clean_url = "https://github.com/alpha-1-design/rehoboth-genesis.git"
        # Insert the token into the URL properly
        auth_url = clean_url.replace("https://", f"https://{GITHUB_TOKEN}@")
        origin.set_url(auth_url)
        
        # Push to the upstream we just set manually
        origin.push(refspec='main:main')
        
        # Optional: Reset URL back to clean version to keep local git 'silent'
        origin.set_url(clean_url)
        
        return True
    except Exception as e:
        print(f"Git Error: {str(e)}")
        return False

