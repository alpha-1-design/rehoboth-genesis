import sys, os, time, psutil
from flask import Flask, render_template, request, jsonify

# Connect to the 'seed' logic for AI and Git
sys.path.append(os.path.abspath("../seed"))
from generator import generate_evolution
from git_manager import push_to_github

app = Flask(__name__)
PROJECT_PATH = os.path.abspath("../projects")

def get_vitals():
    """Reads hardware stats safely for Mobile. If blocked, it stays clean."""
    vitals = {"DISK": "N/A"}
    try:
        # Disk usage is usually allowed even on restricted Android
        vitals["DISK"] = f"{psutil.disk_usage('/').percent}%"
    except:
        pass
    return vitals

@app.route('/')
def index():
    if not os.path.exists(PROJECT_PATH):
        os.makedirs(PROJECT_PATH)
    
    vitals = get_vitals()
    # Get all python files, newest first
    files = sorted([f for f in os.listdir(PROJECT_PATH) if f.endswith('.py')], 
                   key=lambda x: os.path.getmtime(os.path.join(PROJECT_PATH, x)), 
                   reverse=True)
    
    artifacts = []
    for f in files:
        with open(os.path.join(PROJECT_PATH, f), 'r') as file:
            # We only send a snippet of code to keep the mobile UI fast
            artifacts.append({"name": f, "code": file.read()[:200]})
            
    return render_template('index.html', artifacts=artifacts, stats=vitals)

@app.route('/execute', methods=['POST'])
def execute():
    instruction = request.json.get('instruction')
    prompt = f"Objective: {instruction}. Create a short, functional Python script. Respond with CODE ONLY."
    
    try:
        new_code = generate_evolution(prompt)
        # Clean up any AI-generated backticks that break scripts
        clean_code = new_code.replace("```python", "").replace("```", "").strip()
        
        filename = f"evolution_{int(time.time())}.py"
        with open(os.path.join(PROJECT_PATH, filename), "w") as f:
            f.write(clean_code)
            
        return jsonify({"status": "success", "feedback": f"Evolution: {filename} created."})
    except Exception as e:
        return jsonify({"status": "error", "feedback": f"System Alert: {str(e)}"})

@app.route('/deploy/<filename>')
def deploy(filename):
    """The 'Deploy' button calls this to push to GitHub."""
    try:
        success = push_to_github(filename)
        if success:
            return jsonify({"status": "success", "message": f"{filename} pushed to Vault."})
        return jsonify({"status": "error", "message": "Deploy failed. Check terminal."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    # Host 0.0.0.0 makes it accessible on your phone's local network
    app.run(host='0.0.0.0', port=5000)

