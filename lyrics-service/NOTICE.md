# LDDC 服务声明

本容器固定使用 `chenmozhijin/LDDC` 提交
`84631e8cd011fcc3f71ca0ae017e2c9758958ffc`。LDDC 采用 GPL-3.0-only；镜像内的
`/licenses/LDDC-GPL-3.0.txt` 保存完整许可证。上游源码：
https://github.com/chenmozhijin/LDDC

本目录的 HTTP 包装层与 LDDC 一同作为独立服务运行，视频工坊主 API 仅通过 HTTP
使用它，不复制 LDDC 的平台实现。
