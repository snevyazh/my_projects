import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from llm_call_functions import llm_call_open_ai as llm_call
import toml as tomlib

# Load secrets
with open("./.streamlit/secrets.toml", "r") as f:
    secret_data = tomlib.load(f)
os.environ["OPEN_AI_KEY"] = secret_data["secrets"]["OPEN_AI_KEY"]

model = llm_call.get_model()

# Load Prompt
with open("./prompts/prompt_telegram_summary.md", 'r', encoding='utf-8') as f:
    prompt_template = f.read()
    
# Load test text
with open("test_telegram_output.txt", "r", encoding="utf-8") as f:
    text = f.read()

print("Calling LLM...")
prompt = prompt_template.format(text)
summary = llm_call.call_llm(model, prompt)

print("\n\n--- LLM RESULT ---\n")
print(summary)
print("\n------------------\n")
