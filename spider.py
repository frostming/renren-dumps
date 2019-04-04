#!/usr/bin/env python
# -*- coding: utf-8 -*-
import getpass
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Union

import html2text
import tqdm
from requests import Session
from selenium.webdriver import Chrome

requests = Session()
requests.headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36'
}
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

    def download_image(
        image: Dict[str, Union[str, int]], callback: Callable[[], None]
    ) -> None:
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
        t = tqdm.tqdm(
            total=int(album['photoCount']), desc=f'Downloading album {album_name}'
        )
        for image in photo_list:
            pool.submit(download_image, image, t.update)


def parse_article_list() -> List[Dict[str, Union[str, int]]]:
    url = f"http://blog.renren.com/blog/{user_id}/blogs?categoryId=%20&curpage="
    i = 0
    total = 0
    results = []
    if not os.path.isdir(f"data/articles-{user_id}"):
        os.makedirs(f"data/articles-{user_id}")
    while i == 0 or i * 10 < total:
        r = requests.get(url + str(i))
        r.raise_for_status()
        data = r.json()
        if not total:
            total = data['count']
        results.extend(data['data'])
        i += 1
    return results


def download_article(article: Dict[str, Union[str, int]]) -> None:
    url = f"http://blog.renren.com/blog/{user_id}/{int(article['id'])}"
    title = article['title']
    datetime = article['createTime']
    if os.path.isfile(f"data/articles-{user_id}/{title}"):
        return
    resp = requests.get(url)
    resp.raise_for_status()
    text = re.findall(
        r'<div id="blogContent" class="blogDetail-content" data-wiki="">([\s\S]*?)</div>',
        resp.text,
    )[0].strip()
    template = """\
{title}
=======
日期: {datetime}

{content}
"""
    with open(f"data/articles-{user_id}/{title}.md", "w", encoding="utf-8") as f:
        f.write(
            template.format(
                title=title, datetime=datetime, content=html2text.html2text(text)
            )
        )


def main() -> None:
    login(input("Please enter email: "), getpass.getpass("Please enter password: "))
    for album in parse_album_list():
        download_album(album)
    with ThreadPoolExecutor() as pool:
        pool.map(download_article, parse_article_list())


if __name__ == "__main__":
    main()
