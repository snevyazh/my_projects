import sys
import os


def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_output_path(filename):
    """ Get path for output files (next to the executable) """
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.abspath(".")

    output_dir = os.path.join(application_path, "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    return os.path.join(output_dir, filename)