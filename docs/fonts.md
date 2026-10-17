# 字体

插件在启动时按顺序发现可用字体，取第一个存在的。优先等宽且含中文字形。

| 顺序 | 字体 | 位置 |
|------|------|------|
| 1 | Sarasa Mono SC | `<数据目录>/plugin_data/astrbot_plugin_md_render/fonts/SarasaMonoSC-Regular.ttf` |
| 2 | Noto Sans Mono CJK SC | 系统 `NotoSansCJK-Regular.ttc` 的第 7 个 face |
| 3 | WenQuanYi Micro Hei Mono | 系统 `wqy-microhei.ttc` 的第 1 个 face |
| 4 | DejaVu Sans Mono | 系统自带，无中文字形 |

AstrBot 官方镜像自带 `fonts-noto-cjk`，因此第 2 项通常直接命中，不需要配置。

ttc 集合必须指定 face：第 0 个 face 是比例字体，按路径直接取会让代码列对齐歪掉。插件已经带上了 face 参数。

## 安装 Sarasa Mono SC

中英文严格 2:1 等宽，代码观感比系统字体整齐。以下命令在 AstrBot 所在机器执行，完成后重启 AstrBot。

```bash
# 1) 下载压缩包，约 68MB。GitHub 直连不稳时走镜像，镜像失败换注释里的直连
wget https://gh-proxy.com/https://github.com/be5invis/Sarasa-Gothic/releases/download/v1.0.27/SarasaMonoSC-TTF-1.0.27.7z
# 直连：wget https://github.com/be5invis/Sarasa-Gothic/releases/download/v1.0.27/SarasaMonoSC-TTF-1.0.27.7z

# 2) 解压出 Regular 字重，约 25MB，只需要这一个文件。没有 7z 先装：apt-get install -y p7zip-full
7z e SarasaMonoSC-TTF-1.0.27.7z SarasaMonoSC-Regular.ttf

# 3) 放进插件字体目录。Docker 部署的数据目录默认为 /AstrBot/data
DATA_DIR=/AstrBot/data
FONT_DIR="$DATA_DIR/plugin_data/astrbot_plugin_md_render/fonts"
mkdir -p "$FONT_DIR"
mv SarasaMonoSC-Regular.ttf "$FONT_DIR/"

# 4) 重启生效
docker restart astrbot
```

非 Docker 部署在 AstrBot 管理面板重载插件即可。

其它中文字体也可以：重命名为 `SarasaMonoSC-Regular.ttf` 放进同一目录。插件不会在运行时下载或解压字体。

## HTML 文档的字体

HTML 文档渲染走另一条路径，按字体名注册，优先级为 Noto Sans CJK SC、WenQuanYi Micro Hei、上表第 1 项。
