import sys, os, time, psutil, subprocess, shutil
from flask import Flask, render_template, request, jsonify

# Connect to the 'seed' logic
sys.path.append(os.path.abspath("../seed"))
from generator import generate_evolution
from git_manager import push_to_github

app = Flask(__name__)
PROJECT_PATH = os.path.abspath("../projects")
LOG_PATH = os.path.abspath("genesis.log")

def get_vitals():
    """Calculates disk and system health."""
    vitals = {"DISK": "0%"}
    try:
        usage = psutil.disk_usage('/')
        vitals["DISK"] = f"{usage.percent}%"
    except: pass
    return vitals

@app.route('/')
def index():
    if not os.path.exists(PROJECT_PATH): os.makedirs(PROJECT_PATH)
    vitals = get_vitals()
    files = sorted([f for f in os.listdir(PROJECT_PATH) if f.endswith('.py')], 
                   key=lambda x: os.path.getmtime(os.path.join(PROJECT_PATH, x)), reverse=True)
    artifacts = []
    for f in files:
        try:
            with open(os.path.join(PROJECT_PATH, f), 'r') as file:
                artifacts.append({"name": f, "code": file.read()[:150]})
        except: continue
    return render_template('index.html', artifacts=artifacts, stats=vitals)

@app.route('/execute', methods=['POST'])
def execute():
    instruction = request.json.get('instruction')
    prompt = f"Objective: {instruction}. Create a short, functional Python script. Code only."
    try:
        new_code = generate_evolution(prompt).replace("```python", "").replace("```", "").strip()
        filename = f"evolution_{int(time.time())}.py"
        with open(os.path.join(PROJECT_PATH, filename), "w") as f:
            f.write(new_code)
        return jsonify({"status": "success", "feedback": f"Created {filename}"})
    except Exception as e:
        return jsonify({"status": "error", "feedback": str(e)})

@app.route('/run/<filename>')
def run_module(filename):
    try:
        file_path = os.path.join(PROJECT_PATH, filename)
        # Detach process to prevent zombie processes
        subprocess.Popen([sys.executable, file_path], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return jsonify({"status": "success", "message": f"{filename} is now ACTIVE."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/logs')
def get_logs():
    """Streams the last 15 lines of the genesis log."""
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, 'r') as f:
                lines = f.readlines()
                return "".join(lines[-15:])
        except: return "Log read error."
    return "Waiting for Manifest Heartbeat..."

@app.route('/purge')
def purge_system():
    """Investor-grade maintenance: Wipes non-essentials to reclaim disk."""
    try:
        # 1. Clear the log file
        with open(LOG_PATH, "w") as f: 
            f.write(f"[{time.ctime()}] SYSTEM RESET: Storage Purged.\n")
        
        # 2. Keep only the most recent 3 files + Manifest
        files = sorted([f for f in os.listdir(PROJECT_PATH) if f.endswith('.py')], 
                       key=lambda x: os.path.getmtime(os.path.join(PROJECT_PATH, x)), reverse=True)
        
        for f in files[4:]: # Delete everything after the 4 most recent
            if "1770952671" not in f: # Protect the Master Manifest
                os.remove(os.path.join(PROJECT_PATH, f))
                
        return jsonify({"status": "success", "message": "Disk space reclaimed."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/deploy/<filename>')
def deploy(filename):
    try:
        success = push_to_github(filename)
        return jsonify({"status": "success", "message": f"{filename} pushed to Vault."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)

