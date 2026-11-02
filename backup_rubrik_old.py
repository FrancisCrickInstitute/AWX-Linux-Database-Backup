#!/usr/bin/python3

# =============================================================
# LIBRARIES TO IMPORT
# =============================================================
import json  # the only library that need installed
import socket  # to check hostname
import subprocess
from subprocess import call
import os
import datetime
import re
import traceback
import urllib3
import smtplib
import email.utils
from email.mime.text import MIMEText
import time
import sys
import requests  # to connect to API
import shutil
from config_backup import *  # contain the configuration and changes fron postgres to mysql
from email.mime.multipart import MIMEMultipart
import random

get_mv_id = """
query mv_id ($objectType: [ObjectTypeEnum!]) {
  snappableConnection (filter: {objectType: $objectType}) {
    edges {
      node {
        fid
        name
        slaDomain {
          id
        }
      }
    }
  }
}"""


arg = sys.argv[1] if len(sys.argv) > 1 else None

def time_out(arg):
    """
    Determines the timeout value based on the provided argument.

    Args:
        arg (str or None): The argument to determine the timeout. If None, a random timeout between 60 and 300 seconds is generated.
                           If "--no-timeout", the timeout is set to 0.

    Returns:
        int: The determined timeout value in seconds.
    """
    if arg == None:
        time_out = random.randint(180,600)
        log('The back up will start in: ' + str(time_out) + ' seconds')
    elif arg == "--no-timeout" or arg == "-nt":
        log("No time out! Backup will start immediately")
        time_out = 0
    return time_out

# =============================================================
# CHECKING FOR OS UPDATE PENDING
# =============================================================
def exec_yum():
    now = datetime.datetime.now()
    day_of_week = now.weekday()
    if day_of_week == 6:
        result = subprocess.check_output('python3 check_update.py', shell=True, stderr=subprocess.STDOUT).decode('ascii')
    else:
        result = 'No pending update will be checked'    
    return result


# =============================================================
# DATABASE OF DATABASE API INTERFACE
# =============================================================

dod_url = "https://database-of-databases.thecrick.org/api/"


class bcolors:
    """
    Colors for the CLI
    """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def dod_call(url, params):
    """
    Generic function for API call to DOD API endpoints.
    This will handle errors and log relative messages.
    :param url:
    :param params:
    :return:
    """

    try:
        response = requests.request("POST", url, headers={}, data={}, params=params, verify=False)
    except:
        msg = 'Backup log to DOD failed. Unable to connection to DOD API from ' + managed_volume_name
        log(msg)
        send_error_pretty(managed_volume_name, emailfrom, emailto, msg, str(response))

    if response.status_code == 200:
        log('Backup logged in DOD for ' + params['host'] + " " + params['db_name'] + ". " + response.text)
    else:
        msg = 'Backup log in DOD failed for ' + params['host'] + ' ' + params['db_name'] + '. ' + 'API responded with code ' + str(response.status_code) + '. ' + response.text
        log(msg)
        subject = "Backup log in DOD failed " + managed_volume_name
        send_error_pretty(managed_volume_name, emailfrom, emailto, subject, msg)
    return


def dod_fail_all():
    """
    Fail all backups on a host. Used in case there is a host failure.
    :return:
    """

    fail_all_backups_url = dod_url + "fail_all_backups_for_vm"

    # host
    host = socket.gethostname()

    # current time
    bk_timestamp = int(time.time())

    params = {
            "host": host,
            "timestamp": bk_timestamp,
            }

    dod_call(fail_all_backups_url, params)
    return


def dod_log_backup(bk_start, dbname, succeeded):

    """
    Log a backup action to DOD
    :param bk_start:
    :param dbname:
    :param succeeded:
    :return:
    """

    managed_volume = backup_folder
    create_backup_url = dod_url + "create_backup"

    log('Get relevant information to log a backup action on DOD')

    # managed volume
    try:
        managed_volume_total, managed_volume_used, managed_volume_free = shutil.disk_usage(managed_volume)
    except:
        msg = 'Error: cant get managed_volume size'
        log(msg)
        send_error_pretty(managed_volume_name, emailfrom, emailto, msg, msg)
        return

    # host
    host = socket.gethostname()

    # current time
    now = int(time.time())

    # db tech
    database_technology = str(data_server)
    if database_technology == 'mysql':
        database_technology = check_mariadb()

    # backup size and duration
    backup_file = backup_folder + today() + '-' + dbname + ".sql"
    if succeeded:
        bk_size = os.path.getsize(backup_file)
        bk_duration = (now - bk_start)
    else:
        bk_size = 0
        bk_duration = 0

    params = {
            "host": host,
            "db_technology": database_technology,
            "db_name": dbname,
            "succeeded": str(succeeded),
            "timestamp": str(bk_start),
            "duration": str(bk_duration),
            "backup_size": str(bk_size),
            "managed_volume_size": str(managed_volume_total),
            "managed_volume_free": str(managed_volume_free),
            }

    dod_call(create_backup_url, params)
    return


