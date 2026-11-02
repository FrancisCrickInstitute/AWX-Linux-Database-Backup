import os
import time
from enum import Enum
from pathlib import Path
from services import utils


class TagLevel(Enum):
    DEFAULT = "LoggerService"
    RUBRIK = "RubrikService"
    DOD = "DODService"
    EMAIL = "EmailService"
    BACKUP = "BackupService"
    MAIN = "MainService"


class LogLevel(Enum):
    TRACE = "TRACE"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class BColours(Enum):
    """
    Colors for the CLI
    """
    TRACE = "\033[90m"  # grey
    INFO = "\033[94m"  # skyblue
    WARNING = "\033[93m"  # amber (yellow)
    ERROR = "\033[91m"  # rose (red/pinkish)
    SUCCESS = "\033[92m"  # emerald (green)
    RESET = "\033[0m"  # reset to default


class _LoggerService:
    def __init__(self):
        self.start_time = time.time()
        self.directory = "logs"
        self._current_log_file = None

    def delete_old_logs(self):
        self.log(f"Deleting old Log Files...")
        THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60
        files_to_delete = []
        for root, dirs, files in os.walk(self.directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if self.start_time - file_mtime > THIRTY_DAYS_SECONDS:
                        files_to_delete.append(file_path)
                except Exception as e:
                    raise e

        if len(files_to_delete) == 0:
            self.log(f"No Log Files Deleted")
        else:
            for file_path in files_to_delete:
                self.log(f"Deleting Log File: {file_path}")
                Path(file_path).unlink()

    def initiate_log(self):
        start_date = utils.get_date(self.start_time)
        path = Path(f"{self.directory}/{start_date}.log")
        self._current_log_file = path

        if path.exists():
            self.log(f"Writing to existing Log File: {path}", level=LogLevel.INFO)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"Initialising Log File: {path}", level=LogLevel.INFO)

        start_time_formated = utils.get_date(
            timestamp=self.start_time,
            time_format='%I:%M %p'
        )
        self.log(
            text=f"Backup Started at {start_time_formated}",
            level=LogLevel.INFO
        )

    def log(self, text: str, level: LogLevel = LogLevel.TRACE, tag: TagLevel = TagLevel.DEFAULT):
        log_text = _generate_log_message(text, level.value, tag.value)
        with open(self._current_log_file, "a") as log_file:
            log_file.write(f"{log_text}\n")
        _console(log_text, level)


def _generate_log_message(text: str, level: str, tag: str, ) -> str:
    timestamp = utils.get_date(
        timestamp=time.time(),
        time_format="%Y-%m-%d %H:%M:%S"
    )
    return f"[{timestamp}] [{level}] [{tag}] {text}"


def _console(text: str, level: LogLevel):
    level_value = level.value
    colour = BColours[level_value].value
    color_text = f"{colour}{text}{BColours.RESET.value}"
    print(color_text)


logger = _LoggerService()
