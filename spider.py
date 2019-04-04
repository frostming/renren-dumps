#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Union, Callable
import getpass
import tqdm
import html

from requests import Session
from selenium.webdriver import Chrome

requests = Session()
requests.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36'}
user_id = None


def login(email: str, password: str) -> None:
    """login and get cookies."""
    browser = Chrome('D:/Downloads/chromedriver.exe')
    browser.get('http://renren.com')
    browser.find_element_by_id('email').send_keys(email)
    browser.find_element_by_id('password').send_keys(password)
    browser.find_element_by_id('login').click()
    for _ in range(30):
        if browser.current_url != 'http://renren.com/':
            break
        time.sleep(1)
    else:
        browser.close()
        sys.exit("Login email or password is wrong!")
    cookies = browser.get_cookies()
    for cookie in cookies:
        requests.cookies[cookie['name']] = cookie['value']
    global user_id
    print(browser.current_url)
    user_id = int(re.findall(r'/(\d+)/?$', browser.current_url)[0])
    browser.close()


def parse_album_list() -> List[Dict[str, Union[str, int]]]:
    if user_id is None:
        sys.exit('Please login first.')
    collections_url = f'http://photo.renren.com/photo/{user_id}/albumlist/v7?offset=0&limit=40&showAll=1'
    resp = requests.get(collections_url)
    albumlist = json.loads(re.findall(r"'albumList':\s*(\[[\s\S]*?\])", resp.text)[0])
    return [item for item in albumlist if item.get('photoCount')]


def download_album(album: Dict[str, Union[str, int]]) -> None:
    album_name = html.unescape(album['albumName']).strip('./')
    photo_list = []
    album_url = f"http://photo.renren.com/photo/{user_id}/album-{album['albumId']}/bypage/ajax/v7?pageSize=100"
    for i in range(int(album['photoCount'] // 100) + 1):
        resp = requests.get(f'{album_url}&page={i+1}')
        resp.raise_for_status()
        photo_list.extend(resp.json()['photoList'])

    download_dir = os.path.join("data", f"albums-{user_id}", album_name)
    if not os.path.isdir(download_dir):
        os.makedirs(download_dir)

    def download_image(image: Dict[str, Union[str, int]], callback: Callable[[], None]) -> None:
        url = image['url']
        image_path = os.path.join(download_dir, os.path.basename(url))
        if os.path.isfile(image_path):
            callback()
            return
        r = requests.get(url)
        r.raise_for_status()
        with open(image_path, "wb") as f:
            f.write(r.content)
        callback()

    # for image in tqdm.tqdm(photo_list, f'Downloading album {album_name}'):
    #     download_image(image)

    with ThreadPoolExecutor() as pool:
        t = tqdm.tqdm(total=int(album['photoCount']), desc=f'Downloading album {album_name}')
        for image in photo_list:
            f = pool.submit(download_image, image, t.update)


def main() -> None:
    login(input("Please enter email: "), getpass.getpass("Please enter password: "))
    for album in parse_album_list():
        download_album(album)


if __name__ == "__main__":
    main()
