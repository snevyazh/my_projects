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

# Load the second summary prompt
with open("./prompts/prompt_second_summary.md", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

# Load the result from the previous run (the compiled Telegram News Flashes)
with open("full_summary_output.md", "r", encoding="utf-8") as f:
    text = f.read()
    
# Clean off the python print wrappers so it's just the exact markdown
if "```markdown" in text:
    text = text.split("```markdown")[1].split("```")[0].strip()

# Create a mock database input containing ONLY the telegram summary
combined_text = text

print("Calling second LLM prompt...")
prompt = prompt_template.format(combined_text)
summary = llm_call.call_llm(model, prompt)

print("\n\n--- SECOND LLM (DAILY REPORT) RESULT ---\n")
print(summary)
print("\n---------------------------------------\n")
