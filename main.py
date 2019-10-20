#!/usr/bin/python3
from pathlib import Path
from time import sleep, time
import subprocess
import logging
import pickle
import os
import re


CONSOLE_LOG_LEVEL = logging.WARNING
SLEEP_TIME = 0.1
MOUNT_POINT = "/mnt/4"
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.cr2')
MIN_IMAGE_SIZE = 300 * 1024


def create_log():
    global log
    log = logging.getLogger()
    h = logging.StreamHandler()
    h.setLevel(CONSOLE_LOG_LEVEL)
    fh = logging.FileHandler("main.log")
    f = logging.Formatter("%(asctime)s %(funcName)-20s %(levelname)-8s %(message)s")
    h.setFormatter(f)
    fh.setFormatter(f)
    log.addHandler(h)
    log.addHandler(fh)
    #log.setLevel(logging.DEBUG)


def ask_question(question: str, answers: list):
    """Asks a question until the user answers correctly given a set of answers."""
    default = ""
    for a in answers:
        if a.upper() == a:
            default = a
    while True:
        i = input("{} {}: ".format(question, answers.__str__().replace("'", "")))
        if i == "": i = default
        if i in answers:
            return i.lower()
        else:
            print("Invalid answer '{}'".format(i))


def list_devices(path: Path, recursive: bool) -> list:
    """Given a Path object this returns a list of Path objects for the files contained within."""
    devices = []
    for p in path.iterdir():
        if p.is_block_device():
            devices.append(p)


def get_disks() -> set:
    """Returns a set of Path objects for all the disks plugged in right now. IE all sd[a-z] block devices"""
    devs = set()
    for path in Path("/dev").iterdir():
        if path.is_block_device():
            if re.match("^sd[a-z]$", path.name):
                devs.add(path)
    return devs


def is_ntfs_partition(fdisk_line: str):
    if 'NTFS' in fdisk_line: return True
    if 'Microsoft basic data' in fdisk_line: return True
    return False


def get_ntfs_partitions(disk: Path) -> list:
    """Return a list of Paths pointing to the NTFS partitions of disk."""
    global log

    p = subprocess.run(['/usr/bin/fdisk', '-l', disk.__str__()], capture_output=True, timeout=10)
    output = p.stdout.decode()
    output = output.split('\n')
    partitions = tuple(filter(lambda x:x.startswith(disk.__str__()), output))
    log.debug("Found partitions {}".format(partitions))

    ntfs_parts = tuple(filter(lambda x:is_ntfs_partition(x), partitions))
    log.debug("Found NTFS partitions {}".format(partitions))

    ntfs_paths = map(lambda x:re.match('(/dev/sd[a-z][0-9]).*', x).group(1), ntfs_parts)
    ntfs_paths = tuple(map(lambda x:Path(x), ntfs_paths))
    log.debug("Extracted Paths for partitions {}".format(ntfs_paths))

    ntfs_paths = tuple(ntfs_paths)
    return ntfs_paths if len(ntfs_paths) > 0 else ()


def is_mounted(part: str=None, dest: str=None):
    assert part is not None or dest is not None

    p = subprocess.run(['/usr/bin/mount'], capture_output=True)
    out = p.stdout.decode()
    out = out.split('\n')
    for line in out:
        if dest is not None and part is not None:
            regex = "{} on {} .*".format(part, dest)
        elif part is None:
            regex = ".* on {} .*".format(dest)
        elif dest is not None:
            regex = "{} on .*".format(part)
        if re.match(regex, line):
            return True
    return False


def mount(part: str, dest: str) -> bool:
    """Mounts a partition at the dest folder. Returns true if it didn't mount correctly."""
    if is_mounted(dest=dest):
        answer = ask_question("{} is already mounted on {}, continue?".format(part, dest), ("Y", "n"))
        if answer != "y": return
    else:
        try:
            p = subprocess.run(['/usr/bin/mount', part, dest], check=True)
        except subprocess.CalledProcessError:
            log.warning("Mount failed")
    
            if not is_mounted(part, dest):
                log.error("Failed to mount {} at {}".format(part, dest))
                answer = ask_question("Failed to mount {} at {}, do it manually?".format(part, dest), ("Y", "n"))
                if answer != "y":
                    return True
                if not is_mounted(part, dest):
                    log.error("Failed to mount {} at {}".format(part, dest))
    log.info("Successfully mounted {} at {}".format(part, dest))


