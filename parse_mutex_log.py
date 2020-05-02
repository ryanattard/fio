#!/usr/bin/env python

import json
import re
import sys
import multiprocessing
import subprocess
# There's 6 messages we're looking for
#          pid       function                          zone.start
# mutex    16884 zbd(zone_lock): Waiting for zone lock 193005092864
# mutex    16875 zbd(zone_lock): Took zone lock 193005092864
# mutex    16875 zbd(zbd_reset_zones): Released zone lock 193005092864
# mutex    16874 zbd(zbd_free_zone_info): Waiting for zoned device lock
# mutex    16874 zbd(zbd_free_zone_info): Took zoned device lock
# mutex    16874 zbd(zbd_free_zone_info): Released zoned device lock

# Suggested: grep -n "zoned device" if you are interested in that specific lock type.
ZONE_DEV_LOCK_RE = re.compile(
    r'.*mutex\W+(\d+)\W+zbd\((\w+)\): (.*) zoned device lock.*')
ZONE_LOCK_RE = re.compile(
    r'.*mutex\W+(\d+)\W+zbd\((\w+)\): (.*) zone lock (\d+).*')

WAITING = 'Waiting for'
TOOK = 'Took'
RELEASED = 'Released'

VALID_ACTIONS = (WAITING, TOOK, RELEASED)


def update_lock_state_machine(device_lock_state, pid, method, action):
    if action == TOOK:
        device_lock_state['holding'][pid] = method
        if pid in device_lock_state['waiting']:
            device_lock_state['waiting'].pop(pid)
    elif action == WAITING:
        device_lock_state['waiting'][pid] = method
    elif action == RELEASED:
        device_lock_state['holding'].pop(pid)
        if pid in device_lock_state['waiting']:
            device_lock_state['waiting'].pop(pid)


def generate_base_lock_state():
    return {
        'holding': {},
        'waiting': {},
    }


def parse_file(filename):
    device_lock_state = generate_base_lock_state()
    zone_lock_states = {}
    lineno = 0
    line_count = int(subprocess.check_output(
        ('wc', '-l', filename)).strip().split()[0])
    with open(filename) as fd:
        for line in fd:
            lineno += 1
            if lineno % 10**5 == 0:
                print('Completed {}/{} ({:.2f}%)'.format(lineno,
                                                         line_count,
                                                         100*float(lineno)/line_count))
            try:
                zone_dev_match = ZONE_DEV_LOCK_RE.match(line)
                if zone_dev_match:
                    pid, method, action = zone_dev_match.groups()
                    update_lock_state_machine(
                        device_lock_state, pid, method, action)
                    continue
                zone_lock_match = ZONE_LOCK_RE.match(line)
                if zone_lock_match:
                    pid, method, action, zno = zone_lock_match.groups()
                    if zno not in zone_lock_states:
                        zone_lock_states[zno] = generate_base_lock_state()
                        update_lock_state_machine(
                            zone_lock_states[zno], pid, method, action)
                    continue
            except Exception as ex:
                print("On line %s, there's some kind of problem: %s" %
                      (lineno, ex.message))
                print(line)
        return device_lock_state, zone_lock_states


def main():
    device_lock_state, zone_lock_states = parse_file(sys.argv[1])

    with open('zone_locks.json', 'w+') as fd:
        json.dump(
            {zno: zl for zno, zl in zone_lock_states.items() if zl['waiting']}, fd)
    with open('device_lock.json', 'w+') as fd:
        json.dump(device_lock_state, fd)
    return


if __name__ == '__main__':
    main()
