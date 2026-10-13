from urllib.parse import quote


def attachment_header(filename: str) -> str:
    """A Content-Disposition value that a user-chosen name (code name) cannot break or extend."""
    fallback = "".join(
        character if character.isascii() and character.isprintable() and character not in '"\\' else "_"
        for character in filename
    )
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