# =============================================================
# CHECK IF IS MYSQL OR MARIADB
# =============================================================

def check_mariadb():
    myversion = subprocess.check_output('mysql -V', shell=True, stderr=subprocess.STDOUT)
    check_server = re.search("MARIADB", str(myversion).upper())
    if check_server:
        return 'mariadb'
    else:
        return 'mysql'


# =============================================================
# CREATE LOG FILE
# =============================================================
def log(text):
    print(f"{bcolors.HEADER}BACKUP >>>  {bcolors.ENDC}{bcolors.OKCYAN}" + text + f"{bcolors.ENDC}")
    text = str(datetime.datetime.now()) + ' | ' + text +'\n'
    file = today() + '-reference.log'
    f = open(file, "a")
    f.write(text)
    f.close


# =============================================================
# MANAGE EXISTING LOG FILE
# =============================================================
def manage_log():
    try:
        cwd = os.getcwd()
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        # craete log folder if not exit
        if not os.path.exists(str(cwd) + '/log'):
            os.makedirs(str(cwd) + '/log')
            log('Created New Directory ' + str(cwd) + '/log')
        old_logfile = (yesterday.strftime("%Y%m%d")) + '-reference.log'
        # move yesterday log
        mv_command = 'mv ' + cwd + '/' + old_logfile + ' ' + cwd + '/log 2>/dev/null'
        os.system(mv_command)
        log('Move ' + old_logfile + ' to the Log Folder')
        #delete logs older than 30 days
        delete_log = ' find ' + cwd + '/log/ -type f -mtime +30 -delete'
        os.system(delete_log)
        log('Delete logs older than 30 days')
    except:
        # send
        newmsg = 'Problem to manage Log file'
        subj = newmsg + ' on ' + managed_volume_name
        send_error_pretty(managed_volume_name, emailfrom, emailto, subj ,newmsg)
        #send_error(newmsg, managed_volume_name, emailfrom, emailto)


# =============================================================
# CREATE A PART OF FILE NAME
# DB file name format: yyyymmdd-DB_name.sql
# Log file name format: yyyymmdd-DB_name.sql
# =============================================================
def today():
    x = datetime.datetime.now()
    filename = (x.strftime("%Y%m%d"))
    return filename

# =============================================================
# OPEN RUBRIK CONNECTION
# =============================================================



# =============================================================
#CLOSE RUBRIK CONNECTION
# =============================================================

