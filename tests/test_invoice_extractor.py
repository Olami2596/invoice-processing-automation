import json

from src.invoice_extractor import generate_with_ollama


def test_generate_with_ollama_returns_vendor_name():
    prompt = """
    Return a JSON object with exactly one field:
    "vendor_name": "NovaTech Office Solutions"
    """

    result = generate_with_ollama(prompt)

    assert isinstance(result, str)

    parsed_result = json.loads(result)

    assert isinstance(parsed_result, dict)
    assert parsed_result["vendor_name"] == "NovaTech Office Solutions"

