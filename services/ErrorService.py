from .LoggerService import LogLevel, TagLevel, logger


class BackupError(Exception):
    def __init__(self, message: str, tag: TagLevel, severity:LogLevel = LogLevel.ERROR):
        self.message = message
        self.severity = severity
        self.tag = tag
        super().__init__(message)

    def log_error(self):
        logger.log(
            text=self.message,
            level=self.severity,
            tag=self.tag,
        )