# =============================================================
# BACKUP MYSQL
# =============================================================
def mysql_backup(directory, partname):
    """
    Backup function for MySQL.
    Will backup all databases on the server.
    Databases in config_backup.to_omit will be omitted
    :param directory:
    :param partname:
    :return:
    """
    # get list of all dbs to backup
    database_list = []
    try:
        list_output = subprocess.check_output('mysql -Bse "SHOW DATABASES"', shell=True, stderr=subprocess.STDOUT).decode('ascii')
        list_output = list_output.strip()
        database_list = list_output.split('\n')
        # remove any unwanted dbs
        for unwanted_db in to_omit:
            log('Database ' + str(unwanted_db) + ' will be ignored')
            database_list.remove(unwanted_db)
        log("Databases: " + str(database_list) + "\n")
    except subprocess.CalledProcessError as e:
        log('Failed to retrieve database list. mysql service not running')
        subj = 'Backup failed on ' + managed_volume_name + ' Service is not running'
        error_message = 'Error Message: ' + str(e.output) + '\n'
        error_message += 'Error Number: ' + str(e.returncode) + '\n'
        error_message = 'Traceback:\n'
        error_message += str(traceback.format_exc()) + '\n'
        log(error_message)
        send_error_pretty(managed_volume_name, emailfrom, emailto, subj, error_message )
        #dod_fail_all()
        return

    # run the backups
    if not database_list:
        msg = "Database list is empty"
        log(msg)
        send_error(msg, managed_volume_name, emailfrom, emailto)
    else:
        for db in database_list:
            try:
                log("Running backup for '" + str(db) + "'")
                backup_command = '/usr/bin/mysqldump --single-transaction --routines ' + db + ' > ' + directory + partname + '-' + str(db) + '.sql'
                log(backup_command)
                bk_start = int(time.time())
                backup_process = subprocess.check_output(backup_command, shell=True, stderr=subprocess.STDOUT).decode('ascii')
                dod_log_backup(bk_start, db, True)
                log("Backup command output: " + str(backup_process))
                log("Backup completed\n")
            except subprocess.CalledProcessError as e:
                error_message = 'Error Message: ' + str(e.output) + '\n'
                error_message += 'Error Number: ' + str(e.returncode) + '\n'
                error_message = 'Traceback:\n'
                error_message += str(traceback.format_exc()) + '\n'
                log(error_message)
                dod_log_backup(bk_start, db, False)
                subject = "Failed to backup " + str(db)
                send_error_pretty(managed_volume_name, emailfrom, emailto,subject , error_message)


# =============================================================
# BACKUP POSTGRESQL
# =============================================================
def postgres_backup(directory, filetime):
    try:
        if not to_include:
            # get db list
            list_output = subprocess.check_output(
                'psql -d postgres  -U DDpostgres -At -c "select datname from pg_database where not datistemplate and datallowconn;"',
                shell=True, stderr=subprocess.STDOUT)
            # Transform the query result in a python list
            db_text = str(list_output)
            db_list = db_text.replace("b'", "")
            db_list = db_list.replace("'", "")
            database_list = db_list.split('\\n')
            for db in database_list:
                if len(db) > 0 and (str(db) not in to_omit):
                    backup_command = 'pg_dump -U DDpostgres -c -F p ' + db + '>' + directory + filetime + '-' + db + '.sql'
                    log(backup_command)
                    bk_start = int(time.time())
                    list_backup = subprocess.check_output(backup_command,
                                                          shell=True,
                                                          stderr=subprocess.STDOUT)
                    dod_log_backup(bk_start, db, True)
                    log(str(list_backup))
                    log('backup ok')

                else:
                    log('The database ' + str(db) + ' will be ignored')
        else:
            log('We Start to backup only the databases included tn the list')
            for db in to_include:
                backup_command = 'pg_dump -U DDpostgres -c -F p ' + db + '>' + directory + filetime + '-' + db + '.sql'
                log(backup_command)
                bk_start = int(time.time())
                list_backup = subprocess.check_output(backup_command,
                                                      shell=True,
                                                      stderr=subprocess.STDOUT)
                dod_log_backup(bk_start, db, True)
                log(str(list_backup))
                log('backup ok')
    except subprocess.CalledProcessError as e:  # Check error and update the log file and sent an email
        log('Backup failed!!!!')
        bk_start = int(time.time())
        #dod_fail_all()
        newmsg = 'BACKUP FAILED !!!<br><br><br>'
        newmsg = newmsg + 'Error Message: ' + str(e.output) + '\n'
        log('Error Message: ' + str(e.output))
        newmsg = newmsg + 'Error Number: ' + str(e.returncode) + '\n'
        log('Error Number: ' + str(e.returncode))
        log(str(e))
        tb = traceback.format_exc()
        newmsg = newmsg + str(tb) + '\n'
        # send_error(newmsg, managed_volume_name, emailfrom, emailto)
        subject = "ALERT BACKUP FAILED ON " + managed_volume_name.upper()
        msg = "Error returned:" + '<br><br>' + newmsg
        send_error_pretty(managed_volume_name, emailfrom, emailto, subject, msg)
        log('Alert Message sent ')
        log(str(tb))


#==============================================================
#      BACKUP MONGODB
#==============================================================

