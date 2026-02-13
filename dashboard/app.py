import sys, os
from flask import Flask, render_template, redirect, url_for, flash
from git import Repo

# Ensure the bridge to your Git Manager is solid
sys.path.append(os.path.abspath("../seed"))
try:
    from git_manager import push_to_github
except ImportError:
    print("[!] Critical: git_manager.py not found in ../seed/")

app = Flask(__name__)
app.secret_key = "rehoboth_genesis_secret" # Needed for error messages

PROJECT_PATH = os.path.abspath("../projects")
REPO_PATH = os.path.abspath("..")

def get_file_status(filename):
    try:
        repo = Repo(REPO_PATH)
        rel_path = os.path.join("projects", filename)
        
        # 1. Check for untracked (New) files
        if rel_path in repo.untracked_files:
            return "NEW"
        
        # 2. Check for local changes not yet committed
        if any(rel_path in item.a_path for item in repo.index.diff(None)):
            return "MODIFIED"
        
        # 3. Verify if local matches remote (The Anti-False-Sync check)
        # If we have commits that aren't pushed, it's not SYNCED
        ahead = list(repo.iter_commits('origin/main..main'))
        if ahead:
            # Check if this specific file was part of those unpushed commits
            for commit in ahead:
                if rel_path in commit.stats.files:
                    return "AWAITING_PUSH"

        return "SYNCED"
    except Exception as e:
        return "UNKNOWN"

@app.route('/')
def home():
    artifacts = []
    if not os.path.exists(PROJECT_PATH):
        return "Project folder missing!"

    files = sorted([f for f in os.listdir(PROJECT_PATH) if f.endswith('.py')], reverse=True)
    
    for f in files:
        file_path = os.path.join(PROJECT_PATH, f)
        with open(file_path, 'r') as file:
            content = file.read()
            # Intelligent Note Extraction
            note = "System component."
            if "# NOTE:" in content:
                note = content.split("# NOTE:")[1].split("\n")[0].strip()
            
            artifacts.append({
                "name": f,
                "note": note,
                "code": content[:600], # Larger preview for elite eyes
                "status": get_file_status(f)
            })
            
    return render_template('index.html', artifacts=artifacts)

@app.route('/approve/<filename>')
def approve(filename):
    # Attempt the push and catch any failure
    success = push_to_github(filename)
    
    if not success:
        print(f"[!] Deployment failed for {filename}. Check credentials.")
        # In a future update, we can pass this error to the UI
    
    return redirect(url_for('home'))

if __name__ == "__main__":
    # Host 0.0.0.0 makes it accessible on your local network/phone browser
    app.run(host='0.0.0.0', port=5000, debug=True)

