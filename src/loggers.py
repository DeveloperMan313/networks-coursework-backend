from logging import Formatter, Logger, StreamHandler, getLogger


def _get_logger_for_OSI_layer(OSI_layer: str) -> Logger:
    console_handler = StreamHandler()
    formatter = Formatter(
        f"$asctime {OSI_layer} $levelname: $message",
        style="$",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger = getLogger(OSI_layer)
    logger.addHandler(console_handler)
    return logger


phy_logger = _get_logger_for_OSI_layer("phy")
dtl_logger = _get_logger_for_OSI_layer("dtl")
app_logger = _get_logger_for_OSI_layer("app")
