import logging
import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = 'aifridgechef'

default_log_args = {
    'level': logging.DEBUG if int(os.getenv('DEBUG', '0')) else logging.INFO,
    'format': '%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s',
    'datefmt': '%d-%b-%y %H:%M:%S',
    'force': True,
}
logging.basicConfig(**default_log_args)
logger = logging.getLogger(PROJECT_NAME)

# disable 3rd party logs
LOGGERS_TO_DISABLE = [
]
for logger_name in LOGGERS_TO_DISABLE:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL + 1)
