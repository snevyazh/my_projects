from custom_functions import xml_fixer
from custom_functions.fb2_reader import Fb2Book


def get_fb2_xml(fb2_filepath):
    """Extracts and fixes the XML content from an FB2 file.

        This function reads an FB2 file, extracts its body content, and then uses
        `xml_fixer.fix_xml_for_specific_parser()` to transform the XML into a format
        suitable for a specific parser. It also extracts the book's title from the
        FB2 metadata or uses the filename as a fallback.

        Args:
            fb2_filepath (str): The path to the FB2 file.

        Returns:
            tuple: A tuple containing:
                - fixed_xml (str): The fixed XML content.
                - epub_book_name (str): The name of the book for the EPUB.

            Returns None if the file does not exist or another error occurs.

        Raises:
            FileNotFoundError: If the provided FB2 file does not exist.
            Exception: If any other error occurs during file reading or XML processing.
        """

    print(fb2_filepath)

    # read fb2 book
    book_fb_2 = Fb2Book(fb2_filepath)
    encoding = book_fb_2.encoding_of_the_file
    fb2_content = book_fb_2.get_body()
    fixed_xml = xml_fixer.fix_xml_for_specific_parser(fb2_content, encoding)
    # create the epub book
    try:
        # embedded in the file
        epub_book_name = book_fb_2.get_title()
    except:
        # filename
        epub_book_name = fb2_filepath.split('/')[-1].rstrip('.fb2')

    return fixed_xml, epub_book_name, fb2_content, encoding
