#!/usr/bin/python3

import traceback
from dataclasses import dataclass
from typing import NoReturn
import os
import sys
import subprocess

##################### CONFIG #######################

config = {
    "win11-2": {
        "conditional": [
            {
                "when": "/devices/pci0000:00/0000:00:02.1/0000:03:00.0/0000:04:0c.0/0000:0e:00.0/usb1/1-2",  # hub
                "then": [
                    "/devices/pci0000:00/0000:00:02.1/0000:03:00.0/0000:04:0c.0/0000:0e:00.0/usb1/1-2/1-2.4/1-2.4.1",  # mouse
                    "/devices/pci0000:00/0000:00:02.1/0000:03:00.0/0000:04:0c.0/0000:0e:00.0/usb1/1-2/1-2.4/1-2.4.2",  # keyboard
                ],
            }
        ]
    }
}

debug = False
debug_file = None
# debug_file = "/var/log/autousb.log"

###################### CODE ########################


@dataclass
class Mount:
    devpath: str
    busnum: int
    devnum: int


def dbg(msg):
    global debug
    if debug:
        print(msg, file=sys.stderr)

    if debug_file:
        with open(debug_file, "a") as f:
            f.write(msg + "\n")


def skip_attaching() -> NoReturn:
    dbg("--- SKIPPED ---")
    sys.exit(0)


def fail() -> NoReturn:
    dbg("--- FAILED ---")
    sys.exit(2)


# identify action and actual device added


def get_action():
    action = os.getenv("ACTION") or ""
    if action == "":
        print("Unsupported ACTION: " + action)
        fail()

    if action == "add":
        dbg("attaching device")
        op = "attach-device"
    elif action == "remove":
        dbg("detaching device")
        op = "detach-device"
    else:
        dbg("Unsupported ACTION: " + action)
        skip_attaching()

    return op


def skip_non_usb_subsystems():
    subsystem = os.getenv("SUBSYSTEM") or ""
    if subsystem != "usb":
        dbg("don't care about SUBSYSTEM: " + subsystem)
        skip_attaching()


def get_busnum():
    busnum = os.getenv("BUSNUM") or ""
    if busnum == "":
        dbg("BUSNUM is null")
        skip_attaching()
    return int(busnum)


def get_devnum():
    devnum = os.getenv("DEVNUM") or ""
    if devnum == "":
        dbg("DEVNUM is null ")
        skip_attaching()
    return int(devnum)


def get_devpath():
    devpath = os.getenv("DEVPATH") or ""
    if devpath == "":
        dbg("don't care about DEVPATH: " + devpath)
        skip_attaching()
    return os.path.realpath(devpath)


def skip_hubs(devpath: str):
    hub_search = ["ID_MODEL", "ID_MODEL_FROM_DATABASE"]
    for s in hub_search:
        if "hub" in (os.getenv(s) or "").lower():
            dbg("don't care about USB hubs: " + devpath)
            skip_attaching()


def devpath_busnum(devpath: str) -> int:
    lsusb_dev = devpath.split("/")[-1]
    busnum = int(lsusb_dev.split("-")[0])
    return busnum


def devpath_devnum(devpath: str) -> int | None:
    lsusb_p = subprocess.Popen(["lsusb", "-tvv"], stdout=subprocess.PIPE)
    lsusb_p.wait()

    if lsusb_p.stdout and lsusb_p.returncode == 0:
        lsusb_r = lsusb_p.stdout.readlines()
        lsusb_dev = devpath.split("/")[-1]
        try:
            matched = next(l.decode() for l in lsusb_r if lsusb_dev in l.decode())
            return int(matched.strip().split("/")[-1])
        except StopIteration:
            dbg("Could not detect devnum for " + devpath)
            return None

    dbg("Could not detect devnum")
    fail()


def find_domain_with_devpaths(
    config: dict, devpath: str, default_busnum: int, default_devnum: int
) -> tuple[str, list[Mount]]:
    found_domain = ""
    devpaths = []

    for domain, ports in config.items():
        for port in ports.get("devices", []):
            if port != devpath and (port + "/") not in devpath:
                continue
            # If device path does match, but there are sub devices available
            # ignore this device (don't pass through a USB hub itself, causes problems)
            found_domain = domain
            devpaths.append(devpath)
            return (found_domain, [Mount(devpath, default_busnum, default_devnum)])

        for condition in ports.get("conditional", []):
            if "when" in condition and "then" in condition:
                port = condition["when"]
                port_devpaths = condition["then"]

                if port != devpath and (port + "/") not in devpath:
                    continue
                # If device path does match, but there are sub devices available
                # ignore this device (don't pass through a USB hub itself, causes problems)
                found_domain = domain
                try:

                    result_mounts = []
                    for devpath in port_devpaths:
                        devnum = devpath_devnum(devpath)
                        if devnum is None:
                            dbg("Could not detect devnum for " + devpath)
                            continue
                        result_mounts.append(
                            Mount(devpath, devpath_busnum(devpath), devnum)
                        )

                    return (
                        found_domain,
                        result_mounts
                    )
                except Exception as e:
                    dbg("Exception: " + str(e.args))
                    dbg(traceback.format_exc())
                    fail()

    dbg("udev event doesn't match any device in config")
    skip_attaching()


def main():

    dbg("")
    dbg("--- BEGIN ---")
    action = get_action()
    busnum = get_busnum()
    devnum = get_devnum()
    devpath = get_devpath()

    skip_hubs(devpath)
    skip_non_usb_subsystems()

    (domain, mounts) = find_domain_with_devpaths(config, devpath, busnum, devnum)

    for mount in mounts:
        dbg(
            "busnum={} devnum={} devpath={}".format(
                mount.busnum, mount.devnum, mount.devpath
            )
        )

        device_xml = '<hostdev mode="subsystem" type="usb"><source><address bus="{}" device="{}"/></source></hostdev>'
        device_xml = device_xml.format(mount.busnum, mount.devnum)

        virsh = subprocess.Popen(
            ["virsh", action, domain, "/dev/stdin"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        virsh.communicate(input=device_xml.encode("ascii"))
        result = virsh.wait()

        if result != 0:
            dbg(f"virtsh failed for device {mount.devpath} with code: {result}")

    dbg("--- SUCCESS ---")


# find domain for current device


# tell libvirt to attach/detach device

if __name__ == "__main__":
    main()
