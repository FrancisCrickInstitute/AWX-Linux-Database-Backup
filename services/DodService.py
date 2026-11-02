import os.path
import shutil
import socket
import time
from typing import Union

import requests
from requests.exceptions import ConnectionError

import config_backup as config
from services import utils
from services.ErrorService import BackupError
from services.EmailService import send_email
from services.LoggerService import logger, TagLevel, LogLevel

_tag = TagLevel.DOD


def _call(
        url: str,
        payload: dict
):
    dod_url = f"https://database-of-databases.thecrick.org/api/{url}"
    # dod_url = f"https://database-of-databases.dev.thecrick.org/api/{url}"
    headers = {
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(
            url=dod_url,
            headers=headers,
            json=payload,
        )

        response = resp.json()
        message = response['message']
        if response['status'] != 'success':
            raise BackupError(message, tag=_tag)
        logger.log(text=f"{message}", tag=_tag)

    except ConnectionError:
        err_message = f"Couldn't establish a connection with {dod_url}"
        raise BackupError(message=err_message, tag=_tag)
    except Exception as e:
        raise BackupError(message=str(e), tag=_tag)


def fail_all_databases():
    try:
        hostname = socket.gethostname()
        timestamp = int(time.time())
        payload = {hostname: hostname, timestamp: timestamp}
        _call(url="fail_all_backups_for_vm", payload=payload)
    except Exception as e:
        err_message = f"Failed to fail all databases on DOD: {e}"
        logger.log(text=err_message, tag=_tag, level=LogLevel.WARNING)
        send_email(title=f"DOD exception", body=err_message, e_type="warning")


def log_backup_event(
        db_name: str,
        success_flag: bool,
        start_time: Union[int, float],
):
    try:
        hostname = socket.gethostname()

        db_tech = (
            utils.check_mariadb()
            if config.data_server == "mysql"
            else config.data_server
        )

        total, used, free = shutil.disk_usage(config.backup_folder)

        end_time = time.time()
        duration = int(end_time - start_time) if success_flag else 0

        file_path = os.path.join(
            config.backup_folder,
            f"{utils.get_date()}-{db_name}.sql"
        )

        dump_size = 0
        if success_flag and os.path.exists(file_path):
            dump_size = os.path.getsize(file_path)

        payload = {
            "host": hostname,
            "db_technology": db_tech,
            "db_name": db_name,
            "succeeded": success_flag,
            "timestamp": start_time,
            "duration": duration,
            "backup_size": dump_size,
            "managed_volume_size": total,
            "managed_volume_free": free,
        }

        _call(url="create_backup", payload=payload)
    except Exception as e:
        err_message = f"Failed to create backup for {db_name} on DOD: {e}"
        logger.log(text=err_message, tag=_tag, level=LogLevel.WARNING)
        send_email(title=f"DOD exception", body=err_message, e_type="warning")
