import os
import importlib.util
import concurrent.futures

def run_module(module_path):
    spec = importlib.util.spec_from_file_location("module.name", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, 'main'):
        module.main()

def main():
    project_dir = 'projects'
    for filename in os.listdir(project_dir):
        if filename.endswith(".py"):
            module_path = os.path.join(project_dir, filename)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(run_module, module_path)]
                for future in concurrent.futures.as_completed(futures):
                    future.result()

if __name__ == "__main__":
    main()