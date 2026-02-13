import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))
GROQ_API_KEY = os.getenv("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")

MODEL = "llama-3.3-70b-versatile"

client = Groq(api_key=API_KEY)

def expand_code(file_path):
    try:
        with open(file_path, "r") as f:
            existing_code = f.read()

        prompt = f"""
        Context: {existing_code}
        
        Task: Act as a Senior Backend Developer. 
        1. Extend this logic by creating a FastAPI router or a set of utility functions.
        2. Ensure the code is production-ready with type hints.
        3. List dependencies in the DEP section.

        Format:
        DEP: [comma separated libraries]
        NOTE: [developer-focused explanation of the architecture]
        CODE:
        [python code]
        """

        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}]
        )

        return completion.choices[0].message.content

    except Exception as e:
        return f"NOTE: Error encountered during generation.\nCODE:\n# Error: {str(e)}"

