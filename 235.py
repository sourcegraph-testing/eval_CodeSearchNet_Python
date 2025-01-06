import psutil
import os
from datetime import *
from files import get_modification_datetime

def is_running(proc_name):
    output = os.popen("pgrep %s" % proc_name).readlines()
    if output:
        return True
    else:
        return False
def is_running_by_ps(command):
    output = os.popen("ps aux |grep '%s'|grep -v grep" % command).readline()
    return True if output else False

def get_creation_time(proc_name, proc_owner):
    pid = os.popen("pgrep -u %s %s" %(proc_owner, proc_name)).readline().strip()
    proc = psutil.Process(int(pid))
    return proc.create_time

def service_started(proc_name):
    process = os.popen('pgrep %s'%proc_name).readline()
    return True if process else False

def status_changed_recently(proc_name, reference_file=None, reference_proc=None, proc_owner=None):
    if reference_file:
        reference_time = get_modification_datetime(reference_file)
        start_time = get_creation_time(proc_name, proc_owner)
        delta = start_time - reference_time
        if delta > 0: # The reference file has been created before the processes started
            return True
        else:
            return False
    elif reference_proc:
        reference_time = get_creation_time(reference_proc, proc_owner)
        start_time = get_creation_time(proc_name, proc_owner)
        delta = start_time - reference_time
        if delta > 0:
            return True
        else:
            return False

def get_pid(PROCNAME):
    for proc in psutil.process_iter():
        if proc.name == PROCNAME:
            return proc.pid
        