<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# nonebot-plugin-bili-share-keeper

_✨ 记录b站视频链接分享，并提示多次分享 ✨_


<a href="https://github.com/qianqiuzy/nonebot-plugin-bili-share-keeper/stargazers">
        <img alt="GitHub stars" src="https://img.shields.io/github/stars/qianqiuzy/nonebot-plugin-bili-share-keeper" alt="stars">
</a>
<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/qianqiuzy/nonebot-plugin-bili-share-keepern.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-bili-share-keepern">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-bili-share-keeper.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">

</div>

## 📖 介绍

记录b站视频链接分享，并提示多次分享

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-bili-share-keeper

</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details>
<summary>pip</summary>

    pip install nonebot-plugin-bili-share-keeper
</details>
<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-bili-share-keeper
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-bili-share-keeper
</details>
<details>
<summary>conda</summary>

    conda install nonebot-bili-share-keeper
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_bili-share-keeper"]

</details>

## ⚙️ 配置

在 nonebot2 项目的`.env`文件中添加下表中的必填配置

| 配置项 | 必填 | 默认值 | 说明 |
|:-----:|:----:|:----:|:----:|
| bilibili_share_keeper_redis_url | 否 | redis://localhost:6379/0 | redis数据库地址 |
| bilibili_share_keeper_target_group | 是 | 无 | 开启此插件的群聊 |
| bilibili_share_keeper_key_prefix | 否 | nb2:bili_share_keeper | redis中记录的前缀 |
| bilibili_share_keeper_http_timeout | 否 | 10 | http请求的超时值 |

## 🕹️ 使用

在第二次及以上的时候分享B站链接视频会出现“此视频已于{datetime}被群友{群友名称}分享过，这是第{分享次数}次被分享”