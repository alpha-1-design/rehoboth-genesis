import os, sys, time, platform, psutil

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from nexus.dashboard.api import get_api
    NEXUS_API_AVAILABLE = True
except ImportError:
    NEXUS_API_AVAILABLE = False

from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__, template_folder="templates")


def get_vitals():
    vitals = {}
    try:
        usage = psutil.disk_usage("/")
        vitals["disk"] = f"{usage.percent}%"
    except Exception:
        vitals["disk"] = "?"
    try:
        vitals["cpu"] = f"{psutil.cpu_percent(interval=0.1)}%"
    except Exception:
        vitals["cpu"] = "?"
    return vitals


@app.route("/")
def index():
    vitals = get_vitals()
    status = {}
    skills = []
    providers = []
    if NEXUS_API_AVAILABLE:
        api = get_api()
        status = api.get_status()
        skills = api.get_skills()
        providers = api.get_providers()
    return render_template(
        "index.html",
        vitals=vitals,
        status=status,
        skills=skills,
        providers=providers,
    )


@app.route("/api/status")
def api_status():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    return jsonify(api.get_status())


@app.route("/api/providers", methods=["GET", "POST"])
def api_providers():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    if request.method == "POST":
        return jsonify(api.add_provider(request.json))
    return jsonify(api.get_providers())


@app.route("/api/skills")
def api_skills():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    return jsonify(api.get_skills())


@app.route("/api/skills/<name>/activate", methods=["POST"])
def api_skill_activate(name):
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    return jsonify(api.activate_skill(name))


@app.route("/api/memory/search", methods=["POST"])
def api_memory_search():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    data = request.json or {}
    return jsonify(api.search_memory(data.get("query", ""), data.get("limit", 10)))


@app.route("/api/memory/store", methods=["POST"])
def api_memory_store():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    data = request.json or {}
    return jsonify(api.store_memory(data.get("content", ""), data.get("metadata")))


@app.route("/api/facts", methods=["GET", "POST"])
def api_facts():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    if request.method == "POST":
        data = request.json or {}
        return jsonify(api.add_fact(data.get("key", ""), data.get("value"), data.get("category", "general")))
    return jsonify(api.get_facts())


@app.route("/api/sessions")
def api_sessions():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    return jsonify(api.list_sessions())


@app.route("/api/agent/stats")
def api_agent_stats():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    return jsonify(api.get_agent_stats())


@app.route("/api/tools")
def api_tools():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    return jsonify(api.get_tools())


@app.route("/api/vitals")
def api_vitals():
    return jsonify(get_vitals())


@app.route("/api/automation/status")
def api_automation_status():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    return jsonify(api.get_automation_status())


@app.route("/api/automation/execute", methods=["POST"])
def api_automation_execute():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    data = request.json or {}
    tool = data.get("tool")
    params = data.get("params", {})
    return jsonify(api.run_automation_tool(tool, params))


@app.route("/api/execute", methods=["POST"])
async def api_execute():
    if not NEXUS_API_AVAILABLE:
        return jsonify({"error": "Nexus API not available"})
    api = get_api()
    data = request.json or {}
    task = data.get("task", "")
    if not task:
        return jsonify({"error": "No task provided"})
    result = await api.run_agent_task(task)
    return jsonify(result)


@app.route("/logs")
def logs():
    lines = []
    log_path = os.path.join(os.path.dirname(__file__), "nexus.log")
    if os.path.exists(log_path):
        try:
            with open(log_path) as f:
                lines = f.readlines()[-50:]
        except Exception:
            pass
    return "\n".join(lines)


@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.template_folder, "manifest.json", mimetype="application/json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(app.template_folder, "sw.js", mimetype="application/javascript")


