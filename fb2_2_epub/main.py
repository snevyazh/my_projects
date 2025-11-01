from custom_functions.main_process import run_main_process


def main():
    """
    The main function that starts the file processing.
    """
    print("FB2 to EPUB converter")

    run_main_process()


if __name__ == "__main__":
    main()


# TODO add check if the same name is already present in .epub and then skip
# TODO add filenames toa list, and return
# TODO process the filelist with Threads