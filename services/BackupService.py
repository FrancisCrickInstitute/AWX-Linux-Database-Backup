import os
import subprocess
import time
import traceback
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Union

import config_backup as config
from services import utils
from services.DodService import fail_all_databases, log_backup_event
from services.EmailService import send_email
from services.ErrorService import BackupError
from services.LoggerService import TagLevel, logger, LogLevel

_tag = TagLevel.BACKUP


def _wait_for_writable_fs(
        fs_dir: str = config.backup_folder,
        poll_interval: float = 10.0,
        timeout: Union[float, None] = 60 * 60,
):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            count = 0
            start = time.time()
            path = Path(fs_dir).absolute()

            if not path.exists():
                raise BackupError(
                    message=f"path '{path}' does not exist on filesystem",
                    tag=_tag
                )

            while not os.access(path, os.W_OK):
                count += 1
                logger.log(f"Waiting for {path} to be writable...({count})")
                if timeout is not None and (time.time() - start) > timeout:
                    raise TimeoutError(f"Request Timed out: Path not writable: {path}")
                time.sleep(poll_interval)
            logger.log(f"{path} is writable", tag=_tag, level=LogLevel.INFO)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _execute_backup_command(database, backup_command):
    """
    Backup function that encapsulates reusable logic for MySQL and Postgres.
    """
    start_time = time.time()
    try:
        logger.log(backup_command, tag=_tag)
        subprocess.check_output(backup_command,
                                shell=True,
                                stderr=subprocess.STDOUT)
        log_backup_event(database, True, start_time)
        logger.log(f'Backup finished for {database}', tag=_tag, level=LogLevel.INFO)
    except subprocess.CalledProcessError as e:
        err_reason = e.stdout.decode("utf-8")
        logger.log(f'backup failed for {database}: {err_reason}', tag=_tag, level=LogLevel.WARNING)
        log_backup_event(database, False, start_time)
        send_email(f"Backup failed for database {database}",
                   body=f"{e.cmd}\n{err_reason}")


def _run_mysql_backup():
    """
    Backup function for MySQL.
    Will backup all databases on the server.
    Databases in config_backup.to_omit will be omitted
    """

    # get list of all dbs to backup
    directory = config.backup_folder
    today = utils.get_date()

    try:
        list_output = subprocess.check_output('mysql -Bse "SHOW DATABASES"', shell=True,
                                              stderr=subprocess.STDOUT)
        database_list = list_output.decode("utf-8").splitlines()
        # remove any unwanted dbs
        for unwanted_db in config.to_omit:
            logger.log(f'Database {unwanted_db} will be ignored', tag=_tag)
            database_list.remove(unwanted_db)
        logger.log(f"Databases: {database_list}\n", tag=_tag)

        if not database_list:
            logger.log("Database list is empty", tag=_tag)
            return

        for database in database_list:
            backup_command = f'''/usr/bin/mysqldump --single-transaction --routines {database} > {directory}{today}-{database}.sql'''
            _execute_backup_command(database, backup_command)

    except subprocess.CalledProcessError as e:
        err_reason = e.stdout.decode("utf-8")
        logger.log('Failed to retrieve database list. mysql service not running', tag=_tag)
        send_email(f"Backup failed on {config.managed_volume_name}, Service is not running", body=f"{e.cmd}\n{err_reason}")
        fail_all_databases()



def _run_postgres_backup():
    directory = config.backup_folder
    today = utils.get_date()

    if config.to_include:
        logger.log('Started backup only on databases in include list', tag=_tag)
        for database in config.to_include:
            backup_command = f'pg_dump -U DDpostgres -c -F p {database} > {directory}{today}-{database}.sql'
            _execute_backup_command(database, backup_command)
    else:
        # get db list
        list_output = subprocess.check_output(
            'psql -d postgres -U DDpostgres -At -c "select datname from pg_database where not datistemplate and datallowconn;"',
            shell=True, stderr=subprocess.STDOUT)
        # Transform the query result in a python list
        database_list = list_output.decode("utf-8").splitlines()
        for database in database_list:
            if database in config.to_omit:
                logger.log(f'Database "{database}" will be ignored', tag=_tag)
            else:
                backup_command = f'pg_dump -U DDpostgres -c -F p {database} > {directory}{today}-{database}.sql'
                _execute_backup_command(database, backup_command)



def _run_mongo_backup():
    pass


