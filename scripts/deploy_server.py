"""一键部署到国内服务器（Nginx + 静态站 + 服务器本地爬虫每日更新）。

用法：
    python scripts/deploy_server.py <服务器IP> [用户名] [密码]

前提：服务器为 Ubuntu 22.04，root/密码可 SSH 登录，22/80 端口已放行。
"""

from __future__ import annotations

import os
import posixpath
import sys
import time

import paramiko

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(REPO_ROOT, "web")


def ssh(host: str, user: str, pwd: str) -> paramiko.SSHClient:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, port=22, username=user, password=pwd, timeout=20, banner_timeout=20)
    return cli


def run(cli: paramiko.SSHClient, cmd: str, ok_status=(0,), timeout=120) -> tuple[int, str, str]:
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore")
    err = stderr.read().decode("utf-8", "ignore")
    code = stdout.channel.recv_exit_status()
    if code not in ok_status:
        raise RuntimeError(f"命令失败({code}): {cmd}\nSTDOUT:{out}\nSTDERR:{err}")
    return code, out, err


def upload_dir(cli: paramiko.SSHClient, local: str, remote: str) -> None:
    sftp = cli.open_sftp()
    try:
        for root, dirs, files in os.walk(local):
            rel = os.path.relpath(root, local)
            target = remote if rel == "." else posixpath.join(remote, rel.replace(os.sep, "/"))
            try:
                sftp.stat(target)
            except FileNotFoundError:
                sftp.mkdir(target)
            for f in files:
                sftp.put(os.path.join(root, f), posixpath.join(target, f))
    finally:
        sftp.close()


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "114.55.170.164"
    user = sys.argv[2] if len(sys.argv) > 2 else "root"
    pwd = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("SRV_PASS", "")
    if not pwd:
        print("请通过环境变量 SRV_PASS 或第3个参数提供密码")
        return 1

    cli = ssh(host, user, pwd)
    try:
        print("[1/5] 更新系统并安装 Nginx ...")
        run(cli, "apt-get update -qq && apt-get install -y -qq nginx cron curl >/dev/null 2>&1; echo done")

        print("[2/5] 上传网站文件到 /var/www/teacher-hire ...")
        run(cli, "rm -rf /var/www/teacher-hire && mkdir -p /var/www/teacher-hire/data")
        upload_dir(cli, WEB_DIR, "/var/www/teacher-hire")

        print("[3/5] 配置 Nginx ...")
        conf = """server {
    listen 80 default_server;
    server_name _;
    root /var/www/teacher-hire;
    index index.html;
    gzip on;
    gzip_types text/css application/javascript application/json;
    location /data/ {
        add_header Cache-Control "no-cache";
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}"""
        sftp = cli.open_sftp()
        with sftp.open("/etc/nginx/sites-available/teacher-hire", "w") as f:
            f.write(conf)
        sftp.close()
        run(cli, "rm -f /etc/nginx/sites-enabled/default && ln -sf /etc/nginx/sites-available/teacher-hire /etc/nginx/sites-enabled/teacher-hire")
        run(cli, "nginx -t && systemctl restart nginx && systemctl enable nginx")

        print("[4/5] 安装爬虫运行环境（Python + 依赖）...")
        run(cli, "apt-get install -y -qq python3-pip >/dev/null 2>&1 || apt-get install -y -qq python3 python3-venv >/dev/null 2>&1; echo ok")
        run(cli, "pip3 install --break-system-packages -q beautifulsoup4 lxml >/dev/null 2>&1 || pip3 install -q beautifulsoup4 lxml >/dev/null 2>&1; echo ok")
        run(cli, "rm -rf /opt/teacher-hire && mkdir -p /opt/teacher-hire")
        upload_dir(cli, os.path.join(REPO_ROOT, "crawler"), "/opt/teacher-hire/crawler")
        # requirements.txt 一并上传，便于服务器端复装
        sftp = cli.open_sftp()
        sftp.put(os.path.join(REPO_ROOT, "requirements.txt"), "/opt/teacher-hire/requirements.txt")
        sftp.close()

        print("[5/7] 配置每日爬取定时任务（每天 15:30）...")
        cron = (
            "30 15 * * * cd /opt/teacher-hire && "
            "PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python3 -m crawler.runner "
            ">> /var/log/teacher-hire-crawl.log 2>&1 && "
            "mkdir -p /var/www/teacher-hire/data && "
            "cp -f /opt/teacher-hire/web/data/* /var/www/teacher-hire/data/ ; "
            "echo 'crawl done' >> /var/log/teacher-hire-crawl.log"
        )
        run(cli, f'(crontab -l 2>/dev/null | grep -v "teacher-hire"; echo "{cron}") | crontab -')
        run(cli, "crontab -l")

        print("[6/7] 服务器本地跑一次爬虫（生成首版数据）...")
        run(cli, "cd /opt/teacher-hire && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python3 -m crawler.runner > /var/log/teacher-hire-crawl.log 2>&1 || echo '首跑部分源失败，可手动重试'")
        run(cli, "mkdir -p /var/www/teacher-hire/data && cp -f /opt/teacher-hire/web/data/* /var/www/teacher-hire/data/ 2>/dev/null; true")

        print("[7/7] 验证网站 ...")
        _, out, _ = run(cli, "curl -s -o /dev/null -w 'HTTP %{http_code}\\n' http://127.0.0.1/; ls -la /var/www/teacher-hire/data 2>/dev/null | head; tail -5 /var/log/teacher-hire-crawl.log 2>/dev/null")
        print(out)
        print("部署完成！访问 http://" + host)
    finally:
        cli.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
