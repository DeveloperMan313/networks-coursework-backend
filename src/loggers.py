from logging import Formatter, Logger, StreamHandler, getLogger


def _get_logger_for_OSI_level(OSI_level: str) -> Logger:
    console_handler = StreamHandler()
    formatter = Formatter(
        f"$asctime {OSI_level} $levelname: $message",
        style="$",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger = getLogger(OSI_level)
    logger.addHandler(console_handler)
    return logger


phy_logger = _get_logger_for_OSI_level("phy")
cha_logger = _get_logger_for_OSI_level("cha")
app_logger = _get_logger_for_OSI_level("app")
