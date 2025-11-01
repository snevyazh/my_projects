import os
from custom_functions import image_getter
from custom_functions import xml_parser
from custom_functions import epub_creater


def get_valid_folder_input():
    """Gets a valid folder path from the user, retrying until valid or "DDD" is entered."""
    while True:
        folder_to_scan = input("Enter the folder to scan (or 'DDD' to exit): ")

        if folder_to_scan.upper() == "DDD":
            return None  # Signal to exit

        if not os.path.exists(folder_to_scan):
            print(f"Error: Folder '{folder_to_scan}' does not exist.")
        elif not os.path.isdir(folder_to_scan):
            print(f"Error: '{folder_to_scan}' is not a directory.")
        else:
            return folder_to_scan  # Valid folder entered


def run_main_process():
    """Processes FB2 files in a given folder and creates EPUB ebooks.

    This function prompts the user for a folder path, then iterates through all
    .fb2 files within that folder (including subfolders). For each FB2 file, it:

    1. Extracts the XML body using `xml_parser.get_fb2_xml()`.
    2. Extracts the cover image using `image_getter.read_the_fb2_image()`.
    3. Creates an EPUB ebook using `epub_creater.create_ebook()`.
    4. Deletes the temporary extracted image file.

    The function handles potential errors during file processing and provides
    informative output to the console.

    Args:
        None (prompts the user for input).

    Returns:
        None.

    Raises:
        FileNotFoundError: If the provided folder path does not exist.
        Exception: If any other error occurs during processing."""

    #  '/Users/snevyazh/Downloads/fantasy/FB2/Ааронович Бен/Питер Грант/'

    # check the folder entered
    folder_to_scan = get_valid_folder_input()
    if not folder_to_scan:
        print("User exit")
        exit(0)

    # get the files
    for root, _, files in os.walk(folder_to_scan):
        for filename in files:
            if filename.lower().endswith(".fb2"):
                fb2_filepath = os.path.join(root, filename)

                # read the xml body
                fixed_xml, epub_book_name, fb2_content, encoding = xml_parser.get_fb2_xml(fb2_filepath)

                # read the image (no return as it is a file)
                image_getter.read_the_fb2_image(fb2_filepath, encoding)
                # create ebook
                temp_image_filename = "extracted_image.jpg"
                epub_creater.create_ebook(root, epub_book_name, fb2_content, temp_image_filename) #fixed_xml

                # delete the temp cover file, so it won't be used wrongly
                image_getter.delete_image(temp_image_filename)
