#!/usr/bin/env python3
import os
from github import Github, Auth


APP_ID = os.getenv("APP_ID")
INSTALLATION_ID = os.getenv("INSTALLATION_ID")

REPO = os.getenv("REPO")
BRANCH = os.getenv("BRANCH", "main")
COMMIT_MESSAGE = os.getenv("COMMIT_MESSAGE", "Update ips.")

def check_env_vars():
    if not APP_ID or not INSTALLATION_ID or not REPO:
        exit(0)

def update_file_with_github_app():
    if not os.path.exists("private-key.pem"):
        return

    with open("private-key.pem", "r") as key_file:
        private_key = key_file.read()

    print("正在通过 GitHub App 认证...")
    auth = Auth.AppAuth(app_id=APP_ID, private_key=private_key)
    installation_auth = auth.get_installation_auth(installation_id=INSTALLATION_ID)

    g = Github(auth=installation_auth)

    repo = g.get_repo(REPO)
    print(f"✅ 成功连接到仓库: {repo.full_name}")

    try:
        contents = repo.get_contents("ips.csv", ref=BRANCH)
        current_sha = contents.sha
        print(f"📄 文件当前 SHA: {current_sha}")
    except Exception as e:
        print(f"❌ 获取文件失败: {e}")
        print("   请确认文件路径和分支名称是否正确")
        return

    try:
        with open("ips.csv", "r") as file:
            new_content = file.read()
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        print("   请确认文件路径是否正确")
        return

    try:
        result = repo.update_file(
            path="ips.csv",
            message=COMMIT_MESSAGE,
            content=new_content,
            sha=current_sha,
            branch=BRANCH
        )
        print(f"✅ 文件更新成功！")
        print(f"   Commit SHA: {result['commit'].sha}")
        print(f"   新文件 SHA: {result['content'].sha}")
    except Exception as e:
        print(f"❌ 更新文件失败: {e}")

if __name__ == "__main__":
    update_file_with_github_app()
