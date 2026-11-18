from scripts.evaluate_adapter import token_f1


def test_token_f1_identical():
    assert token_f1("DNS maps names to IP addresses", "DNS maps names to IP addresses") == 1.0


def test_token_f1_no_overlap():
    assert token_f1("apple orange", "network security") == 0.0


def test_token_f1_partial_overlap():
    score = token_f1("DNS maps domain names", "DNS maps names to IP addresses")
    assert 0 < score < 1
