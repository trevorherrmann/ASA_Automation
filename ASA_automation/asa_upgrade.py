
#!/usr/bin/env python
'''
This script will upgrade Cisco ASAs.  It will upgrade standalone ASAs
as well as HA pairs.  This script will transfer the file to the ASA and
perform the steps necessary to upgrade the devices.

Written by: Trevor Herrmann
Date: 5/5/2017
'''

import sys
import time
from datetime import datetime
from getpass import getpass, getuser
from netmiko import ConnectHandler, FileTransfer

#function to determine if scp is enabled on the firewall
def asa_scp_handler(ssh_conn, cmd = 'ssh scopy enable', mode = 'enable'):
    print "Enable/Disable ssh scopy..."
    if mode == 'disable':
        cmd = 'no ' + cmd
    ssh_conn.send_config_set([cmd])

#main function to run the upgrade
def main():
    arch = raw_input("Is this a standalone or pair of ASAs [standalone|pair]? ")

    #gather variables and run upgrade for standalone architecture
    if arch == "standalone":
        ip_addr = raw_input("Please enter the IP address or hostname of the ASA: ")
        user = "cisco"
        my_pass = getpass()
        start_time = datetime.now()
        image_location = 'disk0:'
        image_location = raw_input("Enter the image location [disk0:]: ") or "disk0:"
        source_image = raw_input("Enter the image file name: ")
        dest_image = source_image
        dest_image = raw_input("Enter the destination image [" + dest_image +"]: ") or dest_image
        print ">>>> {}".format(start_time)

        standalone_asa = {
            'device_type': 'cisco_asa',
            'ip': ip_addr,
            'username': user,
            'password': my_pass,
            'secret': my_pass,
            'port': 22,
        }

        #connect and login to ASA
        print "\nConnecting and logging in to %s " % ip_addr
        ssh_conn = ConnectHandler(**standalone_asa)

        #verify there is enough space to transfer file, if not prompt for deletion
        with FileTransfer(ssh_conn, source_file=source_image, dest_file=dest_image,
                        file_system=image_location) as scp_transfer:

            if scp_transfer.check_file_exists() == False:
                while scp_transfer.verify_space_available() == False:
                    make_space = raw_input("Insufficient space available on disk0:, "
                            "would you like to make more? [yes|no] [yes]: ") or 'yes'
                    if make_space == 'yes':
                        dir_disk = ssh_conn.send_command('dir disk0:')
                        print "\nOutput from dir disk0:"
                        print dir_disk
                        file_to_delete = raw_input("Enter file to be deleted: ")
                        ssh_conn.send_command('delete disk0:/%s' % file_to_delete)

                    if make_space == 'no':
                        sys.exit("\nExiting script, please go make space on the ASA "
                                    "before proceeding")

                    scp_transfer.verify_space_available()

                #Verify SCP is enabled, if not enable it
                print "\nEnabling SCP..."
                output = asa_scp_handler(ssh_conn, mode='enable')
                print output

                #transfer the file to the ASA
                print "\nTransferring file to ASA..."
                scp_transfer.transfer_file()

                #Disable SCP
                print "\nDisabling SCP..."
                output = asa_scp_handler(ssh_conn, mode='disable')
                print output

                #Verify the file
                print "\Verifying the file..."
                if scp_transfer.verify_file():
                    print "\nSource and Destination File MD5 match!"
                else:
                    raise ValueError("\nMD5 failure between source and destination file!")

                full_file_name = "{}/{}".format(image_location, dest_image)
                boot_cmd = 'boot system {}'.format(full_file_name)
                output = ssh_conn.send_config_set([boot_cmd])
                print output

                #Verify "show boot"
                print "\nVerifying boot variables..."
                output = ssh_conn.send_command('show boot')
                print output

                #write mem and reload the ASA
                print "\nWrite mem and reload"
                output = ssh_conn.send_command_expect('write mem')
                output += ssh_conn.send_command('reload')
                output += ssh_conn.send_command('y')
                print output

            elif scp_transfer.check_file_exists() == True:
                #Set boot commands
                full_file_name = "{}/{}".format(image_location, dest_image)
                boot_cmd = 'boot system {}'.format(full_file_name)
                output = ssh_conn.send_config_set([boot_cmd])
                print output

                #Verify "show boot"
                print "\nVerifying boot variables..."
                output = ssh_conn.send_command('show boot')
                print output

                #write mem and reload the ASA
                print "\nWrite mem and reload"
                output = ssh_conn.send_command_expect('write mem')
                output += ssh_conn.send_command('reload')
                output += ssh_conn.send_command('y')
                print output

        #wait for 5 minutes and verify the system is running on the new code
        time.sleep(300)
        ssh_conn = ConnectHandler(**standalone_asa)
        show_ver = ssh_conn.send_command('show_version')
        show_ver_lines = show_ver.split("\n")
        for line in show_ver_lines:
            if "System image" in line:
                print "\n" + line

        print "\n>>>> {}".format(datetime.now() - start_time)
        print

    if arch == "pair":
        ip_addr_pri = raw_input("Please enter the IP address or hostname of the primary ASA: ")
        ip_addr_sec = raw_input("Please enter the IP address or hostname of the secondary ASA: ")
        user = getuser()
        my_pass = getpass()
        start_time = datetime.now()
        image_location = 'disk0:'
        image_location = raw_input("Enter the image location [disk0:]: ") or "disk0:"
        source_image = raw_input("Enter the image file name: ")
        dest_image = source_image
        dest_image = raw_input("Enter the destination image [" + dest_image +"]: ") or dest_image
        print ">>>> {}".format(start_time)

        #primary_asa = {
        #    'device_type': 'cisco_asa',
        #    'ip': ip_addr_pri,
        #    'username': user,
        #    'password': my_pass,
        #    'secret': my_pass,
        #    'port': 22,
        #}

        secondary_asa = {
            'device_type': 'cisco_asa',
            'ip': ip_addr_sec,
            'username': user,
            'password': my_pass,
            'secret': my_pass,
            'port': 22,
        }

        asa_pair = [secondary_asa, secondary_asa]

        for asa in asa_pair:

            #connect and login to secondary ASA
            print "\nConnecting and logging in to %s " % asa
            ssh_conn = ConnectHandler(**asa)

            #verify that this is the secondary ASA
            print "\nVerifying this is the secondary ASA..."
            failover = ssh_conn.send_command("show failover")
            failover_lines = failover.split("\n")
            for line in failover_lines:
                if ("This host:" in line) and ("Standby Ready" in line):
                    print "\nSecondary host verified"
                elif ("This host:" in line) and ("Active" in line):
                    print "\n This is the primary ASA, failing over..."
                    ssh_conn.send_command('failover active')

            #verify there is enough space to transfer file, if not prompt for deletion
            with FileTransfer(ssh_conn, source_file=source_image, dest_file=dest_image,
                                file_system=image_location) as scp_transfer:

                if scp_transfer.check_file_exists() == False:
                    while scp_transfer.verify_space_available() == False:
                        make_space = raw_input("Insufficient space available on disk0:, "
                                "would you like to make more? [yes|no] [yes]: ") or 'yes'
                        if make_space == 'yes':
                            dir_disk = ssh_conn.send_command('dir disk0:')
                            print "\nOutput from dir disk0:"
                            print dir_disk
                            file_to_delete = raw_input("Enter file to be deleted: ")
                            ssh_conn.send_command('delete disk0:/%s' % file_to_delete)

                        if make_space == 'no':
                            sys.exit("\nExiting script, please go make space on the ASA "
                                        "before proceeding")

                        scp_transfer.verify_space_available()

                    #Verify SCP is enabled, if not enable it
                    print "\nEnabling SCP..."
                    output = asa_scp_handler(ssh_conn, mode='enable')
                    print output

                    #transfer the file to the ASA
                    print "\nTransferring file to ASA..."
                    scp_transfer.transfer_file()

                    #Disable SCP
                    print "\nDisabling SCP..."
                    output = asa_scp_handler(ssh_conn, mode='disable')
                    print output

                    #Verify the file
                    print "\Verifying the file..."
                    if scp_transfer.verify_file():
                        print "\nSource and Destination File MD5 match!"
                    else:
                        raise ValueError("\nMD5 failure between source and destination file!")

                elif scp_transfer.check_file_exists() == True:
                    #Set boot commands
                    full_file_name = "{}/{}".format(image_location, dest_image)
                    boot_cmd = 'boot system {}'.format(full_file_name)
                    output = ssh_conn.send_config_set([boot_cmd])
                    print output

                    #Verify "show boot"
                    print "\nVerifying boot variables..."
                    output = ssh_conn.send_command('show boot')
                    print output

                    #write mem and reload the ASA
                    print "\nWrite mem and reload"
                    output = ssh_conn.send_command_expect('write mem')
                    output += ssh_conn.send_command('reload')
                    output += ssh_conn.send_command('y')
                    print output

            #wait for 5 minutes and verify the system is running on the new code
            time.sleep(300)
            ssh_conn = ConnectHandler(**asa)
            show_ver = ssh_conn.send_command('show_version')
            show_ver_lines = show_ver.split("\n")
            for line in show_ver_lines:
                if "System image" in line:
                    print "\n" + line

            #Make the secondary ASA primary and verify
            print "\nFailing over ASA pair..."
            ssh_conn.send_command('failover active')
            print "\nVerifying this is the primary ASA..."
            failover = ssh_conn.send_command("show failover")
            failover_lines = failover.split("\n")
            for line in failover_lines:
                if ("This host:" in line) and ("Active" in line):
                    print ("\nFailover successful...")


        print "\n>>>> {}".format(datetime.now() - start_time)
        print


if __name__ == "__main__":
    main()
