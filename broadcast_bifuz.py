#!/usr/bin/env python

# Broadcast bifuz.
#
# Copyright (C) 2015 Intel Corporation
# Author: Andreea Brindusa Proca <andreea.brindusa.proca@intel.com>
# Author: Razvan-Costin Ionescu <razvan.ionescu@intel.com>
#
# Licensed under the MIT license, see COPYING.MIT for details

import os, sys
import re
import multiprocessing
from common import *


def parse_logcat(ip, log_filename):
    root_index = log_filename.rfind('/')
    root_path = log_filename[:root_index]
    with open(log_filename, 'r') as logcat:
        error = False
        package_name = ''
        new_name = ''
        for line in logcat:
            if line.startswith('F/BIFUZ'):
                m = re.search("F/BIFUZ_.* -n (.*)\/.*\.(.*\..*)", line)
                try:
                    package_name = m.group(1)
                    broadcast_to = m.group(2).strip()
                except:
                    pass
            elif "Caused" in line:
                error = True
                m = re.search(".* Caused by\: (.*)\:.*", line)
                try:
                    new_name = m.group(1)
                except:
                    pass
    if not error:
        os.remove(log_filename)
        return False
    if package_name and new_name:
        new_filename = root_path + "/" + broadcast_to + "." + new_name
        new_name = new_name.replace('!@#$%^&*()[]{};:,/<>?\|`~-=_+', '')
        os.rename(log_filename, new_filename + ".txt")
    return True


def parse_receiver_resolver(data, package_name):
    index_resv = data.find("Receiver Resolver Table")
    if index_resv == -1:
        return True
    data = data[index_resv:]

    data = data.split("\r\n")
    while_lines = [i for i in range(len(data)) if data[i] == '']
    data = data[:while_lines[1]]
    package_list = []

    for i in range(len(data)):
        m = re.search("\d+\w+\s(.*)\sfilter", data[i])
        try:
            part_line = m.group(1)
        except:
            continue

        part_line = part_line.replace('/.', '.')
        index_sl = part_line.find('/')
        if index_sl != -1:
            part_line = part_line[index_sl+1:]
        package_list.append(part_line)

    package_list = sorted(set(package_list))
    packages_broadcast[package_name] = package_list
    return True


def create_run_file(ip, log_dir):
    if ("." in ip):
        run_cmnd = 'adb -s %s:5555'%(ip)
    else:
        run_cmnd='adb -s %s'%(ip)

    with open(log_dir + '/all_broadcasts_' + ip + '.sh', 'w') as f:
        for k in packages_broadcast.keys():
            for val in packages_broadcast[k]:
                f.write(run_cmnd + ' shell am broadcast -n '+ k + '/' +val + '\n')
    return True


def start_broadcast_fuzzer(ip, log_dir):
    if not os.path.isfile(log_dir + '/all_broadcasts_' + ip + '.sh'):
        print "The broadcast calls were not generated!"
        return False

    with open(log_dir + '/all_broadcasts_' + ip + '.sh', 'r') as f:
        run_inadb(ip, "logcat -c")
        i = 0
        for line in f:
            # clean logcat
            log_in_logcat(ip, 'BIFUZ_BROADCAST ' + line)
            os.system(line)

            log_filename = "%s/testfile_%s_%d.txt"%(log_dir, ip, i)
            run_result = run_inadb(ip, 'logcat -d > ' + log_filename)
            if run_result == "Unavailable device.":
                print "Unavailable device: " + ip + ". Stop."
                return False

            resp_parse = parse_logcat(ip, log_filename)
            if not resp_parse:
                print "Device not found: " + ip + ". Stop!"
                return False

            run_inadb(ip, "logcat -c")
            i = i + 1
    os.system("rm " + log_dir + "/package_*")
    return True


def get_broadcast(ip, log_dir, selected_packages):

    lines = get_package_list(ip, log_dir, selected_packages)
    if not lines:
        log_in_logcat(ip, 'BIFUZ_INTENT no valid packages. STOP!')
        return False

    global packages_broadcast
    packages_broadcast = {}

    for line in lines:
        line = line.replace("package:", "")
        cmnd = "shell dumpsys package %s > %s/package_%s.txt"%(line, log_dir, line)
        print cmnd

        run_resp = run_inadb(ip, cmnd)
        if run_resp.startswith('error'):
            print run_resp
            continue

        with open(log_dir + "/package_" + line + ".txt", 'r') as outfile:
            data = outfile.read()
            parse_receiver_resolver(data, line)
    print packages_broadcast
    return create_run_file(ip, log_dir)


def generate_broadcast_intent(devices_list, selected_packages):

    #devices_list = get_devices_list()
    if not devices_list:
        print "*ERROR* unavailable devices"
        sys.exit(1)

    #ip = devices_list[0]

    map_logdirs = {}
    for h in devices_list:
        log_dir = set_logdir(h, "broadcast")
        map_logdirs[h] = log_dir

    jobs = []
    for h in devices_list:
        log_dir = map_logdirs[h]
        t = multiprocessing.Process(target=get_broadcast, args=(h, log_dir, selected_packages,))
        t.start()
        jobs.append(t)

    for b in jobs:
        b.join()

    jobs = []
    for h in devices_list:
        log_dir = map_logdirs[h]
        t = multiprocessing.Process(target=start_broadcast_fuzzer, args=(h, log_dir,))
        t.start()
        jobs.append(t)

    for b in jobs:
        b.join()