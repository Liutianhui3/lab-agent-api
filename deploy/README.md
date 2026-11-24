# ECS Docker + GitHub Actions 部署

## 架构

公网 IP:8080 → web（Nginx + Vue 静态文件，容器内 80）→ api（FastAPI，8000）→ Redis / MySQL。
仅 web 发布端口；Redis、uploads、data 使用命名卷。MySQL 使用单独的 RDS 或已有实例，不包含在此 Compose 中。
后端使用单 worker，避免每个进程重复启动预约定时任务。

两个仓库分别构建镜像到 GHCR；提交代码不会触发构建或部署。仅在 GitHub Actions 点击 Run workflow 后构建镜像，并根据开关决定是否通过 SSH 部署。默认只构建，首次初始化后开启部署开关。
当前脚本使用 latest 部署，同时保留 commit SHA 镜像标签供回滚。不是零停机部署，更新时可能有短暂中断。

## 1. ECS 准备

推荐 Ubuntu 24.04、x86_64、至少 2 核 4GB。本工作流构建 linux/amd64，不适用于 ARM ECS。
安装 Docker Engine、Buildx、Docker Compose v2 插件，参照官方文档：
https://docs.docker.com/engine/install/ubuntu/

服务器执行确认：

```bash
docker version
docker compose version
sudo apt-get update
sudo apt-get install -y util-linux
sudo mkdir -p /opt/lab-agent
```

安全组开放 8080，SSH 22 按实际使用来源限制；若 GitHub 托管 runner 通过 SSH 部署，需要允许 runner 的出站地址访问 SSH（地址动态变化，可改用固定出口 runner）。
不要开放 API、MySQL、Redis 端口。宿主已有 Nginx 和 myBlob 保持运行，新项目使用 8080，不修改原有站点。
当前按公网 IP + 8080 提供 HTTP 访问。
HTTPS 可由阿里云 ALB 终止 TLS，或给 web 配置 443、挂载证书并修改 Nginx；仅放行 443 不会自动启用 HTTPS。

## 2. GitHub 配置（两个仓库分别配置）

将本次文件提交至各自仓库的默认分支，以便 Actions 显示手动运行入口。
Actions 需要允许 GITHUB_TOKEN 写入 Packages；组织有额外限制时需管理员放行。

Settings → Secrets and variables → Actions，添加 Repository secrets：

| Secret | 内容 |
| --- | --- |
| ECS_HOST | ECS 公网 IP / SSH 域名 |
| ECS_USER | 服务器部署用户 |
| ECS_PORT | SSH 端口，可不设置，默认 22 |
| ECS_SSH_KEY | 部署专用 SSH 私钥全文 |
| ECS_KNOWN_HOSTS | 校验过指纹的服务器 known_hosts 行 |

部署用户需要能运行 Docker，并读写 /opt/lab-agent。Docker 用户组具有高权限，应使用专用部署账户。
公钥添加到该用户 ~/.ssh/authorized_keys。不要把私钥放进代码仓库。
可在可信本机运行 `ssh-keyscan -p 22 服务器IP` 收集 known_hosts，务必与 ECS 控制台可信渠道核对指纹后再保存，不能在 CI 中关闭主机校验。

暂时不要设置 DEPLOY_ENABLED。先各运行一次工作流，确认两个 GHCR 镜像都已生成。

## 3. 服务器初始化（一次）

将后端 deploy/ 下的 compose.yaml、deploy.sh、.env.example、backend.env.example 上传到 /opt/lab-agent。
以下命令以具有 Docker 和目录权限的部署用户运行：

```bash
cd /opt/lab-agent
cp .env.example .env
cp backend.env.example backend.env
chmod 600 .env backend.env
nano .env
nano backend.env
```

.env 中 API_IMAGE / WEB_IMAGE 改为真实的 GHCR 地址，全部小写，例如：

```dotenv
API_IMAGE=ghcr.io/yourname/lab-agent-api:latest
WEB_IMAGE=ghcr.io/yourname/lab-agent-web:latest
```

backend.env 填写生产 MySQL、JWT 密钥和模型配置。Redis 地址由 Compose 覆盖为 redis://redis:6379/0。
不要使用本机开发地址 localhost:3306：容器中的 localhost 是容器自身。RDS 填同 VPC 内网地址。
如使用 ECS 宿主 MySQL，可填 host.docker.internal，但 MySQL 需监听 Docker 网关可达地址并授权对应来源；不要为此把 3306 暴露公网。
DATABASE_URL 中密码的特殊字符需要 URL 编码。JWT 密钥可使用 `openssl rand -hex 48` 生成。
env 文件中含 `$` 的字面值建议用单引号包裹，避免 Compose 插值。

预先创建数据库并授权应用账户；脚本只迁移表结构，不创建数据库，也不导入本地数据或管理员账户。
需要旧数据时，先备份并导入 MySQL，再执行部署。旧 uploads/data 也需单独迁移到对应命名卷，注意应用 UID 为 10001。

如果 GHCR 镜像私有，以部署用户登录（不要仅以其他用户登录）：

```bash
docker login ghcr.io -u YOUR_GITHUB_USER
```

密码使用具有 read:packages 权限且能访问相关包的 token；按组织要求授权 SSO。公开镜像可以跳过登录。

首次启动：

```bash
cd /opt/lab-agent
docker compose config --quiet
bash deploy.sh all
docker compose ps
curl -f http://127.0.0.1:8080/healthz
```

浏览器访问 http://服务器IP:8080，验证登录、预约、上传和 AI 流式响应。healthz 只验证 Nginx，API 健康检查只验证 HTTP 可达；仍需进行真实业务验收。

## 4. 手动发布

两个仓库分别添加 Repository variable：`DEPLOY_ENABLED=true`。
提交代码后，在对应仓库 Actions → Build and deploy → Run workflow，选择 main（或需要发布的分支），再点击 Run workflow：构建镜像 → 推送 GHCR → SSH → 串行获取部署锁 → 拉取镜像 → 后端迁移 → 健康检查。
仅提交或合并代码不会触发工作流。DEPLOY_ENABLED=true 仅表示手动运行时允许部署，不会开启提交触发。
同一仓库不同分支都写入 latest；请仅手动运行你希望部署到生产的分支。
前端更新只更新 web；后端更新会重建 web，使 Nginx 重新解析 API 容器地址。
服务器 deploy.sh / compose.yaml 修改不会随镜像更新自动同步，需要单独上传后再发布。
首次发布前请先手动初始化，两边 workflow 的首次发布不能代替初始化。

## 5. 日志、备份和回滚

```bash
cd /opt/lab-agent
docker compose logs --tail 100 -f api web
docker compose ps
```

每次涉及数据库迁移前备份 MySQL。命名卷在容器重建后保留，但仍须定期备份。
不要执行 `docker compose down -v`，会删除 Redis、上传文件和 data 卷。
latest 是可变标签；每次同时发布的完整 commit SHA 标签可用于确定版本。
回滚时将 .env 对应镜像从 :latest 改为 :目标提交SHA，再执行 `bash deploy.sh web` 或 `bash deploy.sh api`。
应用回滚不等于数据库回滚；如果迁移与旧代码不兼容，需要单独制定恢复方案。
回滚后要恢复跟随下一次手动发布，将对应镜像标签重新改回 :latest。
脚本失败会使 Actions 报错，但不会自动回滚数据库或应用。