def backup_mongo(partname):
    # remove old backup
    try:
        today_date = datetime.date.today()
        yesterday = today_date - datetime.timedelta(days=1)
        old_filename = (yesterday.strftime("%Y%m%d"))
        delete_mold = 'rm -r ' + backup_folder + old_filename
        delete_all = 'rm -r -f '  + backup_folder + '202*'
        #print(delete_mold)
        delete_output = subprocess.check_output(delete_mold, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:  # Check error and update the log file and sent an email
        log('Failed to delete previous backup')
        newmsg = 'Failed to delete previous backup'
        newmsg = newmsg + 'Error Message: ' + str(e.output) + '\n'
        log('Error Message: ' + str(e.output))
        newmsg = newmsg + 'Error Number: ' + str(e.returncode) + '\n'
        log('Error Number: ' + str(e.returncode))
        log(str(e))
        tb = traceback.format_exc()
        newmsg = newmsg + str(tb) + '\n'
        send_error(newmsg, managed_volume_name, emailfrom, emailto)
        log('Alert Message sent ')
        log(str(tb))
    finally:
        list_backup = subprocess.check_output(delete_all, shell=True, stderr=subprocess.STDOUT)
        log('Maybe deleted extra old file')
    
    try:
        if not to_include:
            bk_command = "mongodump --out='" + backup_folder + partname + "'"
            #print(bk_command)
            mongo_output = subprocess.check_output(bk_command, shell=True, stderr=subprocess.STDOUT)
        else:
            for db in to_include:
                db_backup = "mongodump -d " + db + " --out='" + backup_folder + partname + "'"
                log(db_backup)
                mongo_output = subprocess.check_output(db_backup, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:  # Check error and update the log file and sent an email
        log('Failed to create MongoDB Backup')
        newmsg = 'Failed to create MongoDB Backup'
        newmsg = newmsg + 'Error Message: ' + str(e.output) + '\n'
        log('Error Message: ' + str(e.output))
        newmsg = newmsg + 'Error Number: ' + str(e.returncode) + '\n'
        log('Error Number: ' + str(e.returncode))
        log(str(e))
        tb = traceback.format_exc()
        newmsg = newmsg + str(tb) + '\n'
        send_error(newmsg, managed_volume_name, emailfrom, emailto)
        log('Alert Message sent ')
        log(str(tb))


# =============================================================
# DELETE OLD BACKUP FILES
# Option 1 - delete the previous day (error raised if failed)
# Option 2 - delete all files (no error raise)
# =============================================================
def delete_old():
    today_date = datetime.date.today()
    yesterday = today_date - datetime.timedelta(days=1)
    old_filename = (yesterday.strftime("%Y%m%d"))
    # delete_command = 'find ' + backup_folder + '* -maxdepth 0 -type f -delete'
    rm_yest = 'rm ' + backup_folder + old_filename + '*'
    delete_all = 'find ' + backup_folder + '* -maxdepth 0 -type f -delete'
    log('Start to delete old file backups File ')
    try:
        list_backup = subprocess.check_output(rm_yest,
                                              shell=True,
                                              stderr=subprocess.STDOUT)
        log('Deleted successful backup from ' + str(yesterday))

    except subprocess.CalledProcessError as e:
        log('Deletion Failed')
        newmsg = 'Deletion Failed\n'
        newmsg = newmsg + 'Error Message: ' + str(e.output) + '\n'
        log('Error Message: ' + str(e.output))
        newmsg = newmsg + 'Error Number: ' + str(e.returncode) + '\n'
        log('Error Number: ' + str(e.returncode))
        log(str(e))
        tb = traceback.format_exc()
        newmsg = newmsg + str(tb) + '\n'
        # send_error(newmsg, managed_volume_name, emailfrom, emailto)
        subject = 'Old backup not found for ' + managed_volume_name
        send_error_pretty(managed_volume_name, emailfrom, emailto, subject,  newmsg)
        log('Alert Message sent ')
        log(str(tb))
    finally:
        list_backup = subprocess.check_output(delete_all,
                                        shell=True,
                                        stderr=subprocess.STDOUT)
        log('Maybe deleted extra old file')


# =============================================================
# SEND ERROR VIA EMAIL
# send message error to dba-maint Team
# =============================================================
def send_error(msg_body, server_name, mfrom, mto):
    smtp_server = "smtp.thecrick.org"
    port = 25
    msg_from = mfrom
    msg_to = mto
    # Create the message
    msg = MIMEText(msg_body)
    msg['To'] = email.utils.formataddr(('dba-maint', mto))
    msg['From'] = email.utils.formataddr(('Backup Alert', mfrom))
    msg['Subject'] = 'Backup failed on ' + server_name

    try:
        server = smtplib.SMTP(smtp_server)
        # server.set_debuglevel(1)
        server.sendmail(msg_from, msg_to, msg.as_string())
    except Exception as e:
        log(e)
    finally:
        server.quit()


def send_error_pretty(server_name, sender, recipient, subjet, message):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subjet
        msg['From'] = sender
        msg['To'] = recipient

        text = ""
        html = """\
         <html>
           <head></head>
           <body>
             <p style="color: orange; font-size:1.3em;">SERVER: """ + server_name + """</p>
             <hr style="border-top: 1px solid #f2f0f0;;">
             <p style="color: #660b25; font-size:1.3em; margin-top:40px;">Backup alert!</p>
             <p style="color: #660b25; font-size:1.2em;">""" + subjet + """ </p>
             <pre style="color: #ba4834; font-size:0.8em; padding:15px; background-color: #f5f5f5; border-radius:7px;">""" + message + """ </pre>
             <p style="color: orange; font-size:1.2em;"> </p>
             <a style="color: #7dc7c9; font-size:1em;" href="https://database-of-databases.thecrick.org/{}" >""".format(server_name) + server_name + """ on DOD</a><br>
             <a style="color: #7dc7c9; font-size:1em;" href="https://splunk.thecrick.org:8000/en-GB/app/CRICK_SEARCH_DATABASE/unix_vm_overview?form.host_input={}" >""".format(server_name[0:15]) + server_name + """ on Splunk</a><br>            
             <a style="color: #7dc7c9; font-size:1em;" href="https://rubrik.thecrick.org/web/bin/index.html#/protection/managed_volume?tab=LegacyMv&name={}" >""".format(server_name) + server_name + """ on Rubrik</a>
             <p style="color: grey; font-size:0.6em; margin-top:30px;">Sent by backup script</p>
           </body>
         </html>
         """

        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        msg.attach(part1)  # text must be the first one
        msg.attach(part2)  # html must be the last one

        email_server = smtplib.SMTP("smtp.thecrick.org")
        email_server.sendmail(sender, recipient, msg.as_string())
        email_server.quit()

    except requests.ConnectionError:
        log("error: failed to send email to "+ sender)


# =============================================================
# LAST ERROR CHECK
# Currenty are supported only 'mysql' and 'postgres'
# =============================================================
def check_error():
    logfile_name = today() + '-reference.log'
    log('Start to check in the ' + logfile_name)
    to_check = open(logfile_name, "r")
    Lines = to_check.readlines()
    count = 0
    sunbj = 'Backup Error Found on ' + managed_volume_name
    bodymess = ''
    exclude_pattern = r"""Error Message: b'rm: cannot remove|Error Number: \d+|subprocess\.CalledProcessError|"rm:|rm:"""

    for line in Lines:
        if re.search(exclude_pattern, line):
            log('Line Excluded')
        elif re.search("error", line) or re.search("Error", line) or re.search("Error", line):
            bodymess = bodymess + line +'<br><br>'
            count = count + 1
    if count > 0 :
        send_error_pretty(managed_volume_name, emailfrom, emailto, sunbj,  bodymess)
        log(sunbj)
    else:
        log('EveryThing looks ok')
    

# =============================================================
# CHECK DATABASE TYPE
# Currenty are supported only 'mysql' and 'postgres'
# =============================================================
def check_db(version):
    if version == 'mysql':
        delete_old()
        log('Start to backup MySQL databases')
        mysql_backup(backup_folder, today())
    elif version == 'postgres':
        delete_old()
        log('Start to backup PostgreSQL databases')
        postgres_backup(backup_folder, today())
    elif version == 'mongodb':
        log('Start to backup MongoDB databases')
        print('Start to backup MongoDB databases')
        backup_mongo(today())
    elif version == 'filemaker':
        log('Start to backup Filemaker databases')
    else :
        log('This database option is not current supported')
        print('Database type not supported')
        body = 'Database not supported: ' + version
        send_error_pretty(managed_volume_name, emailfrom, emailto, managed_volume_name + ': Database type not supported',' This database option is not current supported' )
        #send_error(body, managed_volume_name, emailfrom, emailto)
        exit()


def get_access_token(auth_details):
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        "https://crick.my.rubrik.com/api/client_token",
        data=auth_details,
        headers=headers,
    )
    access_token = (json.loads(response.text)).get("access_token")
    if access_token:
        log("Access token generated.")
    else:
        log(response.raise_for_status())
        raise SystemExit(0)
    return access_token

def delete_session(access_token):
    headers = {"Authorization": "Bearer " + access_token}
    response = requests.delete(
        "https://crick.my.rubrik.com/api/session", headers=headers
    )
    if response.status_code == 204:
        log("Session deleted successfully.")

def query(access_token, query, variables={}):
    url = "https://crick.my.rubrik.com/api/graphql"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token,
    }
    data = {"query": query, "variables": variables}
    response = requests.post(url=url, headers=headers, data=json.dumps(data))
    query_output = response.content
    query_output_dict = json.loads(query_output.decode("utf8"))
    return query_output_dict