def get_neo4j_pid():
    try:
        # If shell execution is not necessary, split the command into parts
        output = subprocess.check_output(['/bin/neo4j', 'status'], stderr=subprocess.STDOUT).decode('utf-8')
        logger.log(str(output), tag=_tag)
        return 1
    except subprocess.CalledProcessError as e:
        # This captures the case where the neo4j status command fails
        logger.log("Neo4j is not running", tag=_tag)
        return 0


def neo4j_process(status):
    command = f"sudo /bin/neo4j {status}"
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT).decode('ascii')
        logger.log(f"{status} command output: {str(output)}", tag=_tag)
    except:
        logger.log(f"It is not possible to {status} the process.", tag=_tag)


def _run_neo4j_backup():
    dbs = ('neo4j', 'system')
    directory = config.backup_folder
    today = utils.get_date()
    current_database = None
    start_time = time.time()
    try:
        my_pid = get_neo4j_pid()
        logger.log(f"The PID is: {my_pid}", tag=_tag)
        neo4j_process('stop')
        for db in dbs:
            current_database = db
            backup_command = f"sudo -u neo4j /bin/neo4j-admin database dump --overwrite-destination=true --to-path={directory.rstrip('/')} {db}"
            _execute_backup_command(db, backup_command)

            # Rename File from <database>.dump to <YYMMDD>-<database>.dump
            # Because _delete_old_backups function needs that naming convention
            current_file = Path(f"{directory}{db}.dump")
            current_file.rename(f"{directory}{today}-{db}.dump")

    except subprocess.CalledProcessError as e:  # Check error and update the log file and sent an email
        err_reason = e.stdout.decode("utf-8")
        logger.log(f'backup failed for {current_database}: {err_reason}', tag=_tag, level=LogLevel.WARNING)
        log_backup_event(current_database, False, start_time)
        send_email(f"Backup failed for database {current_database}",
                   body=f"{e.cmd}\n{err_reason}")
    finally:
        neo4j_process('start')
        my_pid = get_neo4j_pid()
        logger.log(f"The PID is: {my_pid}", tag=_tag)


def _delete_old_backups():
    logger.log(
        text="Deleting old backup files...",
        tag=_tag
    )

    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    found_yesterday_backup = False

    for file in Path(config.backup_folder).rglob("*.*"):
        if file.name.startswith(yesterday_date):
            found_yesterday_backup = True

        logger.log(f"Deleting {file.name}...", tag=_tag)
        file.unlink()

    if not found_yesterday_backup:
        email_message = f"Old backup not found for {config.managed_volume_name}"
        send_email(title="Old backup not found", body=email_message, e_type="info")

    logger.log(
        text="Deleted old backup files",
        tag=_tag
    )


_SUPPORTED_TECH = {
    "mysql": {
        "name": "MySQL",
        "backup_function": _run_mysql_backup,
    },
    "postgres": {
        "name": "PostgreSQL",
        "backup_function": _run_postgres_backup,
    },
    "mongodb": {
        "name": "MongoDB",
        "backup_function": _run_mongo_backup,
    },
    "neo4j": {
        "name": "Neo4j",
        "backup_function": _run_neo4j_backup,
    },
}


@_wait_for_writable_fs()
def run_backup():
    try:
        server_key = config.data_server
        technology = _SUPPORTED_TECH.get(server_key)

        if technology is None:
            raise BackupError(
                message=f"Data server '{server_key}' is not supported",
                tag=_tag
            )

        # DELETE OLD BACKUP FILES IF ANY
        _delete_old_backups()

        technology_name = technology["name"]
        backup_fn = technology["backup_function"]

        logger.log(
            text=f"Starting Backup Service for {technology_name} databases...",
            level=LogLevel.INFO,
            tag=_tag
        )

        backup_fn()

        logger.log(
            text=f"Finished Backup Service for {technology_name} databases",
            level=LogLevel.SUCCESS,
            tag=_tag
        )
    except subprocess.CalledProcessError as ex:
        fail_all_databases()
        err_reason = ex.stdout.decode("utf-8")
        error_message = f"Command that failed: {ex.cmd}\Reason: {err_reason}"
        raise BackupError(
            message=f"Backup Error Found on {config.managed_volume_name}:{error_message}",
            tag=_tag
        )
    except Exception as ex:
        fail_all_databases()
        raise BackupError(
            message=f"Backup Error Found on {config.managed_volume_name}:{ex}",
            tag=_tag
        )
