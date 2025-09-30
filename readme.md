zeroCAM Installation Guide
This guide explains how to perform a clean and automated installation of the zeroCAM application on a Raspberry Pi.

Automated Installation (Recommended)
The recommended way to install zeroCAM is by using the provided installation script. This script will handle all necessary steps, including setting up dependencies, creating a dedicated user, and configuring the application to run as a system service.

Instructions:

Clone or copy the project files to your Raspberry Pi.

Navigate to the project's root directory in the terminal.

Make the installation script executable:

chmod +x install.sh

Run the script with sudo:

sudo ./install.sh

The script will guide you through the process. You will be asked to provide a DEVICE_ID for your camera.

Once completed, the application will be running in the background.

Managing the Service
You can manage the zeroCAM service using standard systemctl commands:

Check Status: sudo systemctl status zerocam.service

Stop Service: sudo systemctl stop zerocam.service

Start Service: sudo systemctl start zerocam.service

Restart Service: sudo systemctl restart zerocam.service

View Logs: sudo journalctl -u zerocam.service -f

Licensing
zeroCAM is released under a dual-license model.

Non-Commercial Use
For personal, educational, research, and any other non-commercial purposes, you are free to use, modify, and distribute this software under the terms of the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) license. See the LICENSE file for more details.

Commercial Use
If you wish to use this software for any commercial purpose, you must purchase a commercial license. Please contact us at [INSERISCI QUI LA TUA EMAIL O IL TUO SITO WEB] to inquire about pricing and terms.