def get_mv_fid(access_token, mv_name):
    variables = {"objectType": "ManagedVolume"}
    query_output = query(access_token, get_mv_id, variables=variables)
    mv_list = query_output.get('data').get('snappableConnection').get('edges')
    mv_details = next((dict['node'] for dict in mv_list if dict['node']['name'] == mv_name), None)
    return mv_details



def beginsnapshot(token,fid):
    url = 'https://crick.my.rubrik.com/api/graphql'
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        "query": "mutation beginManagedVolumeSnapshot($id:String!){beginManagedVolumeSnapshot(input:{id:$id,config:{isAsync:true}}){snapshotId asyncRequestStatus{id}}}",
        "operationName": "beginManagedVolumeSnapshot",
        "variables": {"id": fid}
    }
    response = requests.post(url, headers=headers, json=data)
    # To print the response from the server
    return response.json()

def end_snapshot(token,my_fid,SLA_ID):
    url = 'https://crick.my.rubrik.com/api/graphql'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    data = {
        "query":"mutation endManagedVolumeSnapshot($id:String!,$slaId:String!){endManagedVolumeSnapshot(input:{id:$id,params:{isAsync:true retentionConfig:{slaId:$slaId}}}){asyncRequestStatus{id}}}",
        "operationName":"endManagedVolumeSnapshot",
        "variables":{"id":my_fid,"slaId":SLA_ID}
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# =============================================================
# EXECUTE THE BACKUPS
# =============================================================

log('New LOG file Created')
urllib3.disable_warnings()
REQ_DATA = json.dumps({"client_id": RSC_USER, "client_secret": RSC_SECRET})
manage_log()
TOKEN = get_access_token(REQ_DATA)
log(TOKEN)
mv_details = get_mv_fid(TOKEN, managed_volume_name)
log(str(mv_details))
FID = mv_details.get('fid')
log(FID)
SLA_ID = mv_details.get('slaDomain').get('id')
log(SLA_ID)


try: 
    begin_snap = beginsnapshot(TOKEN,FID)
    log(str(begin_snap))
except subprocess.CalledProcessError as e:
    log('Is not possible to open Managed volume: '+ str(e))
    send_error_pretty(managed_volume_name, emailfrom, emailto, managed_volume_name + ': Is Not possible to open Managed Volume ' ,str(e))
finally:
    try: 
        snapshot_id = begin_snap['data']['beginManagedVolumeSnapshot']['snapshotId']
    except:
        send_error_pretty(managed_volume_name, emailfrom, emailto, managed_volume_name + ': Managed Volume is already opened' ,str(begin_snap))

my_timeout = time_out(arg)
time.sleep(my_timeout)

check_db(data_server)

try:
    close_snap = end_snapshot(TOKEN,FID,SLA_ID)
    log(str(close_snap))
    id_value = close_snap['data']['endManagedVolumeSnapshot']['asyncRequestStatus']['id']
except subprocess.CalledProcessError as e:
    log('Not possible to close Manage Volume : '+ str(e))
    send_error_pretty(managed_volume_name, emailfrom, emailto, managed_volume_name + ': Not possible to close Manage Volume',str(e) )


try:
    log('Delete Token')
    delete_session(TOKEN)
    log("TOKEN DELETED")
except subprocess.CalledProcessError as e:
    log('Not possible to delete the TOKEN '+ str(e))

yum = exec_yum()
log(yum)
check_error()

log('Backup Completed')