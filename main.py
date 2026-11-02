from src.pdf_extractor import extract_text_from_pdf

def main():
    pdf_path = "data/fictional_invoice.pdf"

    extracted_text = extract_text_from_pdf(pdf_path)

    print(extracted_text)


if __name__ == "__main__":
    main()
