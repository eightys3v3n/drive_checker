Linux only. Isn't cleaned up or documented properly.

A quick afternoon project to help look through 40 hard drives from old computers to find someones images. This program mounts disks and checks various programmed in criteria (whether it's an NTFS drive, what windows users are present, approximately how many images each user has), printing to the console.

Add other methods to be run on every disk insertion to the process_disk method if you want it to run on Every disk. Add methods to the process_ntfs_partition method if you only want to handle say, windows partitions.
