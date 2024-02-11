import os
import re
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, send_file, redirect
from urllib.parse import urlparse, urljoin
import zipfile
import csv
import shutil
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase  # Add this import statement
from email import encoders

app = Flask(__name__)


async def scrape_images_from_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                soup = BeautifulSoup(await response.text(), 'html.parser')
            image_urls = []
                
            # Extract images from <div class="col-sm-6 big-image-container">
            big_image_container = soup.find('div', class_='col-sm-6 big-image-container')
            if big_image_container:
                img_tag = big_image_container.find('img', class_='img-responsive big-image')
                if img_tag and 'src' in img_tag.attrs:
                    img_url = img_tag['src']
                    if not bool(urlparse(img_url).netloc):
                        img_url = urljoin(url, img_url)
                        image_urls.append(img_url)
                # Extract images from <div id="owl-gallery" class="owl-carousel">
            owl_gallery = soup.find('div', id='owl-gallery', class_='owl-carousel')
            if owl_gallery:
                gallery_items = owl_gallery.find_all('a', class_='gallery-item')
                for item in gallery_items:
                    img_tag = item.find('img', class_='img-responsive lazyOwl')
                    if img_tag and 'data-src' in img_tag.attrs:
                        img_url = img_tag['data-src']
                        if not bool(urlparse(img_url).netloc):
                            img_url = urljoin(url, img_url)
                        img_url = img_url.replace('/kis_kep/', '/nagy_kep/')
                        image_urls.append(img_url)
                return image_urls
            else:
                print(f"Failed to fetch URL: {url}")
                return []



async def download_image(session, image_url, numbermatch):
    async with session.get(image_url) as response:
        if response.status == 200:
            download_folder = os.path.join("downloaded_images", numbermatch)
            if not os.path.exists(download_folder):
                os.makedirs(download_folder)
            filename = os.path.basename(urlparse(image_url).path)
            download_path = os.path.join(download_folder, filename)
            with open(download_path, 'wb') as f:
                f.write(await response.read())
            print(f"Downloaded image: {download_path}")
            return download_path
        else:
            print(f"Failed to download image: {image_url} - Status code: {response.status}")
            return None

async def download_images(image_urls):
    downloaded_paths = []
    async with aiohttp.ClientSession() as session:
        tasks = []
        for image_url in image_urls:
            numbermatch = extract_number(image_url)
            if numbermatch:
                task = asyncio.create_task(download_image(session, image_url, numbermatch))
                tasks.append(task)
            else:
                print(f"Failed to extract number from URL: {image_url}")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, str):
                    downloaded_paths.append(result)
    return downloaded_paths

async def send_email_with_attachment(filename, recipient_emails, subject, message_body):
    sender_email = "sales@aws-trading.hu"
    smtp_server = "mail.aws-trading.hu"
    smtp_port = 587  # Change this to 465 for SMTP_SSL

    # Username and password
    username = "sales@aws-trading.hu"
    password = "heritech@098"

    # Create a multipart message and set headers
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = ", ".join(recipient_emails)
    message["Subject"] = subject

    # Add body to email
    message.attach(MIMEText(message_body, "plain"))

    # Open the file in binary mode
    with open(filename, "rb") as attachment:
        # Add file as application/octet-stream
        # Email client can usually download this automatically as attachment
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())

    # Encode file in ASCII characters to send by email
    encoders.encode_base64(part)  # Use the encoders module here

    # Add header as key/value pair to attachment part
    part.add_header(
        "Content-Disposition",
        f"attachment; filename= {filename}",
    )

    # Add attachment to message and convert message to string
    message.attach(part)
    text = message.as_string()

    # Log in to server and send email
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(username, password)  # Use the provided username and password
        server.sendmail(sender_email, recipient_emails, text)



async def send_emails(filename, numbermatch):
    await send_email_with_attachment(filename, ["okunolaope98@gmail.com"], "Hello David", f"Here is the CSV file for {numbermatch}")
    # await send_email_with_attachment(filename, ["zoltan@msps.one"], "Hello Zoltan", f"Here is the CSV file for {numbermatch}")
async def create_zip_folder(folder_path, zip_filename):
    zip_path = os.path.join("downloaded_images", zip_filename)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), folder_path))
    return zip_path

@app.route('/', methods=['GET', 'POST'])
async def index():
    error_message = None
    if request.method == 'POST':
        link = request.form['link']
        app.logger.info(f"Received request for link: {link}")
        nagy_kep_urls_with_watermark, nagy_kep_urls_without_watermark = await extract_nagy_kep_images(link)
        app.logger.info(f"Extracted image URLs without watermark: {nagy_kep_urls_without_watermark}")
        downloaded_paths = await download_images(nagy_kep_urls_without_watermark)
        if downloaded_paths:
            numbermatch = extract_number(nagy_kep_urls_without_watermark[0])
            # Create CSV
            csv_data = "Image URL\n"
            for url in nagy_kep_urls_without_watermark:
                csv_data += f"{url}\n"
            # Save CSV
            csv_file_path = os.path.join("downloaded_images", f"{numbermatch}.csv")
            with open(csv_file_path, 'w', newline='') as csvfile:
                csvfile.write(csv_data)
            # Create ZIP
            zip_filename = f"{numbermatch}.zip"
            zip_path = await create_zip_folder(os.path.join("downloaded_images", numbermatch), zip_filename)
            # Send Email
            await send_emails(csv_file_path, numbermatch)
            # Send the zip file as a response for download
            return send_file(zip_path, as_attachment=True)
        else:
            error_message = "No images downloaded."
    if error_message:
        return render_template('index.html', error_message=error_message)
    return render_template('index.html')


async def extract_nagy_kep_images(property_link):
    nagy_kep_urls_with_watermark = []
    nagy_kep_urls_without_watermark = []
    try:
        image_urls = await scrape_images_from_url(property_link)
        for img_url in image_urls:
            if '-watermark.jpg' in img_url:
                nagy_kep_urls_with_watermark.append(img_url)
                without_watermark_url = img_url.replace('-watermark.jpg', '.jpg')
                nagy_kep_urls_without_watermark.append(without_watermark_url)
    except Exception as e:
        app.logger.error(f"Error extracting image URLs: {e}")
        if not nagy_kep_urls_with_watermark:
            app.logger.warning("No nagy_kep image URLs with watermark found on the page")
    if not nagy_kep_urls_without_watermark:
        app.logger.warning("No nagy_kep image URLs without watermark found on the page")
    app.logger.info(f"Extracted image URLs with watermark: {nagy_kep_urls_with_watermark}")
    app.logger.info(f"Extracted image URLs without watermark: {nagy_kep_urls_without_watermark}")
    return nagy_kep_urls_with_watermark, nagy_kep_urls_without_watermark


def extract_number(image_url):
    match = re.search(r'-(\d+)-?', image_url)
    if match:
        return match.group(1)
    else:
        return None





if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)