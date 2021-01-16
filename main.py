import json
import os
import logging
import pprint
import datetime
import piexif
from shutil import copyfile
import string
from ip2geotools.databases.noncommercial import DbIpCity
import pickle
from lib import utils

logFormatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)


facebook_dir = input("Facebook Export Directory: ")
output_dir_name = input("Output Directory Name (created in the facebook export directory): ")


if os.path.exists("geo_ip_cache.pickle"):
    geo_ip_cache = pickle.load(open("geo_ip_cache.pickle", 'rb'))
else:
    geo_ip_cache = {}


def extract_location(attachment_data):
    upload_ip = None
    latitude = None
    longitude = None
    if "media_metadata" in attachment_data['media']:
        if "photo_metadata" in attachment_data['media']['media_metadata']:
            if "upload_ip" in attachment_data['media']['media_metadata']['photo_metadata']:
                upload_ip = attachment_data['media']['media_metadata']['photo_metadata']['upload_ip']

        if "video_metadata" in attachment_data['media']['media_metadata']:
            if "upload_ip" in attachment_data['media']['media_metadata']['video_metadata']:
                upload_ip = attachment_data['media']['media_metadata']['video_metadata']['upload_ip']

    if upload_ip:
        if upload_ip not in geo_ip_cache:
            try:
                response = DbIpCity.get(upload_ip, api_key='free')
            except KeyError as err:
                logger.error("Error getting location data for %s" % upload_ip)
                response = None
            geo_ip_cache[upload_ip] = response
            pickle.dump(geo_ip_cache, open("geo_ip_cache.pickle", 'wb'))
        else:
            response = geo_ip_cache[upload_ip]
        if response:
            latitude = response.latitude
            longitude = response.longitude

    return latitude, longitude

def extract_album_title(attachment_data):
    # Get the file path
    file_path = attachment_data['media']['uri']
    # Get the file name of the media
    file_name = file_path.split("/")[-1]

    # Parse out album names
    if not file_path.endswith(".mp4"):
        if "title" not in attachment_data['media']:
            logger.error("No title in media!")
            exit()
        album_name = attachment_data['media']['title']
    else:
        album_name = "Videos"

    if album_name == "":
        album_name = "Misc"

    album_name = utils.format_filename(album_name)
    return album_name

def extract_creation_date(attachment_data, post):
    if "creation_timestamp" in attachment_data['media']:
        creation_date = attachment_data['media']['creation_timestamp']
    else:
        creation_date = post['timestamp']

    creation_date = datetime.datetime.fromtimestamp(creation_date).strftime("%Y:%m:%d %H:%M:%S")
    return creation_date

def main():

    if not os.path.exists(facebook_dir):
        logger.error("Error missing facebook directory!")
        exit()

    posts_dir = os.path.join(facebook_dir, "posts")

    if not os.path.exists(posts_dir):
        logger.error("Error missing facebook posts directory!")
        exit()

    # Create a new directory to store the output.
    output_dir = os.path.join(facebook_dir, output_dir_name)

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)


    # Collect all facebook posts
    posts_data = []
    for json_file in os.listdir(posts_dir):
        if json_file.endswith(".json"):
            with open(os.path.join(posts_dir, json_file)) as in_file:
                data = json.load(in_file)
                posts_data += data

    photos = {}

    # Loop through posts and find which ones have photo uploads
    for post in posts_data:
        # pprint.pprint(post)
        logger.debug("Processing Post: %s" % post['timestamp'])
        if "attachments" in post:
            for attachment in post['attachments']:
                if "data" in attachment:
                    for attachment_data in attachment["data"]:
                        if "media" in attachment_data:
                            logger.debug("Media found in attachment!")
                            logger.debug(attachment_data)
                            # Get the file path
                            file_path = attachment_data['media']['uri']
                            # Get the file name of the media
                            file_name = file_path.split("/")[-1]

                            latitude, longitude = extract_location(attachment_data)
                            creation_date = extract_creation_date(attachment_data, post)
                            album_name = extract_album_title(attachment_data)

                            # Copy the media files to a new folder

                            # If the media file doesn't exist for some reason...
                            if not os.path.exists(os.path.join(facebook_dir, file_path)):
                                logger.error("Path to media file does not exist!")
                                logger.error(file_path)
                                exit()

                            # Create the new folder
                            if os.path.exists(os.path.join(output_dir, album_name)):
                                logger.debug("Copying %s to %s" % (os.path.join(facebook_dir, file_path), os.path.join(output_dir,album_name,file_name)))
                                copyfile(os.path.join(facebook_dir, file_path), os.path.join(output_dir,album_name,file_name))
                            else:
                                logger.warning("Album directory (%s) not created, making it now..." % album_name)
                                os.mkdir(os.path.join(output_dir, album_name))
                                logger.debug("Copying %s to %s" % (os.path.join(facebook_dir, file_path), os.path.join(output_dir,album_name,file_name)))
                                copyfile(os.path.join(facebook_dir, file_path), os.path.join(output_dir, album_name, file_name))

                            new_file_path = os.path.join(output_dir, album_name, file_name)

                            # Load up and edit the exif data
                            if new_file_path.endswith("jpg"):
                                exif_dict = piexif.load(new_file_path)

                                exif_dict['0th'][piexif.ImageIFD.DateTime] = creation_date
                                exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = creation_date
                                exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = creation_date
                                if latitude and longitude:
                                    exif_dict['GPS'] = utils.set_gps_location(latitude, longitude, 10)

                                exif_bytes = piexif.dump(exif_dict)

                                # Remove existing metadata
                                piexif.remove(new_file_path)
                                piexif.insert(exif_bytes, new_file_path)

                        else:
                            pass
                            # logger.warning("No media in attachment data")
                else:
                    pass
                    # logger.warning("No data in attachment")
        else:
            pass
            # logger.warning("No attachments in post")
        # exit()


if __name__ == "__main__":
    main()