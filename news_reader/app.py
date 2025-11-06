import warnings
# suppress warnings
warnings.filterwarnings('ignore')

import streamlit as st
import subprocess
import sys
import os
import toml
from datetime import datetime
import time
import toml as tomlib


# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="News Digest Runner",
    page_icon="🗞️",
    layout="wide"
)
st.markdown("""
<style>
/* Target all text elements for a clearer, larger font */
html, body, [class*="st-"] {
   font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
   font-size: 1.1rem;
}

/* Target the code block (for your logs) to make it clearer */
pre, code {
    font-family: 'Roboto Mono', 'Consolas', 'Menlo', monospace;
    font-size: 1.05rem !important; /* Use !important to override default */
}

/* Make the title a bit bigger to match */
h1 {
    font-size: 2.5rem !important;
}
</style>
""", unsafe_allow_html=True)

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

st.subheader("Settings")
time_window_days = st.number_input(
    "Set Time Window (in days)",
    min_value=1,
    max_value=30,
    value=1,  # Default to 1 day
    step=1,
    help="How many days back to look for articles (e.g., 1 = last 24 hours)."
)

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
    # st.subheader("Running main process, please wait...")

    try:
        # Start the subprocess
        # -u = unbuffered output (crucial for live updates)
        process_args = [
            python_executable,
            "-u",
            "main.py",
            str(time_window_days)  # Pass the number as a string
        ]

        process = subprocess.Popen(
            process_args,  # Use the new arguments
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

