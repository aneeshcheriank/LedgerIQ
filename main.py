from src.file_process import pdf_to_markdown

if __name__ == "__main__":
    path = "./data/raw/apple/2022/10K.pdf"
    result = pdf_to_markdown(path)
    if result["status"] == "success":
        print("PDF converted to markdown successfully.")
        print("Markdown content:")
        print(result["markdown"])
