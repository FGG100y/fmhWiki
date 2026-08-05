# 部署指南（Docker）

本指南面向第一次接手本项目的同学，从零开始把白板智能体（后端 FastAPI 服务，端口 `18088`）用 Docker 部署到一台 Linux 服务器上。

## 零、快速开始（太长不看版）

> 照做即可跑起来，想了解每个步骤背后的原理再看对应小节。

**开发机（负责构建镜像，amd64/arm64 都能编）：**

1. 装好 Docker 后，在项目根目录执行 `./build-multiarch.sh`
   → 产出 `painteragent-1.0.0-amd64.tar` 和 `painteragent-1.0.0-arm64.tar`（详见「五、多架构构建」）
2. 把对应服务器架构的包拷到服务器：`scp painteragent-1.0.0-arm64.tar user@server:/tmp/`

**服务器（以 arm64 为例）：**

3. 安装 Docker（已装可跳过）：`curl -fsSL https://get.docker.com | sh`
4. 导入镜像：`docker load -i /tmp/painteragent-1.0.0-arm64.tar`
5. 改名对齐 tag（可选）：`docker tag painteragent:1.0.0-arm64 painteragent:1.0.0`
6. 准备密钥：`cp .env.example .env` 并填入真实豆包 API Key（缺失 Key 会 500，密钥说明见「六、第三步：在服务器运行」）
   > 若之前已部署过同名容器，先 `docker stop painteragent && docker rm painteragent`（**不要加 `-v`**，否则会连会话卷一起删），否则 `docker run --name painteragent` 会报 `Conflict`。
7. 启动容器：
   `docker run -d --name painteragent -p 18088:18088 -v painteragent_memory:/app/memory --env-file .env --restart unless-stopped painteragent:1.0.0`
8. 验证：`docker ps | grep painteragent` 状态为 Up，再调一下健康接口：
   `curl -X POST http://<服务器IP>:18088/api/whiteboard-agent/clear-history -H "Content-Type: application/json" -d '{"sessionId": 1}'`

## 一、项目是什么

- 技术栈：Python 3.11+ / FastAPI / uvicorn / langgraph / deepagents
- 启动入口：`start_backend.py` → `uvicorn.run("api.whiteboard_app:app", host="0.0.0.0", port=18088)`
- 对外接口：
  - `POST /api/whiteboard-agent/generate-image`
  - `POST /api/whiteboard-agent/clear-history`
- 状态存储：内存用 SQLite 持久化到 `memory/checkpoints.db`（会话记忆），容器重建若不挂卷会丢失。

## 二、仓库现状与产出物

