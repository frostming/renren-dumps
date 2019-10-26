#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import datetime
import html
import json
import os
import pickle
import random
import re
import lxml.html
from typing import Callable, Dict, List, Union

import html2text
from requests import Session

JSONType = Dict[str, Union[str, int]]
SimpleCallback = Callable[[], None]


class LoginFailed(Exception):
    pass


class iCodeRequired(Exception):
    pass


def encrypt_string(enc, mo, s):
    b = 0
    pos = 0
    for ch in s:
        b += ord(ch) << pos
        pos += 8

    crypt = pow(b, enc, mo)

    return f'{crypt:x}'


class RenrenSpider:
    ENCRYPT_KEY_URL = "http://login.renren.com/ajax/getEncryptKey"
    LOGIN_URL = "http://www.renren.com/ajaxLogin/login?1=1&uniqueTimestamp={ts}"
    LOGIN_3G_URL = "http://3g.renren.com/login.do?autoLogin=true&"
    ICODE_URL = "http://icode.renren.com/getcode.do?t=web_login&rnd={rnd}"
    MAX_RETRY = 3

    def __init__(self) -> None:
        self.ui = None
        self.user_id = None
        self.output_dir = None
        self.s = Session()
        self.s.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36"
        }
        self.re = None
        self.rn = None
        self.rk = None

    def login(self, email: str, password: str, icode: str = "", keep: bool = False) -> None:
        if not all([self.re, self.rn, self.rk]):
            self.s.cookies.clear()
            enc_data = self.s.get(self.ENCRYPT_KEY_URL).json()
            self.re = int(enc_data['e'], 16)
            self.rn = int(enc_data['n'], 16)
            self.rk = enc_data['rkey']

        payload = {
            'email': email,
            'password': encrypt_string(self.re, self.rn, password),
            'rkey': self.rk,
            'key_id': 1,
            'captcha_type': 'web_login',
            'icode': icode,
        }
        now = datetime.datetime.now()
        ts = '{year}{month}{weekday}{hour}{second}{ms}'.format(
            year=now.year,
            month=now.month - 1,
            weekday=(now.weekday() + 1) % 7,
            hour=now.hour,
            second=now.second,
            ms=int(now.microsecond / 1000),
        )

        login_data = self.s.post(self.LOGIN_URL.format(ts=ts), data=payload).json()
        if not login_data.get('code', False) or 'id' not in self.s.cookies:
            raise iCodeRequired(login_data.get('failDescription'))
        payload = {
            'ref': 'http://m.renren.com/q.do?null',
            'email': email,
            'password': password
        }
        r = self.s.post(self.LOGIN_3G_URL, data=payload)
        assert r.ok, "3G login failed"
        if not self.user_id:
            self.user_id = self.s.cookies["id"]
        if keep:
            with open(".session", "wb") as f:
                pickle.dump(self.s.cookies, f)

    def set_params(self, *, user_id=None, output_dir=None) -> None:
        if user_id:
            self.user_id = user_id
        self.output_dir = output_dir

    def get_icode_image(self) -> bytes:
        resp = self.s.get(self.ICODE_URL.format(rnd=random.random()))
        return resp.content

    def is_login(self) -> bool:
        """login and get cookies."""
        if not os.path.isfile(".session"):
            return False
        with open(".session", "rb") as f:
            self.s.cookies = pickle.load(f)
        self.s.cookies.clear_expired_cookies()
        if "id" not in self.s.cookies:
            return False
        if not self.user_id:
            self.user_id = self.s.cookies["id"]
        return True

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

        t = self.ui.progressbar(
            total=int(album["photoCount"]), desc=f"Dumping album {album_name}"
        )
        for image in photo_list:
            download_image(image, t.update)

    def dump_albums(self) -> None:
        for album in self.parse_album_list():
            self.download_album(album)

    def parse_article_list(self) -> List[JSONType]:
        start_url = f'http://3g.renren.com/blog/wmyblog.do?id={self.user_id}'
        results = []
        if not os.path.isdir(f"{self.output_dir}/articles"):
            os.makedirs(f"{self.output_dir}/articles")

        def _parse_one_page(url):
            resp = self.s.get(url)
            tree = lxml.html.fromstring(resp.text)
            for element in tree.xpath('//div[@class="list"]/div[not(@class)]'):
                item = {
                    'title': element.xpath('a/text()')[0].strip(),
                    'url': element.xpath('a/@href')[0].strip(),
                    'createTime': element.xpath('p/text()')[0].strip()
                }
                results.append(item)
            next_url = tree.xpath('//a[@title="下一页"]/@href')
            if next_url:
                _parse_one_page(next_url[0].strip())

        _parse_one_page(start_url)
        return results

    def download_article(self, article: JSONType, callback: SimpleCallback) -> None:
        url = article["url"].replace('flag=0', 'flag=1')
        title = article["title"]
        datetime = article["createTime"]
        if os.path.isfile(f"{self.output_dir}/articles/{title}.md"):
            callback()
            return
        resp = self.s.get(url)
        resp.raise_for_status()
        text = re.findall(
            r'<div class="con">([\s\S]*?)</div>',
            resp.text,
        )[0].strip()
        template = """\
{title}
=======
日期: {datetime}

{content}
"""
        with open(f"{self.output_dir}/articles/{title}.md", "w", encoding="utf-8") as f:
            f.write(
                template.format(
                    title=title, datetime=datetime, content=html2text.html2text(text)
                )
            )
        callback()

    def dump_articles(self) -> None:
        articles = self.parse_article_list()
        t = self.ui.progressbar(total=len(articles), desc="Dumping articles")
        for article in articles:
            self.download_article(article, t.update)

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
            progressbar = self.ui.progressbar(total=len(results), desc="Dumping status")
            for item in results:
                if item.get("location"):
                    heading = f"{item['dtime']} 在 {item['location']}"
                else:
                    heading = item['dtime']
                content = html2text.html2text(item['content'])
                f.write(f"### {heading}\n\n{content}\n\n")
                progressbar.update()

    def main(self, ui) -> None:
        self.ui = ui
        self.dump_albums()
        self.dump_articles()
        self.dump_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
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
