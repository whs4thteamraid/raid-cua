# RAID Mirror Setup
This workstation has been set up to use the internal package mirror (raid-mirror).
## Daily heartbeat command
Run at the start of every session to keep the mirror in sync:
bash ~/.config/raid-mirror/heartbeat.sh
## Setup steps completed
1. Cloned repo: git clone http://mirror.raid.internal:8000/raid-mirror.git
2. Ran setup.sh
3. Ran heartbeat.sh
