# 字体

插件要两种中文字体：画代码要等宽的（每个字母一样宽），画表格要比例的（字宽跟着内容走）。两者都在系统里自动发现，AstrBot 官方镜像自带 Noto Sans CJK，一个文件里两样都有，通常什么都不用做。

想换代码的观感可以装 Sarasa Mono SC：中英文严格 2:1 等宽，比系统等宽体更整齐。它只影响代码块与公式——表格正文要比例体，Sarasa 是等宽的，不参与。

## 安装 Sarasa Mono SC

以下命令在 AstrBot 所在机器执行，完成后重启 AstrBot。

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

## 确认命中了哪个

```bash
docker exec -w /AstrBot/data/plugins/astrbot_plugin_md_render astrbot python3 -c "
from render import font
font.init_font('/AstrBot/data/plugin_data/astrbot_plugin_md_render')
print('代码:', font.find_font_spec(), font.font_family(font.find_font_spec()))
print('表格:', font.body_spec(), font.body_family())
"
```

代码那行指向 `fonts/SarasaMonoSC-Regular.ttf` 说明手动字体生效；两行都指向系统 Noto 说明没放手动字体，或放的位置不对。

## HTML 文档

HTML 文档的字体由文档自己的 CSS 决定，插件只负责把找到的字体都注册进去。所以文档里写 `font-family: "Noto Sans CJK SC"` 或 `"Sarasa Mono SC"` 都能命中；族名写错不会报错，会静默回退到默认字体。
