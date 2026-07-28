import os


def file_path(data_folder: str):
    """
    Get the absolute path to a file in the data folder.
    args:
        data_folder (str): The name of the data folder.
    return:
        list: A list containing the absolute paths to the files in the data folder.
    """
    file_paths = []
    for root, _, files in os.walk(data_folder):
        for file in files:
            file_path = os.path.join(root, file)
            details = str(file_path).split("/")
            meta_data = {
                "company_name": details[-3],
                "year": details[-2],
                "report_type": details[-1].split(".")[0],
            }
            file_paths.append((file_path, meta_data))
    return file_paths


def write_to_file(content, output_file):
    """
    Write content to a file.
    args:
        content (str): The content to write.
        output_file (str): The path to the output file.
    """
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
