人人网备份脚本
=============

***没有什么网站能永远保存你的数据***

2018年11月14日晨，著名社交媒体公司人人网携手多牛传媒股份有限公司（以下简称多牛传媒）发布公告称，人人网以整体对价6000万美金（2000万美金+4000万多牛传媒股份）出售人人网及相关业务。

你还记得上次用人人是什么时候吗？你在人人上还有多少珍贵的回忆？

可能这些回忆，你也并不想再去打开它。但话说回来，想不想看是一回事，能不能再看到是另一回事。我的数据自己做主，快使用这个脚本吧！


## 依赖

* Python >= 3.6
* Pipenv:  `$ pip install --upgrade pipenv`
* 安装:  `$ pipenv install`
* Chrome Driver

## 运行

```bash
$ pipenv run spider.py
Please enter email:
Please enter password:
...
Done
```
相册保存在`data/album-<user_id>`中


## Todo

- [ ] 文章
