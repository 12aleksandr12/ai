import os

def create_download_folder(folder="downloads"):
    if not os.path.exists(folder):
        os.makedirs(folder)
