from sailwind_mod_sync.logutil import setup_logging
from sailwind_mod_sync.paths import AppPaths


def test_setup_logging_writes_file(paths: AppPaths) -> None:
    logger = setup_logging(paths.log_file)
    logger.info("debug line")
    for handler in logger.handlers:
        handler.flush()
    text = paths.log_file.read_text(encoding="utf-8")
    assert "Logging to" in text
    assert "debug line" in text
