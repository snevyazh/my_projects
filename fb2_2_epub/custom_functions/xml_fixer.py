from lxml import etree


def fix_xml_for_specific_parser(xml_string, encoding):
    """Fixes XML to have direct title content for a specific parser.

    This function transforms the provided XML string to make the title content
    directly accessible by the target parser. It assumes the target parser
    expects the title text to be directly within the `<title>` element,
    rather than potentially contained within child elements like `<p>`.

    Args:
        encoding: text encoding
        xml_string (str): The XML string to be transformed.

    Returns:
        str: The transformed XML string, or None if an error occurs during processing.

    The function performs the following transformations:

    1. It uses `etree.XMLParser(recover=True)` to attempt parsing even with
       minor errors in the XML.
    2. It locates the `<title>` element.
    3. If a `<title>` element is found, it extracts the text content from any
       child `<p>` elements within it and sets that combined text as the
       direct text content of the `<title>` element. This ensures the title
       text is directly accessible by the parser.
    4. It removes the child `<p>` elements from the `<title>` element.
    5. It checks for and adds missing namespaces and fixes attributes that
       start with "l:". This might be necessary for specific parsers.

    Raises:
        etree.XMLSyntaxError: If a critical parsing error is encountered.
        Exception: If any other unexpected error occurs.
    """

    try:
        parser = etree.XMLParser(recover=True)  # Recover from errors
        root = etree.fromstring(xml_string, parser=parser) # .encode(encoding)
        title_element = root.find(".//title")
        if title_element is not None:
            # Extract text from child <p> elements and set it as title text
            title_text = "\n".join(p.text for p in title_element.findall(".//p") if p.text is not None)
            title_element.text = title_text  # Set the title's direct text content
            # Remove the child <p> elements
            for p in title_element.findall(".//p"):
                title_element.remove(p)
            print(f"title read {title_text}")
        # Check for and add missing namespaces and fix attributes
        if any("l:" in attrib for element in root.iter() for attrib in element.attrib):
            nsmap = {'l': 'http://www.w3.org/1999/xlink'}
            root.attrib.update(nsmap)
            for element in root.iter():
                for attrib_name, attrib_value in list(
                        element.attrib.items()):  # Iterate over a copy of the items to allow modification
                    if "l:" in attrib_name:
                        new_attrib_name = f'{{{nsmap["l"]}}}{attrib_name[2:]}'
                        element.attrib[new_attrib_name] = attrib_value
                        del element.attrib[attrib_name]
        # print(etree.tostring(root, encoding=encoding)[:500])
        return etree.tostring(root, encoding=encoding)

    except etree.XMLSyntaxError as e:
        print(f"XML Syntax Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
