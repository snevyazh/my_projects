import glob
import os
from datetime import datetime

def find_file_with_full_text(search_directory):

    file_pattern = "full_text_*.txt"
    search_path = os.path.join(search_directory, file_pattern)

    found_files = glob.glob(search_path)
    list_dates = []
    if found_files:
        for file_path in found_files:
            date_string = os.path.basename(file_path)[10:-4]
            # Extract the date string, e.g., "2025-11-07"
            date_of_the_file =  datetime.strptime(date_string, "%Y-%m-%d").date()
            list_dates.append(date_of_the_file)
        if len(list_dates) > 0:
            max_date = max(list_dates)
            filename = os.path.join(search_directory, f"full_text_{max_date}.txt")
            return filename
        else:
            return None
    else:
       return None


def find_file_exists(search_directory, filename):

    search_path = os.path.join(search_directory, filename)
    return os.path.isfile(search_path)
