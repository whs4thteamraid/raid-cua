# RAID Mirror Heartbeat Command
To keep the workstation in sync with the raid-mirror, run this command at the start of every session:
bash ~/.config/raid-mirror/heartbeat.sh
The mirror index rotates daily, so this is required to prevent the client from falling out of sync.
