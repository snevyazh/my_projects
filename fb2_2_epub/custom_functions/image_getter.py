import base64
from bs4 import BeautifulSoup
import os


def extract_jpeg_from_fb2(fb2_content):
    """Extracts JPEG image data from an FB2 file content using Beautiful Soup."""
    try:
        soup = BeautifulSoup(fb2_content, "xml")  # Parse as XML
        binary_tag = soup.find("binary", {"content-type": "image/jpeg"})

        if binary_tag:
            base64_data = binary_tag.text.strip()  # Get the text *within* the tag
            binary_data = base64.b64decode(base64_data)
            return binary_data
        else:
            return None

    except (base64.binascii.Error, TypeError) as e:
        print(f"Error decoding Base64 data: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during parsing: {e}")
        return None


def read_the_fb2_image(fb2_filepath, encoding):
    """Attempts to extract and save a JPEG image embedded in an FB2 file.

        This function reads the contents of the provided FB2 file and attempts to
        extract an embedded JPEG image. If an image is found, it is saved as
        "extracted_image.jpg" in the same directory as the script.

        Args:
            fb2_filepath (str): The path to the FB2 file.

        Returns:
            None

        Raises:
            FileNotFoundError: If the FB2 file cannot be found.
            Exception: If any other error occurs during file reading or image extraction.
        """

    # read the image
    try:
        with open(fb2_filepath, "r", encoding=encoding) as file:
            fb2_image_data = file.read()

        jpeg_data = extract_jpeg_from_fb2(fb2_image_data)

        if jpeg_data:
            with open("extracted_image.jpg", "wb") as f:
                f.write(jpeg_data)
        else:
            print("No JPEG image found in the FB2 content.")

    except FileNotFoundError:
        print("Error: FB2 file not found.")
    except Exception as e:
        print(f"An unexpected error occurred during file reading: {e}")


def delete_image(image_filename):
    """Deletes the specified image file if it exists.

        This function attempts to delete the file at the given path. If the file
        does not exist, a message is printed to the console.

        Args:
            image_filename (str): The path to the image file to be deleted.

        Returns:
            None.
        """
    if os.path.exists(image_filename):
        os.remove(image_filename)
    else:
        print("The image file does not exist")
