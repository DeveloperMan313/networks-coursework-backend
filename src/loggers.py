import logging

_formatter_msg_template = "{asctime} [OSI_level] {levelname}: {message}"
_formatter_datefmt = "%Y-%m-%d %H:%M:%S"

_console_handler_phy = logging.StreamHandler()
_formatter_phy = logging.Formatter(
    _formatter_msg_template.replace("[OSI_level]", "phy"),
    style="{",
    datefmt=_formatter_datefmt,
)
_console_handler_phy.setFormatter(_formatter_phy)
phy_logger = logging.getLogger(__name__)
phy_logger.addHandler(_console_handler_phy)
