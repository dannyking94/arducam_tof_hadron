#!/usr/bin/env python3
import os
import shutil
import subprocess

def copy_arducam_folder():
    """
    Copies the /boot/arducam folder to the filesystem /boot/arducam folder.
    Requires sudo permissions to write to /boot.
    """
    source_folder = "/home/dk_jetson/arducam_tof/driver/boot/arducam"
    dest_folder = "/boot/arducam"
    
    print(f"Attempting to copy {source_folder} to {dest_folder}...")
    
    # Check if source folder exists
    if not os.path.exists(source_folder):
        print(f"Error: Source folder {source_folder} does not exist!")
        return False
    
    try:
        # Using sudo with shell commands since Python might not have permissions to write to /boot
        
        # Check if destination folder exists and remove it
        if os.path.exists(dest_folder):
            print(f"Removing existing {dest_folder}...")
            subprocess.run(["sudo", "rm", "-rf", dest_folder], check=True)
        
        # Create destination directory
        print(f"Creating new {dest_folder}...")
        subprocess.run(["sudo", "mkdir", "-p", dest_folder], check=True)
        
        # Copy contents of source folder to destination folder
        print(f"Copying files from {source_folder} to {dest_folder}...")
        subprocess.run(["sudo", "cp", "-R", f"{source_folder}/.", dest_folder], check=True)
        
        print(f"Successfully copied {source_folder} to {dest_folder}")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

if __name__ == "__main__":
    print("Starting ARDUCAM folder copy operation...")
    success = copy_arducam_folder()
    
    if success:
        print("Copy operation completed successfully!")
    else:
        print("Copy operation failed!")