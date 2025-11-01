import xml2epub


def create_ebook(root, epub_book_name, fixed_xml, image_filename):
    """Creates an EPUB ebook from XML content and an image.

        This function takes XML content representing the book's body and an image
        file (typically a cover image) and generates an EPUB ebook. It uses the
        `xml2epub` library to handle the EPUB creation process.

        Args:
            root (str): The root directory where the EPUB will be saved.
            epub_book_name (str): The name of the EPUB file (without the .epub extension).
            fixed_xml (str): The XML content of the book's body.
            image_filename (str): The path to the image file (e.g., "extracted_image.jpg").

        Returns:
            None.

        Raises:
            FileNotFoundError: If the specified image file does not exist.
            Exception: If any other error occurs during EPUB creation.

        Example:
            create_ebook("/path/to/output/folder", "MyBook", "<book><chapter>...</chapter></book>", "cover.jpg")
        """

    book_epub = xml2epub.Epub(epub_book_name)

    # add image

    chapter0 = xml2epub.create_chapter_from_string(image_filename, title='cover', strict=False)
    # create chapter objects
    chapter1 = xml2epub.create_chapter_from_string(fixed_xml)
    # add chapters to eBook
    book_epub.add_chapter(chapter0)
    book_epub.add_chapter(chapter1)
    # generate epub file
    book_epub.create_epub(root)
    print(f"Ebook {epub_book_name} created")