本仓库已含 Docker 部署所需文件：

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 以 `python:3.11-slim` 为基础镜像，用清华源 pip 装依赖后把项目拷入并启动 |
| `build-multiarch.sh` | 一键编出 amd64 + arm64 多平台镜像（分平台 docker tar 或推送仓库），见第五节「多架构构建」 |
| `docker-compose.yml` | 可选方案（见下文「可选项」），把端口映射/卷/重启策略参数文件化，一键运行 |
| `.dockerignore` | 构建时排除 git/.venv/*.db/logs 等，保证镜像干净小巧 |

> 注意：项目依赖使用 `uv.lock` 管理，但服务器不强依赖 uv；`Dockerfile` 直接用 `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt`，最简单、新人最易上手。

## 三、需要准备的东西

1. 一台 Linux 服务器（本指南以 Ubuntu/Debian 为例），能连外网
2. 服务器上已安装 Docker（如需用 compose 可选项，再装 Docker Compose 插件）
3. 可访问外网（Agent 需要请求豆包/火山方舟 API）

## 四、第一步：安装 Docker（服务器第一次才需要）

如果已经装过，可以直接跳过。

```bash
# 官方一键安装脚本
curl -fsSL https://get.docker.com | sh

# 把当前用户加入 docker 组，免 sudo 使用（需要重新登录终端生效）
sudo usermod -aG docker $USER

# 验证
docker --version
docker compose version
```

## 五、第二步：本地构建镜像

本项目无镜像仓库，直接在本地构建并使用本地镜像名，通过离线方式部署到服务器。

在**你的开发机**（项目根目录下）执行：

```bash
# 1. 构建镜像，tag 用 项目名:版本号
docker build -t painteragent:1.0.0 .
```

### 国内网络：给 Docker 配置镜像加速（拉取基础镜像超时时）

`FROM python:3.11-slim` 从 Docker Hub（`registry-1.docker.io`）拉取，国内常超时。注意：**这不归 pip 的清华源管**（清华源只代理 Python 包，不代理 Docker 镜像），需单独给 Docker 配置 registry mirror。

```bash
# 1. 写入加速器配置（选一组国内镜像即可）
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com",
    "https://docker.1panel.live",
    "https://mirror.ccs.tencentyun.com"
  ]
}
EOF

# 2. 重启 Docker 使生效
sudo systemctl restart docker

# 3. 验证加速器已加载
docker info | grep -A3 "Registry Mirrors"

# 4. 重新构建即可正常拉取基础镜像
docker build -t painteragent:1.0.0 .
```

### 备选：完全离线的方式（服务器连不上构建环境时）

```bash
# 本地导出镜像为 tar
docker save -o painteragent.tar painteragent:1.0.0

# 上传到服务器
scp painteragent.tar user@server:/tmp/

# 服务器上导入
docker load -i /tmp/painteragent.tar
```

### 多架构构建：同时编出 amd64 + arm64（arm 服务器部署关键）

> 背景：普通 `docker build` 或 buildx 默认的 `docker` 驱动只编**本机架构**。在 amd64 开发机上编出的镜像是 amd64 的，放到 arm64 服务器（鲲鹏/飞腾、Apple Silicon 云主机等）上跑不起来。本项目依赖全是纯 Python 包，`python:3.11-slim` 也是多架构基础镜像，所以用下面的 buildx 方法在 amd64 机器上就能同时编出两个架构，无需在 arm 服务器上重新构建。

**一键脚本（推荐）：**

```bash
# 分平台产出 docker 格式 tar（默认），可直接 docker load
./build-multiarch.sh
# 产出: painteragent-1.0.0-amd64.tar / painteragent-1.0.0-arm64.tar

# 或直接构建并推送双平台镜像到仓库
./build-multiarch.sh --push registry.example.com/painteragent:1.0.0
```

脚本会依次做：检查 docker/buildx → 安装 binfmt 跨架构模拟器（幂等，重复执行安全）→ 创建并启用 `docker-container` 驱动的 `multiarch` builder（自动配好 buildkit 国内镜像加速）→ 执行多平台构建。可通过环境变量 `IMAGE_NAME` / `IMAGE_TAG` / `PLATFORMS` / `MIRRORS` / `PIP_INDEX_URL` 自定义。

> 默认产出的是 **docker 格式**的分平台 tar，任何版本的 `docker load` 都能导入。`--output type=oci` 的单文件多架构归档（`--oci` 模式）经典镜像存储的 `docker load` 不支持（报 `blobs/json: no such file or directory`），只有在启用了 containerd 镜像存储的新版 Docker 上才能 load，一般不推荐。

**离线归档的部署（无镜像仓库场景）：**

```bash
# amd64 服务器
scp painteragent-1.0.0-amd64.tar user@server:/tmp/
docker load -i /tmp/painteragent-1.0.0-amd64.tar

# arm64 服务器
scp painteragent-1.0.0-arm64.tar user@server:/tmp/
docker load -i /tmp/painteragent-1.0.0-arm64.tar

docker images | grep painteragent   # 确认镜像已导入
```

> 注意：脚本打的 tag 是 `painteragent:1.0.0-<arch>`（带架构后缀，避免两台平台 tar 在同一机器上 load 时互相覆盖）。第六节 `docker run` 用的是 `painteragent:1.0.0`，直接跑会提示找不到该镜像。两种处理：
> - 改名后再跑（最贴近第六节命令）：`docker tag painteragent:1.0.0-arm64 painteragent:1.0.0`
> - 或直接指定带后缀的 tag 跑：`docker run ... painteragent:1.0.0-arm64`
>
> 然后按第六节启动容器（tag 换成上面确认到的名字）。

**校验多架构结果（推送到仓库的场景）：**

```bash
docker buildx imagetools inspect registry.example.com/painteragent:1.0.0
# 输出中 Platform 应同时列出 linux/amd64 与 linux/arm64
```

**降级方案：若 `docker load` 对 OCI 归档有兼容性问题，退回分平台手工构建：**

```bash
docker buildx build --platform linux/amd64 -t painteragent:1.0.0-amd64 --load .
docker buildx build --platform linux/arm64 -t painteragent:1.0.0-arm64  --load .
docker save -o painteragent-amd64.tar painteragent:1.0.0-amd64
docker save -o painteragent-arm64.tar  painteragent:1.0.0-arm64
# 分别把对应架构的 tar 传到对应架构服务器上 docker load
```

> 注意：`--load` 只支持单平台；多平台要么 `--push` 到仓库、要么用 docker 格式分平台 tar（默认模式）或 OCI 归档（`--oci`，仅新版 containerd 镜像存储可 load）。首次构建 arm64 平台要经 binfmt 模拟、pip 安装会比本机架构慢，属正常现象。
>
> **基础镜像加速的重要区别**：普通 `docker build` 走 daemon 的 `registry-mirrors`；而本脚本用的 `docker-container` builder 是**独立的 buildkit 容器，不读 daemon 配置**，若直接拉取 `python:3.11-slim` 会报 `connection reset by peer` / `i/o timeout`。脚本会自动生成 `.buildx/buildkitd.toml` 给 builder 单独配置镜像加速器（daocloud 等），并用指纹文件跟踪——改了 `MIRRORS` 环境变量后重跑脚本会自动重建 builder 使新配置生效。若默认加速器在你的网络不可用，用 `MIRRORS=... ./build-multiarch.sh` 覆盖（逗号分隔）。

## 六、第三步：在服务器运行

若走离线 tar 方式，先 `docker load -i`；若镜像已在本地则直接运行。

```bash
# 方式 A：直接 docker run（本方案首选，单容器）
# 数据用 Docker 命名卷 painteragent_memory 持久化，不暴露宿主机裸路径，防误删
docker run -d --name painteragent \
  -p 18088:18088 \
  -v painteragent_memory:/app/memory \
  --env-file .env \
  --restart unless-stopped \
  painteragent:1.0.0
```

> 密钥说明：镜像已排除 `.env`（见 `.dockerignore`），运行时必须注入环境变量，否则豆包接口返回 500。下面两种方式都把服务器上的 `.env` 传给容器，保证密钥不进镜像。

参数说明：
- `-p 18088:18088`：宿主机端口 18088 映射到容器 18088（如需改对外端口，如 `9000:18088`）
- `-v painteragent_memory:/app/memory`：用 Docker **命名卷**持久化 SQLite 会话数据，防止重构容器丢记忆。卷由 Docker 管理（存于 `/var/lib/docker/volumes/painteragent_memory/`），无宿主机裸路径，避免被其他管理员误删。
- `--restart unless-stopped`：服务器重启后自动拉起容器

> 方式 B（docker-compose，可选）见下文「可选项：用 docker-compose 运行」。

### 可选项：用 docker-compose 运行（了解场景，按需选用）

`docker-compose.yml` 本质上就是把上面那条 `docker run` 的参数（端口、卷、重启策略、环境变量）写进一个 yaml 配置文件。本项目只有一个容器，用 `docker run` 完全够；以下场景才值得切换到 compose：

- 想把这套启动参数**文件化、进 git 版本管理**，换机/重装能一键还原；
- 后续可能**增加更多容器**（如 Web 前端、数据库、旁路服务）需要一起编排管理；
- 想让项目配置（environment）和启动描述与代码放一起维护。

若要用 compose，先在服务器上用 docker save/load（或本地 build）得到 `painteragent:1.0.0` 镜像，然后：

```bash
mkdir -p /srv/painteragent && cd /srv/painteragent
cp 项目里的 docker-compose.yml 到该目录
cp .env 到该目录（compose 通过 env_file: .env 注入密钥）
docker compose up -d
```

> 说明：此目录只放 compose 配置与 `.env`（会话数据在 Docker 卷 `painteragent_memory`，见下）。
> 持久化：compose 与 `docker run` 的卷**不同名**——compose 会把声明卷 `painteragent_memory` 按项目名前缀重命名为 `painteragent_painteragent_memory`（当前已部署容器即为该卷），而 `docker run -v painteragent_memory` 创建的是字面名为 `painteragent_memory` 的卷。**两种方式会得到两套会话记忆，同一台服务器请只跑其中一种**。

> 注意：compose 固定写了 `image: painteragent:1.0.0`，与本方案 `docker run` 使用的 tag 一致，可视为等价的两种启动方式。

### 备份与恢复会话数据（命名卷 painteragent_painteragent_memory）

会话记忆存在 Docker 卷里，备份用临时容器把卷打成 tar；恢复则反向解压回卷。

> 卷名：compose 方式部署时实际卷名为 `painteragent_painteragent_memory`（先 `docker volume ls | grep painteragent` 确认），若用的是 `docker run -v painteragent_memory` 则卷名为 `painteragent_memory`，把下面命令里的卷名替换成实际名字。

```bash
# 备份：把 painteragent_painteragent_memory 卷打包到当前目录 memory-backup.tar
docker run --rm -v painteragent_painteragent_memory:/data -v "$(pwd)":/backup \
  alpine tar czf /backup/memory-backup.tar.gz -C /data .

# 恢复：把 tar 解压回 painteragent_painteragent_memory 卷
docker run --rm -v painteragent_painteragent_memory:/data -v "$(pwd)":/backup \
  alpine tar xzf /backup/memory-backup.tar.gz -C /data

# 迁移到新服务器：先在本机导出上述 tar，scp 到新机后在新机上执行恢复命令即可
```

> 提示：备份/恢复前建议先停容器（`docker stop painteragent`），避免 SQLite 正在写入时打包出损坏数据；完成后 `docker start painteragent`。

## 七、验证部署是否成功

```bash
# 查看容器运行状态
docker ps | grep painteragent

# 查看日志
docker logs -f painteragent

# 本地健康检查（能返回 JSON 即说明服务起来了）
curl -X POST http://<服务器IP>:18088/api/whiteboard-agent/clear-history \
  -H "Content-Type: application/json" -d '{"sessionId": 1}'
```

`generate-image` 接口需要构造 `queryInfo`，简单 curl 示例：

```bash
curl -X POST http://<服务器IP>:18088/api/whiteboard-agent/generate-image \
  -H "Content-Type: application/json" -d '{
    "sessionId": 1,
    "queryInfo": [
      {"dataType": 0, "data": {"memory": {"text": "画一只熊猫"}}}
    ]
  }'
```

## 八、常见问题排查

| 现象 | 排查方向 |
|------|---------|
| `docker: command not found` | 未安装 Docker，回到第四节 |
| 容器立即退出 / 持续重启 | `docker logs <容器名>` 看报错 |
| 端口被占用 | 改宿主端口映射，如 `-p 9000:18088` |
| 镜像加载后找不到/名称不对 | `docker images` 确认镜像名字，`docker run` 的 tag 需与构建一致 |
| `docker run` 报 `Conflict. The container name "/painteragent" is already in use` | 已存在同名容器（可能已停止），先 `docker stop painteragent && docker rm painteragent`（不要加 `-v`，保留会话卷）再运行 |
| 启动报找不到依赖 / pip 安装报 `Read timed out`（清华源偶发下载超时） | Dockerfile 已给 pip 加 `--timeout 120 --retries 10`，并在清华源失败时**自动回退** `https://pypi.mirrors.ustc.edu.cn/simple`；仍失败可用 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ ./build-multiarch.sh` 换源（会作为 `--build-arg` 传入） |
| 构建拉取基础镜像超时（`2026...: i/o timeout`） | 国内网络访问 Docker Hub 超时，按第五节「国内网络」配置 registry mirror 后重试 |
| 一问请求返回 500 | 看日志，多为豆包 API Key/模型名配置问题 |

## 九、安全与上线建议（重要）

1. **API Key 与密钥**：豆包 Key 已改为从环境变量读取（`os.getenv`），保存在 `.env`。`.gitignore` 已排除 `.env`，`.dockerignore` 已排除 `.env`，因此密钥**不进 git、不进镜像**，构建时无需额外处理密钥。
2. **部署时注入密钥**：`docker run` 用 `--env-file .env`，compose 用 `env_file: .env`。服务器上的 `.env` 按 `.env.example` 模板创建。
3. **若仓库是公开的**：绝不能把真实 Key 提交进去。请立即到火山方舟控制台**轮换**现有 Key 并移除历史明文。
4. **升级更新**：重新构建新版（多架构用 `./build-multiarch.sh`）→ 上传 → load 导入新镜像 → **先 `docker stop painteragent && docker rm painteragent` 移除旧容器**（不要加 `-v`，避免删掉会话卷）→ 再按第六节 `docker run` 启动新镜像；若用了 compose，则 `docker compose up -d --build` 重建即可。
5. **限制对外暴露**：建议通过 Nginx/网关反代并做访问控制，不要把 18088 直接裸奔到公网。

## 十、后续可选改造（按需）

- 多环境（dev/prod）通过环境变量区分
- 增加健康检查 `/healthz` 并配置 compose `healthcheck`
