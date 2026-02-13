import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))
GITHUB_TOKEN = os.getenv("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")
GITHUB_USER = "alpha-1-design"
REPO_NAME = "rehoboth-genesis"
REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def push_to_github(filename):
    try:
        # 1. Load the repo
        if not os.path.exists(os.path.join(REPO_PATH, ".git")):
            repo = Repo.init(REPO_PATH)
        else:
            repo = Repo(REPO_PATH)

        # 2. Force branch name to 'main'
        if repo.active_branch.name != 'main':
            try:
                repo.git.branch('-M', 'main')
            except:
                # If branch 'main' doesn't exist yet, create it
                repo.git.checkout('-b', 'main')

        # 3. Add and Commit
        file_full_path = os.path.join(REPO_PATH, "projects", filename)
        repo.index.add([file_full_path])
        repo.index.commit(f"Evolution: {filename}")

        # 4. Setup Remote & Push
        remote_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{REPO_NAME}.git"
        if 'origin' not in [r.name for r in repo.remotes]:
            origin = repo.create_remote('origin', remote_url)
        else:
            origin = repo.remote('origin')
            origin.set_url(remote_url)

        origin.push('main')
        return True

    except Exception as e:
        print(f"Git Error: {str(e)}")
        return False

