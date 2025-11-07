import subprocess
import sys

command = [sys.executable, "-m", "streamlit", "run", "web_app/app.py"]

try:
    subprocess.run(command, check=True)
except FileNotFoundError:
    print(f"Error: 'streamlit' or '{sys.executable}' not found.")
    print("Please ensure streamlit is installed in this environment.")
except subprocess.CalledProcessError as e:
    print(f"Streamlit app failed to run: {e}")

