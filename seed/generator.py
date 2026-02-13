import os
import groq
from dotenv import load_dotenv

# 1. This looks for the .env file in the folder above this one
env_path = os.path.join(os.path.dirname(__file__), '../.env')
load_dotenv(env_path)

# 2. This grabs the key labeled "GROQ_API_KEY" from that file
API_KEY = os.getenv("GROQ_API_KEY")

# 3. Initialize the AI engine
client = groq.Groq(api_key=API_KEY)
MODEL = "llama-3.3-70b-versatile"

def generate_evolution(prompt):
    """Generates the code for the next stage of the world."""
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error in brain: {str(e)}"

