from config_backup import *
import subprocess
import smtplib
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import os
import re
import signal

def send_error_pretty(server_name, subject, sender, recipient, title, message):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] =  subject
        msg['From'] = sender
        msg['To'] = recipient

        text = ""
        html = """\
         <html>
           <head></head>
           <body>
             <p style="color: orange; font-size:1.3em;">SERVER: """ + server_name + """</p>
             <hr style="border-top: 1px solid #f2f0f0;;">
             <p style="color: #660b25; font-size:1.2em;">""" + title + """ </p>
             <pre style="color: #ba4834; font-size:0.8em; padding:15px; background-color: #f5f5f5; border-radius:7px;">""" + message +  """ </pre>
             <p style="color: orange; font-size:1.2em;"> </p>
             <a style="color: #7dc7c9; font-size:1em;" href="https://database-of-databases.thecrick.org/{}" >""".format(server_name) + server_name + """ on DOD</a><br>
             <a style="color: #7dc7c9; font-size:1em;" href="https://splunk.thecrick.org:8000/en-GB/app/CRICK_SEARCH_DATABASE/unix_vm_overview?form.host_input={}" >""".format(server_name) + server_name + """ on Splunk</a><br>            
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
        print("error: failed to send email to "+sender)

def check_db_ver(server):
    if server == 'postgres':
        version = subprocess.getoutput('psql -d postgres  -U DDpostgres -At -c "select version();"')
        technology = 'PostgreSQL'
    else:
        version = subprocess.getoutput('mysql -V')
        check_server = re.search("MARIADB", str(version).upper())
        if check_server:
            technology = 'MariaDB'
        else:
            technology = 'MySQL'
    return version, technology




def find_value(my_value):
    matches = ["POSTGRES", "MYSQL", "MARIA",'DB','SQL','DATABASE']
    # All Value in Matches must be in Upper 
    if any([x in my_value.upper() for x in matches]):
        value = True
    else:
        value = False
    return value

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Function timed out.")


def check_update():
    output = subprocess.getoutput('yum check-update')
    new_message = ''
    for line in output.split('\n'):
        exist = find_value(line)
    if exist:
        new_message = new_message + str(line) + '\n'
    if len(new_message) > 0:
        tit = "OS Yum patches for " + str(check_db_ver(data_server)[1]) + " on " + str(os.uname()[1])
        sub = 'The following Yum updates will be applied on '+ str(os.uname()[1]) + ' at the next OS patching schedule. Please check for any possible issues.'
        msg = 'Current database version: ' + str(check_db_ver(data_server)[0]) + '\n\n' + new_message 
        servername = str(os.uname()[1])
        send_error_pretty(servername, tit, emailfrom, emailto,  sub, msg)
        #print(sub)
        #print(msg)
        print('Found database update: I will send an alert')
    else:
        print("No database update found: I will not send any alert.")


# Set the signal handler
signal.signal(signal.SIGALRM, timeout_handler)
# Set the timeout value to 5 seconds
signal.alarm(60)

try:
    # Call the function that may take too long
    check_update()
except TimeoutException as e:
    print(str(e))
    version,technology = check_db_ver(data_server)
    print(version)
    print(technology)
    servername = str(os.uname()[1])
    print(servername)
    tit = "YUM-UPDATE: Not Possible to check update for " + str(check_db_ver(data_server)[1]) + " on " + str(os.uname()[1])
    sub = 'Please  manually check ' + servername + ' or contact SysAdmin'
    msg = 'Current database version: ' + str(check_db_ver(data_server)[0]) + '\n\n' + sub    
    send_error_pretty(servername, tit, emailfrom, emailto,  sub, msg)   
else:
    # Cancel the timer if the function completes successfully
    signal.alarm(0)
