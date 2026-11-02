# backup_rubrik.py

The Python script `backup_rubrik.py` automates the process of creating backups for different types of databases (MySQL, PostgreSQL, MongoDB), and manages backup logs and errors. Here's a step-by-step explanation:

## Imports and Configuration

It imports necessary libraries and configuration settings from `config_backup`.

## OS Update Check

Defines a function to check if OS updates are pending on Sundays.

## Database API Interface

Sets up for API calls to a Database of Databases (DOD) service, including logging backups, handling failed backups, and determining database specifics.

## Database Backup Functions

- **MySQL/MariaDB**: Backs up MySQL/MariaDB databases, excluding certain databases as defined.
- **PostgreSQL**: Backs up PostgreSQL databases, including or excluding specific databases based on configuration.
- **MongoDB**: Manages MongoDB backups, including deleting old backups and creating new ones.
- **Neo4J**: Manages Neo4j and Sys databases backups, including deleting old backups and creating new ones.
  
## Backup Management

- **Log Management**: Creates, manages, and rotates log files for tracking backup activities.
- **Old Backup Deletion**: Defines strategies for deleting old backup files, either from the previous day or all files.
- **Error Handling and Reporting**: Implements functions to send error reports via email, both in plain text and HTML formats.

## Utility Functions

Includes helpers for various tasks, like determining the day for file naming, checking if MySQL or MariaDB is used, and managing Rubrik snapshots for backups.

## Execution Flow

1. Disables warnings for unverified HTTPS requests.
2. Retrieves a token for authentication with the backup system.
3. Manages log files from previous runs.
4. Attempts to open a new snapshot for backup, logs the activity, and sends an alert if it fails.
5. Chooses the appropriate database backup function based on the database type (MySQL, PostgreSQL, MongoDB).
6. After backups, it checks for errors, attempts to close the snapshot, and deletes the authentication token.

This script is designed for robustness and error handling, using logging and email alerts to manage backup operations and failures.

