from src.modules.common.downloads import attachment_header


def test_quotes_and_non_ascii_cannot_break_the_header():
    header = attachment_header('Project "Blue"\r\nX-Evil: 1 é.csv')
    assert "\r" not in header
    assert "\n" not in header
    assert header.count('"') == 2
    assert "filename*=UTF-8''Project%20%22Blue%22%0D%0AX-Evil%3A%201%20%C3%A9.csv" in header


def test_plain_name_keeps_a_readable_fallback():
    assert attachment_header("Atlas.csv") == "attachment; filename=\"Atlas.csv\"; filename*=UTF-8''Atlas.csv"
