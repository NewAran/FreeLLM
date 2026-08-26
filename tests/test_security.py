from app.security import hash_api_key, hash_password, make_admin_token, verify_admin_token, verify_password


def test_password_hash_roundtrip():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)


def test_api_key_hash_is_stable():
    assert hash_api_key("abc") == hash_api_key("abc")
    assert hash_api_key("abc") != hash_api_key("abcd")


def test_admin_token():
    key = b"x" * 32
    token = make_admin_token(key, 60)
    assert verify_admin_token(key, token)
    assert not verify_admin_token(b"y" * 32, token)
