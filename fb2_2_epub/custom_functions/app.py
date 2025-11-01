import streamlit as st
import os


def get_valid_folder_input():
    """Gets a valid folder path from the user, retrying until valid or "DDD" is entered."""

    while True:
        st.title("FB2 to EPUB converter")

        # Get user input
        folder_to_scan = st.text_input("Enter the folder to scan (or 'DDD' to exit): ")

        if folder_to_scan.upper() == "DDD":
            return None  # Signal to exit

        if not os.path.exists(folder_to_scan):
            print(f"Error: Folder '{folder_to_scan}' does not exist.")
        elif not os.path.isdir(folder_to_scan):
            print(f"Error: '{folder_to_scan}' is not a directory.")
        else:
            return folder_to_scan  # Valid folder entered


if __name__ == "__main__":
    user_input = get_valid_folder_input()
