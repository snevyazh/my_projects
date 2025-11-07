import sys
import subprocess
from pathlib import Path



def check_and_install_playwright_browsers():
    """
    Checks if Playwright browsers are installed (using a flag file).
    If not, it runs the installation command.
    """
    # Create a flag file in the user's home directory
    home_dir = Path.home()
    # You can name this flag file anything you want
    flag_file = home_dir / ".daily_digest_playwright_installed"

    if not flag_file.exists():
        print("First-time setup: Installing browser (Chromium)...")

        try:
            # We use sys.executable to be sure we're using the Python
            # interpreter that is bundled *inside* the .exe
            # We only install chromium to save space and time.
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # If successful, create the flag file
            flag_file.touch()
            print("Browser installation complete.")

        except subprocess.CalledProcessError as e:
            print("--- ERROR: FAILED TO INSTALL BROWSER ---")
            print("Playwright (which is required) could not be installed.")
            print("Please check your internet connection and try again.")
            print(f"Error details: {e.stderr.decode()}")
            # Exit the app; it cannot continue.
            sys.exit(1)

    else:
        # This will be printed on every run *after* the first one
        print("Playwright browser is already installed. Infrastructure ready, Sir")
