import pdfplumber

def extract_text_from_pdf(pdf_path):
    """Extract text from every page of a PDF file."""
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = []

        for page in pdf.pages:
            text = page.extract_text()
            pages_text.append(text or "")

        return "\n".join(pages_text)
