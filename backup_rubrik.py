from services import RubrikService
from services import BackupService
from services import EmailService
from services.ErrorService import BackupError
from services.LoggerService import logger, LogLevel, TagLevel


def main():
    try:
        # 1. CREATE NEW LOG FILE
        logger.initiate_log()

        # 2. REMOVE LOGS OLDER THAN 30 DAYS
        logger.delete_old_logs()

        # 3. GET RUBRIK TOKEN
        RubrikService.get_access_token()

        # 4. BEGIN RUBRIK SNAPSHOT
        RubrikService.begin_snapshot()

        # 5. RUN BACKUP JOB
        BackupService.run_backup()

    except BackupError as ex:
        ex.log_error()
        title, body = ex.message.split(":", 1)
        EmailService.send_email(title=title, body=body)
    except Exception as ex:
        title, body = str(ex).split(":", 1)
        logger.log(
            text=f"Exception: {ex}",
            level=LogLevel.ERROR,
            tag=TagLevel.MAIN,
        )
        EmailService.send_email(
            title=title,
            body=body
        )
    finally:
        # 6. CLOSE RUBRIK CONNECTION
        RubrikService.end_snapshot()

        # 7. DELETE RUBRIK TOKEN
        RubrikService.delete_access_token()


if __name__ == "__main__":
    main()
