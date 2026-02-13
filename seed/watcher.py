import time
import os
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from generator import expand_code

PROJECTS_DIR = "projects"

class GenesisHandler(FileSystemEventHandler):
    def on_created(self, event):
        # Only act on new Python files that aren't already evolutions
        if event.src_path.endswith(".py") and "evolution" not in event.src_path:
            print(f"[*] Analyzing new artifact: {event.src_path}")
            
            raw_response = expand_code(event.src_path)
            
            # Parse the structured response using Regex
            dep_match = re.search(r"DEP:\s*(.*)", raw_response)
            note_match = re.search(r"NOTE:\s*(.*)", raw_response)
            code_match = re.search(r"CODE:\s*(.*)", raw_response, re.DOTALL)

            dependencies = dep_match.group(1).strip() if dep_match else ""
            note = note_match.group(1).strip() if note_match else "No notes provided."
            code = code_match.group(1).strip() if code_match else "# Error: No code generated."

            timestamp = int(time.time())
            
            # 1. Save the Evolution Code
            filename = f"evolution_{timestamp}.py"
            with open(os.path.join(PROJECTS_DIR, filename), "w") as f:
                f.write(f"# NOTE: {note}\n\n{code}")

            # 2. Update Requirements
            if dependencies:
                with open(os.path.join(PROJECTS_DIR, "requirements.txt"), "a") as f:
                    for item in dependencies.split(","):
                        f.write(f"{item.strip()}\n")

            print(f"[+] Success: {filename} created.")
            print(f"[i] Agent Note: {note}")

if __name__ == "__main__":
    if not os.path.exists(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR)
    
    event_handler = GenesisHandler()
    observer = Observer()
    observer.schedule(event_handler, PROJECTS_DIR, recursive=False)
    
    print("Rehoboth Genesis Watcher: Online and parsing...")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

