#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import getpass
import html
import json
import os
import pickle
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Union

import html2text
import tqdm
from requests import Session
from selenium.webdriver import Chrome

JSONType = Dict[str, Union[str, int]]
SimpleCallback = Callable[[], None]


class RenrenSpider:
    def __init__(self, args: argparse.Namespace) -> None:
        self._user_id = args.user
        self.email = args.email
        self.password = args.password
        self.keep = args.keep
        self.output_dir = args.output
        self.driver = args.driver
        self.s = Session()
        self.s.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36"
        }

    @property
    def user_id(self):
        if not self._user_id:
            raise RuntimeError("Please login first!")
        return self._user_id

    def login(self) -> None:
        """login and get cookies."""
        if self.keep and os.path.isfile(".session"):
            with open(".session", "rb") as f:
                self._user_id = int(f.readline().strip().decode())
                self.s.cookies = pickle.load(f)
            return

        email, password = self.email, self.password
        if not email:
            email = input("Please enter email: ")
        if not password:
            password = getpass.getpass("Please enter password: ")
        browser = Chrome(self.driver)
        browser.get("http://renren.com")
        browser.find_element_by_id("email").send_keys(email)
        browser.find_element_by_id("password").send_keys(password)
        browser.find_element_by_id("login").click()
        for _ in range(30):
            if browser.current_url != "http://renren.com/":
                break
            time.sleep(1)
        else:
            browser.close()
            sys.exit("Login email or password is wrong!")
        cookies = browser.get_cookies()
        for cookie in cookies:
            self.s.cookies[cookie["name"]] = cookie["value"]
        print(browser.current_url)
        if not self._user_id:
            self._user_id = int(re.findall(r"/(\d+)/?$", browser.current_url)[0])
        if self.keep:
            with open(".session", "wb") as f:
                f.write(f"{self.user_id}\n".encode())
                pickle.dump(self.s.cookies, f)
        browser.close()

    def parse_album_list(self) -> List[JSONType]:
        collections_url = f"http://photo.renren.com/photo/{self.user_id}/albumlist/v7?offset=0&limit=40&showAll=1"
        resp = self.s.get(collections_url)
        albumlist = json.loads(
            re.findall(r"'albumList':\s*(\[[\s\S]*?\])", resp.text)[0]
        )
        return [item for item in albumlist if item.get("photoCount")]

    def download_album(self, album: JSONType) -> None:
        album_name = html.unescape(album["albumName"]).strip("./")
        photo_list = []
        album_url = f"http://photo.renren.com/photo/{self.user_id}/album-{album['albumId']}/bypage/ajax/v7?pageSize=100"
        for i in range(int(album["photoCount"] // 100) + 1):
            resp = self.s.get(f"{album_url}&page={i+1}")
            resp.raise_for_status()
            photo_list.extend(resp.json()["photoList"])

        download_dir = os.path.join(self.output_dir, "albums", album_name)
        if not os.path.isdir(download_dir):
            os.makedirs(download_dir)

        def download_image(image: JSONType, callback: SimpleCallback) -> None:
            url = image["url"]
            image_path = os.path.join(download_dir, os.path.basename(url))
            if os.path.isfile(image_path):
                callback()
                return
            r = self.s.get(url)
            r.raise_for_status()
            with open(image_path, "wb") as f:
                f.write(r.content)
            callback()

        with ThreadPoolExecutor() as pool:
            t = tqdm.tqdm(
                total=int(album["photoCount"]), desc=f"Dumping album {album_name}"
            )
            for image in photo_list:
                pool.submit(download_image, image, t.update)

    def dump_albums(self) -> None:
        for album in self.parse_album_list():
            self.download_album(album)

    def parse_article_list(self) -> List[JSONType]:
        url = (
            f"http://blog.renren.com/blog/{self.user_id}/blogs?categoryId=%20&curpage="
        )
        i = 0
        total = 0
        results = []
        if not os.path.isdir(f"{self.output_dir}/articles"):
            os.makedirs(f"{self.output_dir}/articles")
        while i == 0 or i * 10 < total:
            r = self.s.get(url + str(i))
            r.raise_for_status()
            data = r.json()
            if not total:
                total = data["count"]
            results.extend(data["data"])
            i += 1
        return results

    def download_article(self, article: JSONType, callback: SimpleCallback) -> None:
        url = f"http://blog.renren.com/blog/{self.user_id}/{int(article['id'])}"
        title = article["title"]
        datetime = article["createTime"]
        if os.path.isfile(f"{self.output_dir}/articles/{title}"):
            callback()
            return
        resp = self.s.get(url)
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
        with open(f"{self.output_dir}/articles/{title}", "w", encoding="utf-8") as f:
            f.write(
                template.format(
                    title=title, datetime=datetime, content=html2text.html2text(text)
                )
            )
        callback()

    def dump_articles(self) -> None:
        articles = self.parse_article_list()
        t = tqdm.tqdm(total=len(articles), desc="Dumping articles")
        with ThreadPoolExecutor() as pool:
            for article in articles:
                pool.submit(self.download_article, article, t.update)

    def dump_status(self) -> None:
        url = f"http://status.renren.com/GetSomeomeDoingList.do?userId={self.user_id}&curpage="
        i = 0
        total = 0
        results = []
        while i == 0 or i * 20 < total:
            r = self.s.get(url + str(i))
            r.raise_for_status()
            data = r.json()
            if not total:
                total = data["count"]
            results.extend(data["doingArray"])
            i += 1

        if not os.path.isdir(f"{self.output_dir}"):
            os.makedirs(f"{self.output_dir}")

        with open(f"{self.output_dir}/status.md", "w", encoding="utf-8") as f:
            for item in results:
                if item.get("location"):
                    heading = f"{item['dtime']} 在 {item['location']}"
                else:
                    heading = item['dtime']
                content = html2text.html2text(item['content'])
                f.write(f"### {heading}\n\n{content}\n\n")

    def main(self) -> None:
        self.login()
        self.dump_albums()
        self.dump_articles()
        self.dump_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--driver",
        default=os.getenv("CHROME_DRIVER"),
        help="The path to Chrome driver, defaults to envvar CHROME_DRIVER.",
    )
    parser.add_argument(
        "-k",
        "--keep",
        default=False,
        action="store_true",
        help="Whether keep the login cookies",
    )
    parser.add_argument("--user", help="Specify the user ID to parse")
    parser.add_argument(
        "--email",
        default=os.getenv("RENREN_EMAIL"),
        help="Login email, defaults to envvar RENREN_EMAIL",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("RENREN_PASSWD"),
        help="Login password, defaults to envvar RENREN_PASSWD",
    )
    parser.add_argument(
        "-o", "--output", default="output", help="Specify output directory"
    )
    args = parser.parse_args()
    spider = RenrenSpider(args)
    spider.main()
