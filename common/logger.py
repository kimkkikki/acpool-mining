import os
import logging

if os.getenv("DEBUG") == 'true':
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(module)s.%(funcName)s # %(message)s")
else:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s # %(message)s")

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(fmt)


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL")))
    logger.addHandler(stream_handler)

    if not os.getenv("DEBUG") == 'true' and os.getenv("LOG_FILE") is not None:
        file_handler = logging.FileHandler(os.path.join(os.getenv("LOG_DIR"), os.getenv("LOG_FILE")))
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    logger.debug("Logging initialized")
    return logger