def unmount(dest: str):
    os.system("umount {}".format(dest))


def get_users() -> list:
    """Get the list of usernames from /Users and return it as a list of users"""
    users_path = Path(MOUNT_POINT, "Users")
    users = []
    for dir in users_path.iterdir():
        if not dir.is_dir(): continue
        if Path(dir, "ntuser.dat").exists():
            users.append(dir)
        elif Path(dir, "NTUSER.DAT").exists():
            users.append(dir)

    return users


def list_files(start_path: Path, max_depth=5) -> list:
    files = []
    if max_depth < 0: return ()
    for path in start_path.iterdir():
        if path.is_file(): files.append(path)
        elif path.is_dir() and not path.is_symlink():
            files.extend(list_files(path, max_depth=max_depth-1))
    return files


def count_images(user_dir: Path) -> int:
    """Counts the number of images (size > MIN_IMAGE_SIZE) in the /Users/username directory."""
    files = list_files(user_dir)
    images = 0
    for f in files:
        if f.suffix.lower() in IMAGE_EXTENSIONS:
            #if f.stat().st_size > MIN_IMAGE_SIZE:
                #images += 1
            images += 1
    return images


def process_ntfs_partition(part: Path):
    """Does everything needed when a new NTFS partition is found. Returns True if partition failed to process."""
    start = time()

    if mount(part, MOUNT_POINT): return True
    
    users = get_users()
    log.info("Found users {}".format(list(map(lambda x:x.name, users))))

    for user in users:
        images = count_images(user)
        print("Found user {:<16} with {:<6} images".format(user.name, images))
        log.info("User {} has {} images".format(user.name, images))
    log.info("Took {}s to scan partition".format(round(time() - start, 4)))

    return False


def get_disk_serial(disk: str):
    """Returns the serial number for the given disk."""
    p = subprocess.run(['/usr/bin/udevadm', 'info', '--query=all', '--name={}'.format(disk)], capture_output=True)
    out = p.stdout.decode().split('\n')
    serial = ""
    for line in out:
        serial = re.match(".*ID_SERIAL_SHORT=(.*)", line)
        if not serial: continue
        serial = serial.group(1)
        return serial
    log.warning("Failed to get serial number for {}. Using {}".format(disk, serial))
    return ""


def process_disk(path: Path):
    """Does everthing needed when a new disk is inserted."""
    global log

    serial = get_disk_serial(path)
    log.info("Processing disk {}".format(serial))
    print("Found disk {}".format(serial))

    partitions = get_ntfs_partitions(path)
    if len(partitions) == 0:
        log.info("Found no NTFS partitions")
        print("Found no NTFS partitions")
        return
    log.info("Found NTFS partitions: {}".format(list(map(lambda x:x.name, partitions))))
    for partition in partitions:
        if process_ntfs_partition(partition):
            log.warning("Failed to process partition {}".format(partition))
        unmount(partition)


def cleanup():
    global log
    unmount(MOUNT_POINT)


def main():
    global log
    
    create_log()
    log.info("Started.")

    original_disks = get_disks()
    original_disks.remove(Path('/dev/sdc'))
    log.info("Starting with disks: {}".format(list(map(lambda x:x.name, original_disks))))

    while True:
        current_disks = get_disks()
        new_disks = current_disks - original_disks
        if len(new_disks) > 0:
            log.info("Found new disks: {}".format(list(map(lambda x:x.name, new_disks))))

            for disk in new_disks:
                process_disk(disk)
                original_disks.add(disk)
            print("Waiting for new disks...")

        removed_disks = original_disks - current_disks
        if len(removed_disks) > 0:
            log.info("Removed disks: {}".format(list(map(lambda x:x.name, removed_disks))))
            original_disks -= removed_disks

        sleep(SLEEP_TIME)


if __name__ == '__main__':
    try:
        main()
    finally:
        cleanup()
