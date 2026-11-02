import re
import subprocess
import time
from datetime import datetime
from typing import Union


def get_date(timestamp:Union[int, float]=time.time(), time_format: str = "%Y%m%d"):
    date = datetime.fromtimestamp(int(timestamp)).strftime(time_format)
    return date

def get_template():
    with open("email_templates/template.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return html_content

def check_mariadb():
    version = subprocess.check_output('mysql -V', shell=True, stderr=subprocess.STDOUT)
    check_server = re.search("MARIADB", str(version).upper())
    if check_server:
        return 'mariadb'
    else:
        return 'mysql'
    
def get_background_color(e_type):
    colour_scheme = {
        "success": "#4CAF50",
        "error": "#fb413d",
        "warning": "#f4ba46",
        "info": "#13b5f4",
    }
    return colour_scheme.get(e_type)