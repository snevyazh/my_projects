import streamlit as st
import subprocess
import sys
import os
import toml
from datetime import datetime
import time
import toml as tomlib
import warnings

# suppress warnings
warnings.filterwarnings('ignore')

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="News Digest Runner",
    page_icon="🗞️",
    layout="wide"
)

# real-time Hebrew news feeds
with open("./config/config.toml", "r") as f:
    config_data = tomlib.load(f)
ISRAELI_NEWS_FEEDS = config_data["feeds"]["ISRAELI_NEWS_FEEDS"]

# --- 2. LOAD API KEY (ISOLATED) ---
# We read the key here to pass it to the subprocess
try:
    secrets = toml.load(".streamlit/secrets.toml")
    API_KEY = secrets["secrets"]["GEMINI_API_KEY"]
except Exception as e:
    st.error(f"Error loading API key from .streamlit/secrets.toml: {e}")
    st.code(
        "Make sure your .streamlit/secrets.toml file exists and has:\n\n[secrets]\nGEMINI_API_KEY=\"your_key_here\"")
    st.stop()

# --- 3. THE APP UI ---
st.title("🗞️ Daily Hebrew News Digest Runner")

st.info(f"This app runs the following RSS feeds {ISRAELI_NEWS_FEEDS}")

if st.button("Run Daily Digest", type="primary"):
    st.divider()

    # --- 4. THE SUBPROCESS LOGIC ---

    # Create a placeholder for the live log output
    log_placeholder = st.empty()

    # Get the path to the python executable in the *current* venv
    python_executable = sys.executable

    # Get the environment variables for this process
    env = os.environ.copy()
    # Set the KEY variable *only* for the subprocess
    env["KEY"] = API_KEY

    log_output = ""
    st.subheader("Running `main.py`...")

    try:
        # Start the subprocess
        # -u = unbuffered output (crucial for live updates)
        process = subprocess.Popen(
            [python_executable, "-u", "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            env=env
        )

        # Read the output line by line, in real-time
        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Append to our log string
            log_output += line

            # Update the Streamlit element
            log_placeholder.code(log_output, language="bash")

        process.wait()

        st.success("Script finished.")
        st.divider()

        # --- 5. SHOW THE FINAL RESULT ---
        st.header("Final Digest")

        # Find the summary file your script created
        run_time = datetime.today().strftime('%Y-%m-%d')
        summary_file = f"./output/summary_text_{run_time}.txt"

        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary_text = f.read()
            st.markdown(summary_text)
        except FileNotFoundError:
            st.error(f"Error: Could not find the output file: {summary_file}")
            st.info("The script ran, but the summary file was not created.")

    except Exception as e:
        st.error(f"An error occurred while trying to run the script: {e}")
        st.code(log_output)  # Show what we got before it crashed



# python - m streamlit run app.py

