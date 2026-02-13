import sys, os, time, psutil
from flask import Flask, render_template, request, jsonify

# Connect to the 'seed' logic
sys.path.append(os.path.abspath("../seed"))
from generator import generate_evolution
from git_manager import push_to_github

app = Flask(__name__)
PROJECT_PATH = os.path.abspath("../projects")

def get_vitals():
    vitals = {"DISK": "0%"}
    try: vitals["DISK"] = f"{psutil.disk_usage('/').percent}%"
    except: pass
    return vitals

@app.route('/')
def index():
    vitals = get_vitals()
    files = sorted([f for f in os.listdir(PROJECT_PATH) if f.endswith('.py')], reverse=True)
    artifacts = []
    for f in files:
        with open(os.path.join(PROJECT_PATH, f), 'r') as file:
            artifacts.append({"name": f, "code": file.read()[:120]})
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

@app.route('/deploy/<filename>')
def deploy(filename):
    """Pushes the specific file to GitHub and clears local clutter if needed."""
    try:
        success = push_to_github(filename)
        if success:
            return jsonify({"status": "success", "message": f"{filename} secured in GitHub Vault."})
        return jsonify({"status": "error", "message": "Deploy failed. Check logs."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

